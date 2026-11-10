"""Take an update, from inside the app.

Three paths share the installer half:
- `apply_release`: move the checkout to a published release tag. This is the
  only update the terminal CLI/TUI takes, and the PWA's release button.
- `apply_update`: fast-forward to the default branch's tip, for the commit
  channel the desktop app and PWA offer between tags.
- `reinstall`: the installer alone, for a tree the desktop shell has moved.

Every one of them stops before the first command when it cannot finish, and
none of them touches the running shell's own UI: the PWA the backend serves is
refreshed, the installed desktop bundle is replaced only by the signed updater.

Every refusal is a sentence with a reason code, and none of them runs a command:
a dirty tree, another branch or a second click while one runs stops first. The
running shell's own UI is bundled with the app and is not touched here; the PWA
the same backend serves is.
"""
from __future__ import annotations

import subprocess
import threading
from pathlib import Path
from typing import Any

PULL_TIMEOUT_S = 180
INSTALL_TIMEOUT_S = 1800
_BUSY = threading.Lock()


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git(root: Path, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=timeout, check=False
    )


#: One sentence per refusal, for the log and the API reader. The surface owns
#: the words the user sees; these travel beside the code, never instead of it.
_REFUSAL_DETAIL = {
    "not_a_checkout": "this installation has no git checkout; take the newest release instead",
    "not_on_main": "this checkout is on a development branch, not on main",
    "dirty_tree": "this checkout has local changes; commit or set them aside first",
    "release_unreachable": "the release source could not be reached",
    "tag_missing": "the release tag is not in this checkout",
    "fetch_failed": "the release tag could not be fetched",
    "ahead_of_release": (
        "this checkout is ahead of the newest release; "
        "the release channel never moves it backwards"
    ),
    "release_failed": "the release tag did not fast-forward",
}


def _step(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail}


def _refusal(reason: str, detail: str) -> dict[str, Any]:
    return {"ok": False, "reason": reason, "detail": detail, "steps": []}


def probe(root: Path | None = None, *, release: bool = False) -> dict[str, Any]:
    """Whether this installation *can* move the tree, without moving it.

    The surface asks before it offers the button: a build installed from a
    release has no checkout to fast-forward, and a checkout on another branch
    would have to be moved first, so neither is a failure a retry can cure.

    A release update may run from `main` or from a checkout already parked on a
    tag (detached HEAD); a commit update only from `main`, because it is the
    branch's tip it follows."""
    base = root or project_root()
    if not (base / ".git").exists():
        return {"ok": False, "code": "not_a_checkout"}
    branch = _git(base, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != "main" and not (release and branch == "HEAD"):
        return {"ok": False, "code": "not_on_main"}
    if _git(base, "status", "--porcelain").stdout.strip():
        return {"ok": False, "code": "dirty_tree"}
    return {"ok": True, "code": ""}


def apply_release(root: Path | None = None) -> dict[str, Any]:
    """Move the checkout to the newest published release tag, or stop.

    The release feed decides *whether* to move; the tag, not the branch tip,
    decides *where* to. A checkout on `main` is fast-forwarded to the tag, so
    merges after the tag stay out of a release-pinned installation. A checkout
    already past the newest tag is refused: the release channel never rewrites
    a tree backwards. A checkout already on the tag is a no-op."""
    base = root or project_root()
    from core import update_check

    # The feed is asked before git is touched: an unreachable source is an
    # answer, so no git command runs for it.
    try:
        status = update_check.release_status()
    except Exception:  # noqa: BLE001 — no answer, no command
        return _refusal("release_unreachable", _REFUSAL_DETAIL["release_unreachable"])
    if not status.get("available"):
        return {
            "ok": True,
            "reason": "latest_release",
            "detail": f"Ephe {status.get('current', '?')} is the newest release",
            "steps": [],
        }
    ready = probe(base, release=True)
    if not ready["ok"]:
        return _refusal(ready["code"], _REFUSAL_DETAIL.get(ready["code"], ""))
    if not _BUSY.acquire(blocking=False):
        return _refusal("busy", "an update is already running")
    try:
        steps: list[dict[str, Any]] = []
        tag = str(status.get("tag") or "")
        if not tag:
            return _refusal("tag_missing", _REFUSAL_DETAIL["tag_missing"])
        ref = f"refs/tags/{tag}"
        if _git(base, "rev-parse", "--verify", ref).returncode != 0:
            try:
                fetched = _git(
                    base, "fetch", "--tags", "--force", "origin", timeout=PULL_TIMEOUT_S
                )
            except subprocess.TimeoutExpired:
                return _refusal("fetch_failed", _REFUSAL_DETAIL["fetch_failed"])
            steps.append(
                _step("fetch", fetched.returncode == 0, (fetched.stdout + fetched.stderr).strip()[-600:])
            )
            if fetched.returncode != 0:
                return {
                    "ok": False,
                    "reason": "fetch_failed",
                    "detail": _REFUSAL_DETAIL["fetch_failed"],
                    "steps": steps,
                }
        target = _git(base, "rev-parse", f"{ref}^{{commit}}")
        if target.returncode != 0:
            return _refusal("tag_missing", _REFUSAL_DETAIL["tag_missing"])
        target_sha = target.stdout.strip()
        before_sha = _git(base, "rev-parse", "HEAD").stdout.strip()
        before = _git(base, "rev-parse", "--short", "HEAD").stdout.strip()
        if before_sha == target_sha:
            return {
                "ok": True,
                "reason": "latest_release",
                "detail": f"already on release {tag}",
                "steps": steps,
                "before": before,
                "after": before,
                "restart": False,
                "tag": tag,
            }
        ancestor = _git(base, "merge-base", "--is-ancestor", "HEAD", target_sha)
        if ancestor.returncode != 0:
            return {
                "ok": False,
                "reason": "ahead_of_release",
                "detail": _REFUSAL_DETAIL["ahead_of_release"],
                "steps": steps,
            }
        try:
            merged = _git(base, "merge", "--ff-only", ref, timeout=PULL_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return _refusal("release_failed", _REFUSAL_DETAIL["release_failed"])
        steps.append(
            _step("release", merged.returncode == 0, (merged.stdout + merged.stderr).strip()[-600:])
        )
        if merged.returncode != 0:
            return {
                "ok": False,
                "reason": "release_failed",
                "detail": _REFUSAL_DETAIL["release_failed"],
                "steps": steps,
            }
        after_sha = _git(base, "rev-parse", "HEAD").stdout.strip()
        after = _git(base, "rev-parse", "--short", "HEAD").stdout.strip()
        if (base / "install.sh").exists():
            refused = _installer_run(base, steps)
            if refused is not None:
                return refused
        # The answer that offered this release is stale now; a check in this
        # process must not keep naming a tag the tree already runs.
        update_check._reset_cache()
        return {
            "ok": True,
            "reason": "",
            "detail": f"{tag} installed ({before} → {after})",
            "steps": steps,
            "before": before,
            "after": after,
            "tag": tag,
            "restart": before_sha != after_sha,
        }
    finally:
        _BUSY.release()


def apply_update(root: Path | None = None) -> dict[str, Any]:
    """Fast-forward this checkout and reinstall it, or stop with a reason."""
    base = root or project_root()
    ready = probe(base)
    if not ready["ok"]:
        return _refusal(ready["code"], _REFUSAL_DETAIL.get(ready["code"], ""))
    if not _BUSY.acquire(blocking=False):
        return _refusal("busy", "an update is already running")
    try:
        steps: list[dict[str, Any]] = []
        before = _git(base, "rev-parse", "--short", "HEAD").stdout.strip()
        try:
            pulled = _git(base, "pull", "--ff-only", timeout=PULL_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return _refusal("pull_timeout", "the checkout did not finish pulling in three minutes")
        steps.append(
            _step("pull", pulled.returncode == 0, (pulled.stdout + pulled.stderr).strip()[-600:])
        )
        if pulled.returncode != 0:
            return {"ok": False, "reason": "pull_failed", "detail": "git pull was refused",
                    "steps": steps}
        after = _git(base, "rev-parse", "--short", "HEAD").stdout.strip()
        if (base / "install.sh").exists():
            refused = _installer_run(base, steps)
            if refused is not None:
                return refused
        return {
            "ok": True,
            "reason": "",
            "detail": f"{before} → {after}" if before != after else f"{before} (already current)",
            "steps": steps,
            "before": before,
            "after": after,
            "restart": before != after,
        }
    finally:
        _BUSY.release()


def _installer_run(base: Path, steps: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Run this tree's installer and append the step. `None` means it landed.

    The tree is the working directory, so the installer resolves its own paths
    and the checkout's location never travels in a command line.
    """
    try:
        done = subprocess.run(
            ["bash", str(base / "install.sh"), "--no-start"],
            cwd=str(base),
            capture_output=True,
            text=True,
            timeout=INSTALL_TIMEOUT_S,
            check=False,
            env={**_env(), "EPHE_NO_START": "1"},
        )
    except subprocess.TimeoutExpired:
        steps.append(_step("install", False, "the installer did not finish in 30 minutes"))
        return {"ok": False, "reason": "install_timeout", "detail": "installer timed out",
                "steps": steps}
    steps.append(_step("install", done.returncode == 0, (done.stdout + done.stderr).strip()[-600:]))
    if done.returncode != 0:
        return {"ok": False, "reason": "install_failed",
                "detail": "the installer stopped with an error", "steps": steps}
    return None


def reinstall(root: Path | None = None) -> dict[str, Any]:
    """Refresh the environment around this tree, issuing no git of its own.

    The desktop shell owns the release: it replaces the app bundle and moves the
    checkout the backend runs from. That leaves the tree newer than the
    environment around it — the same version number, a different dependency set.
    This is the step that closes that gap: the installer `apply_update` runs,
    called on its own, over a tree the shell has already moved.
    """
    base = root or project_root()
    ready = probe(base)
    if not ready["ok"]:
        return _refusal(ready["code"], _REFUSAL_DETAIL.get(ready["code"], ""))
    if not (base / "install.sh").exists():
        return _refusal("no_installer", "this installation carries no installer to run")
    if not _BUSY.acquire(blocking=False):
        return _refusal("busy", "an update is already running")
    try:
        steps: list[dict[str, Any]] = []
        refused = _installer_run(base, steps)
        if refused is not None:
            return refused
        return {
            "ok": True,
            "reason": "",
            "detail": "the environment was refreshed from this tree",
            "steps": steps,
            # The process that answers here still holds the imports it made at
            # its own start; the refresh only reaches it over a start.
            "restart": True,
        }
    finally:
        _BUSY.release()


def _env() -> dict[str, str]:
    import os

    return dict(os.environ)
