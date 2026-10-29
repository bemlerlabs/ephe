"""Take the newest commits on the default branch, from inside the app.

A release the signed updater can install is one path; a checkout that runs the
backend is the other. Both end in the same place — the user clicks once — so
`apply_update` fast-forwards the checkout and then lets `install.sh --no-start`
refresh the environment and the PWA bundle.

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


def _step(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail}


def _refusal(reason: str, detail: str) -> dict[str, Any]:
    return {"ok": False, "reason": reason, "detail": detail, "steps": []}


def apply_update(root: Path | None = None) -> dict[str, Any]:
    """Fast-forward this checkout and reinstall it, or stop with a reason."""
    base = root or project_root()
    if not (base / ".git").exists():
        return _refusal(
            "not_a_checkout",
            "this installation has no git checkout; take the newest release instead",
        )
    if not _BUSY.acquire(blocking=False):
        return _refusal("busy", "an update is already running")
    try:
        branch = _git(base, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        if branch != "main":
            return _refusal("not_on_main", f"this checkout is on {branch or 'no branch'}, not main")
        dirty = _git(base, "status", "--porcelain").stdout.strip()
        if dirty:
            return _refusal(
                "dirty_tree",
                "this checkout has local changes; commit or set them aside first",
            )
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
        installer = base / "install.sh"
        if installer.exists():
            try:
                done = subprocess.run(
                    ["bash", str(installer), "--no-start"],
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
            steps.append(
                _step("install", done.returncode == 0, (done.stdout + done.stderr).strip()[-600:])
            )
            if done.returncode != 0:
                return {"ok": False, "reason": "install_failed",
                        "detail": "the installer stopped with an error", "steps": steps}
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


def _env() -> dict[str, str]:
    import os

    return dict(os.environ)
