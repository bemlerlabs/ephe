"""Ephe — Update check (update-experience wave)
core/update_check.py

The app tells the user when a newer Ephe release exists. PWA and desktop
share this source of truth; the desktop shell additionally offers an
in-place update through the Tauri updater (see app/src-tauri).

Contract (pinned in tests/test_r67_update_check.py):
- semver comparison tolerates "v"-prefixed tags; equal versions are NOT an
  update.
- Fail-soft: an unreachable release source yields available=False with an
  error field — the app never breaks because the check failed.
- TTL cache (default 6 h) keeps the release source from being hammered;
  force=True bypasses it.
- The deep setting `appearance.update_check` (default ON) gates the check —
  privacy-first: opt-out is one toggle, and nothing but an anonymous request
  to the release source is involved (no telemetry, no identifiers).

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

UPDATE_TTL_S = 6 * 3600
#: The continuous channel: merges on the default branch reach a user between two
#: tagged releases. Compared by ancestry, so a checkout that is ahead or has
#: diverged is not told to update.
MAIN_BRANCH = "main"
# A failed check is not an answer worth keeping for six hours: the feed can go
# live, and a button that keeps reporting a stale failure reads as broken. A
# short failure TTL also makes an explicit refresh unnecessary in most cases.
FAILURE_TTL_S = 300
_cache: dict[str, Any] = {"at": None, "value": None}

_SEMVER_RE = re.compile(r"^\D*(\d+)\.(\d+)\.(\d+)")
# The full form keeps the prerelease, because a beta product's whole update
# story lives there: a later beta is newer than an earlier one, and the short
# numeric tuple above cannot tell the two apart.
_SEMVER_FULL_RE = re.compile(
    r"^v?(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"
    r"(?:-(?P<pre>[0-9A-Za-z.-]+))?(?:\+(?P<build>[0-9A-Za-z.-]+))?$"
)


def release_repo() -> str:
    """GitHub repo the release feed is read from (owner can override via env
    before a repository move). Default derives from core.__github__ so the
    release feed follows the canonical product URL."""
    override = os.environ.get("EPHE_UPDATE_REPO")
    if override:
        return override
    from core import __github__

    return __github__.removeprefix("https://github.com/")


def current_version() -> str:
    from core._version import __version__

    return __version__


def _semver(tag: str) -> tuple[int, int, int]:
    m = _SEMVER_RE.match((tag or "").strip())
    if not m:
        return (0, 0, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def _parse(tag: str) -> tuple[int, int, int, list[str] | None] | None:
    """The version with its prerelease kept: (major, minor, patch, pre).

    `pre` is None for a release and a list of identifiers for a prerelease,
    which is what makes a release outrank any of its prereleases."""
    m = _SEMVER_FULL_RE.match((tag or "").strip())
    if not m:
        return None
    pre = m.group("pre")
    return (int(m.group("major")), int(m.group("minor")), int(m.group("patch")),
            pre.split(".") if pre else None)


def _compare(candidate: str, current: str) -> int:
    """Semver order, prereleases included. 0 also means "cannot be ordered",
    which never offers an update — the honest answer for an unparseable tag."""
    a, b = _parse(candidate), _parse(current)
    if a is None or b is None:
        return 0
    if a[:3] != b[:3]:
        return 1 if a[:3] > b[:3] else -1
    pa, pb = a[3], b[3]
    if pa is None and pb is None:
        return 0
    if pa is None:
        return 1
    if pb is None:
        return -1
    for ia, ib in zip(pa, pb):
        if ia == ib:
            continue
        na, nb = ia.isdigit(), ib.isdigit()
        if na and nb:
            return 1 if int(ia) > int(ib) else -1
        if na != nb:
            return -1 if na else 1
        return 1 if ia > ib else -1
    if len(pa) == len(pb):
        return 0
    return 1 if len(pa) > len(pb) else -1


def _is_newer(candidate: str, current: str) -> bool:
    return _compare(candidate, current) > 0


def _fetch_latest() -> dict[str, Any]:
    """Anonymous request against the GitHub release feed. Raises on network
    failure (the caller turns that into an honest unavailable-result)."""
    url = f"https://api.github.com/repos/{release_repo()}/releases/latest"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310 — https, pinned host
        data = json.loads(resp.read().decode("utf-8"))
    return {
        "tag": str(data.get("tag_name") or ""),
        "url": str(data.get("html_url") or f"https://github.com/{release_repo()}/releases"),
        "notes": str(data.get("body") or "")[:600],
    }


def installed_commit() -> str:
    """The commit this build runs on: baked at packaging time, else the checkout's
    HEAD. Empty when neither is known, and then the continuous channel stays quiet."""
    baked = (os.environ.get("EPHE_BUILD_COMMIT") or "").strip()
    if baked:
        return baked
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.exists(os.path.join(root, ".git")):
        return ""
    import subprocess

    try:
        done = subprocess.run(
            ["git", "-C", root, "rev-parse", "HEAD"],
            capture_output=True, timeout=5, check=False, text=True,
        )
    except Exception:  # noqa: BLE001 — a missing git is not an update answer
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def _get_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310 — https, pinned host
        return json.loads(resp.read().decode("utf-8"))


def _fetch_head() -> dict[str, str]:
    """The tip of the default branch: its sha and the newest commit subject.

    GitHub's compare answers with an empty commit list when the build is only
    behind, so the range alone names neither the tip nor what changed."""
    data = _get_json(f"https://api.github.com/repos/{release_repo()}/commits/{MAIN_BRANCH}")
    body = str((data.get("commit") or {}).get("message") or "")
    return {"sha": str(data.get("sha") or ""), "message": body.splitlines()[0][:160] if body else ""}


def _fetch_main_compare(commit: str) -> dict[str, Any]:
    """Ancestry of `commit` against the default branch's tip. Raises on network
    failure like the release fetch."""
    data = _get_json(
        f"https://api.github.com/repos/{release_repo()}/compare/{commit}...{MAIN_BRANCH}"
    )
    commits = data.get("commits") or []
    status = str(data.get("status") or "")
    message = str((commits[-1].get("commit") or {}).get("message") or "") if commits else ""
    tip = str(commits[-1].get("sha") or "") if commits else ""
    if status == "behind" and (not message or not tip):
        head = _fetch_head()
        message = message or head["message"]
        tip = tip or head["sha"]
    return {
        "status": status,
        "behind": int(data.get("behind_by") or 0),
        "sha": str((data.get("base_commit") or {}).get("sha") or ""),
        "tip": tip,
        "message": message.splitlines()[0][:160] if message else "",
    }


def _main_channel(commit: str) -> dict[str, Any] | None:
    """The continuous channel's answer for `commit`, or None when there is none.

    A lookup failure returns None rather than raising: the release answer is
    already in hand and a secondary source going down must not erase it."""
    try:
        main = _fetch_main_compare(commit)
    except Exception as exc:  # noqa: BLE001 — release answer stands without it
        logger.info("main-branch comparison failed: %s", exc)
        return None
    if main["status"] != "behind" or main["behind"] <= 0:
        return None
    return {
        "available": True,
        "channel": "main",
        "latest": (main["tip"] or MAIN_BRANCH)[:12],
        "commit": commit[:12],
        "commitsBehind": main["behind"],
        "url": f"https://github.com/{release_repo()}/compare/{commit}...{MAIN_BRANCH}",
        "notes": main["message"],
    }


def update_check_enabled() -> bool:
    """Deep setting `appearance.update_check` (default ON)."""
    from core.settings_schema import deep_bool

    return deep_bool("appearance.update_check")


def check_for_update(force: bool = False) -> dict[str, Any]:
    """Full contract result; cached within the TTL unless force=True."""
    if not update_check_enabled():
        return {"enabled": False, "available": False}
    now = time.monotonic()
    cached = _cache["value"]
    if not force and cached is not None and _cache["at"] is not None:
        ttl = FAILURE_TTL_S if "error" in cached else UPDATE_TTL_S
        if now - _cache["at"] < ttl:
            return dict(cached)

    current = current_version()
    commit = installed_commit()
    try:
        latest = _fetch_latest()
        newer_release = _is_newer(latest["tag"], current)
        result = {
            "enabled": True,
            "available": newer_release,
            "current": current,
            "latest": latest["tag"].removeprefix("v").removeprefix("V"),
            "url": latest["url"],
            "notes": latest["notes"],
            "channel": "release",
        }
        if commit:
            result["commit"] = commit[:12]
            if not newer_release:
                # A merge that has not been tagged yet is still an update the user
                # can take. Only `behind` says so: ahead and diverged would be
                # telling a checkout to go backwards.
                result.update(_main_channel(commit) or {})
    except Exception as exc:  # noqa: BLE001 — the check must never break the app
        # The exception is for the log below. The client gets a fixed sentence.
        logger.warning("update check failed: %s", exc)
        result = {
            "enabled": True,
            "available": False,
            "current": current,
            "error": "the release source could not be reached",
        }
    _cache["at"], _cache["value"] = now, result
    return dict(result)


def _reset_cache() -> None:
    """Test seam: drop the TTL cache."""
    _cache["at"], _cache["value"] = None, None


# One answer a day across process starts.
#
# The in-memory TTL above describes a running process. A terminal app that is
# opened ten times a day would ask the feed ten times without a store that
# outlives it, and the product promise here is one look a day.
DAY_S = 24 * 3600
STATE_FILE = "update.json"
OPT_OUT_ENV = "EPHE_NO_UPDATE_CHECK"


def state_path() -> Path:
    from core.engine_config import config_root

    return config_root() / STATE_FILE


def load_daily_state() -> dict[str, Any]:
    try:
        payload = json.loads(Path(state_path()).read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_daily_state(result: dict[str, Any], now: float) -> None:
    payload = {"checked_at": now, "result": result}
    target = state_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except Exception:
        pass


def daily_check(now: float | None = None) -> dict[str, Any]:
    """The release answer, asked at most once a day across process starts."""
    if os.environ.get(OPT_OUT_ENV):
        return {"enabled": False, "available": False}
    stamp = time.time() if now is None else now
    stored = load_daily_state()
    checked = stored.get("checked_at")
    result = stored.get("result")
    if isinstance(checked, (int, float)) and isinstance(result, dict):
        if stamp - float(checked) < DAY_S:
            return dict(result)
    fresh = check_for_update(force=True)
    if fresh.get("enabled", True):
        _save_daily_state(fresh, stamp)
    return fresh


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


def run_update(root: Path | None = None) -> tuple[bool, str]:
    """Pull the checkout and reinstall. Returns (ok, one line to show)."""
    checkout = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    installer = checkout / "install.sh"
    if not installer.exists():
        return False, "install.sh not found"

    pulled = _git(checkout, "pull", "--ff-only")
    if pulled.returncode != 0:
        tail = (pulled.stderr or pulled.stdout or "").strip().splitlines()
        return False, tail[-1] if tail else "git pull failed"

    env = os.environ.copy()
    env["EPHE_NO_START"] = "1"
    try:
        installed = subprocess.run(
            ["bash", str(installer), "--no-start"],
            cwd=str(checkout),
            env=env,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        return False, str(exc)
    if installed.returncode != 0:
        tail = (installed.stderr or installed.stdout or "").strip().splitlines()
        return False, tail[-1] if tail else f"installer exited {installed.returncode}"
    _reset_cache()
    try:
        Path(state_path()).unlink()
    except Exception:
        pass
    return True, "updated"
