"""Ephe – shell_sandbox: macOS Seatbelt wrapper for the shell tool (R23).

OPT-IN via security.json (`sandbox_enabled`, Settings → Security). Wraps the
approved shell command in `sandbox-exec -p <profile>`:

  - Writing ONLY into the workspace, system TMP and HOME (the profile would
    otherwise be unusable — git/npm write caches into $HOME)
  - Outbound network off (deny network*); a loopback listener is allowed, because
    "start my project" ends in a dev server the user opens in a browser
  - Reading stays allowed (otherwise every toolchain breaks)

Honest limits (documented in docs/SANDBOX_EXECUTION.md): sandbox-exec is
macOS-only (Linux equivalent: bubblewrap — R25/Docs), deprecated-but-working,
and the whitelist guard keeps running BEFORE the sandbox as a hard boundary.
"""
from __future__ import annotations

import os
import shutil
import tempfile


def is_available() -> bool:
    return shutil.which("sandbox-exec") is not None


def build_profile(workspace: str) -> str:
    """SBPL profile: writing only workspace/TMP/HOME plus the device nodes a
    toolchain needs, network off."""
    tmp = tempfile.gettempdir()
    darwin_tmp = "/private" + tmp if not tmp.startswith("/private") else tmp
    ws = os.path.realpath(workspace) if workspace else os.getcwd()
    home = os.path.realpath(os.path.expanduser("~"))
    return (
        "(version 1)\n"
        "(allow default)\n"
        "(deny network*)\n"
        # Narrower than the deny above, and later: binding and accepting on
        # loopback is how a workspace starts its own dev server. Every outbound
        # connection and every non-loopback bind stays refused.
        "(allow network-bind network-inbound (local ip \"localhost:*\"))\n"
        f"(deny file-write*)\n"
        f"(allow file-write*\n"
        f"  (subpath \"{ws}\")\n"
        f"  (subpath \"{tmp}\")\n"
        f"  (subpath \"{darwin_tmp}\")\n"
        f"  (subpath \"{home}\")\n"
        f"  (regex #\"^/private/var/folders/.*\")\n"
        f"  (literal \"/dev/null\")\n"
        f"  (literal \"/dev/tty\")\n"
        f"  (subpath \"/dev/fd\")\n"
        f")\n"
    )


def wrap_command(command: str, workspace: str) -> list[str] | None:
    """Returns the sandbox-exec command line — or None when unavailable."""
    if not is_available():
        return None
    profile = build_profile(workspace)
    # A pager has no tty here and would hang or fail; the /dev/null probe git
    # itself makes is covered by the device nodes in the profile above.
    sh_cmd = f"export GIT_PAGER=cat GIT_PAGER_NO_COLOR=1; {command}"
    return ["sandbox-exec", "-p", profile, "/bin/sh", "-c", sh_cmd]
