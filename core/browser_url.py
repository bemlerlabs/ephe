"""core/browser_url.py — the headless browser's URL policy (pure, without Playwright).

One file, one question: what is this browser allowed to load at all? It lives here
because the answer needs neither a page nor a dialog — and because the rest of
core/browser.py already carries enough weight per session.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlsplit

from core.reason import reason
from core.engine_config import config_root

# URL-Policy: what the headless browser is allowed to load at all
# The browser cluster does NOT gate itself through a dialog (SELF_GATED_TOOLS
# claims that, but core/browser.py never calls check_sandbox). It gates itself
# through its reach: a model line "open file://~/.ssh/id_rsa" was, right up to
# here, an ordinary file reader without any question.

# What the session HOLDS: the second bound, and the one that is not about reach.

#: Empty in this build. Nothing the browser is launched with keeps a credential
#: across runs: no profile directory, no stored sign-in state, so every cookie and
#: every token dies with the process and the agent acts as nobody but itself.
#:
#: The session-persistence programme fills one of these two keys, and this dict is
#: the only place it may do it, because both halves read the answer from here:
#: `core/browser.py` launches from it, and the approval gate asks
#: `browser_session_is_credentialed()` before it hands a browser tool the no-dialog
#: licence.
#:
#: Two things still have to be DECIDED before that flip ships, and neither is made
#: true by wiring:
#:   1. who consents to the agent acting AS the user on the user's accounts — a
#:      stored sign-in turns "navigate and click" into a person's identity, which is
#:      a different risk class from "which pages may load" (docs/SECURITY_AND_PRIVACY.md,
#:      the "Tool approval" row);
#:   2. which session gets which profile, since one manager already carries several
#:      session contexts (sub-agents among them) and a shared profile would hand each
#:      of them the same identity.
_BROWSER_PROFILE: dict[str, str] = {}

#: What a profile directory would need before `core/browser.py` may start one: the
#: decision above, plus the per-session shape question. Kept as one line so the
#: refusal names the gap instead of pretending the setting is unsupported.
PERSISTENT_PROFILE_UNWIRED = (
    "A browser profile directory is configured, and this build does not start one: "
    "who consents to the agent acting as the user has not been decided, and the "
    "per-session profile shape is open. Decide both in core/browser_url.py "
    "(_BROWSER_PROFILE) and wire the launch in core/browser.py, or clear the setting. "
    "The browser tools are refused rather than run under a licence they no longer hold."
)


def browser_profile_settings() -> dict[str, str]:
    """The launch settings of a session that keeps state across runs; empty keys today."""
    return {
        "user_data_dir": str(_BROWSER_PROFILE.get("user_data_dir") or ""),
        "storage_state": str(_BROWSER_PROFILE.get("storage_state") or ""),
    }


def browser_session_is_credentialed() -> bool:
    """True when the browser session carries an identity the user did not grant here.

    About the launch rather than the page it is on: a stored sign-in, a
    cookie jar or a profile directory means the agent's clicks and typed text go out
    as the user's own, and that is the condition the browser cluster's no-dialog
    licence depends on (`_CREDENTIAL_BOUND_TOOLS` in core/tools/approval_rules.py).
    False while `_BROWSER_PROFILE` stays empty.

    Fail-closed, the same direction as every other default in the gate: a profile
    this code cannot read is a profile that holds something, so it is treated as
    credentialed and the dialog comes back.
    """
    try:
        settings = browser_profile_settings()
    except Exception:  # noqa: BLE001 — an unreadable session shape is not an approval
        return True
    return bool(settings["user_data_dir"] or settings["storage_state"])


def _artifact_roots() -> list[Path]:
    """Ephe's own storage folders — the only ones whose content gets rendered.

    Deliberately NOT ``core.tools.base._get_allowed_roots()``: the preview
    whitelist contains the complete home directory, and ``~/.ssh/id_rsa``
    is not an artifact.
    """
    roots = [
        config_root(),
        Path(os.environ.get("EPHE_IMAGE_DIR") or config_root() / "sessions" / "images"),
        Path("/tmp"),
        Path(os.environ.get("TMPDIR") or "/tmp"),
    ]
    try:
        from core.engine_config import get_output_dir, get_workspace_dir

        for value in (get_output_dir(), get_workspace_dir()):
            if value:
                roots.append(Path(value))
    except Exception:
        pass  # without a workspace only the default folders — tighter, not wider
    return roots


def _split_scheme(raw: str) -> tuple[str, str]:
    """(scheme, candidate-url) — ``localhost:3000`` is a host, not a scheme.

    urlsplit alone walks you into a phantom scheme ``localhost`` there; the
    browser policy must not reject that, or the dev preview is gone.
    """
    head, sep, rest = raw.partition(":")
    if sep and head.isalpha() and rest and not rest[:1].isdigit():
        return head.lower(), raw
    return "", f"https://{raw}"


def url_policy(url: str) -> tuple[bool, str]:
    """(allowed, URL or reason) — a decision, no side effect.

    http/https and data: are allowed; file: only inside the artifact roots
    (symlinks resolved, no ``../`` escape). Everything else — javascript:,
    gopher:, chrome:, ws:, ftp:, about: — is blocked, because the headless
    browser is a web tool, not a host access channel.

    A refusal is a `core.reason.Reason`: the sentence the model reads lives here,
    the wording the card shows is ``reader.<code>`` in both locale bundles.
    """
    raw = (url or "").strip()
    if not raw:
        return False, reason("browser_url_empty", "Empty URL — the browser loads nothing.")
    scheme, candidate = _split_scheme(raw)
    if scheme in ("", "http", "https"):
        return True, candidate
    if scheme == "data":
        return True, candidate
    if scheme != "file":
        return False, reason(
            "browser_scheme_blocked",
            f"{scheme}: is blocked for the headless browser — allowed are http/https, "
            "data: and file: inside Ephe's artifact folders.",
            scheme=scheme,
        )
    path = Path(unquote(urlsplit(candidate).path)).expanduser()
    try:
        resolved = path.resolve()
    except OSError as exc:
        return False, reason(
            "browser_path_unresolvable",
            f"{path} cannot be resolved ({exc}).",
            path=str(path),
            error=str(exc),
        )
    for root in _artifact_roots():
        try:
            root_resolved = root.resolve()
        except OSError:
            continue
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            continue
        if not resolved.is_file():
            return False, reason(
                "browser_target_not_a_file",
                f"{resolved} is not a file inside {root_resolved}.",
                resolved=str(resolved),
                root=str(root_resolved),
            )
        return True, f"file://{resolved}"
    return False, reason(
        "browser_outside_artifact_roots",
        f"{resolved} is outside Ephe's artifact folders — the headless browser reads no "
        "host files. Write the HTML into an allowed folder first (~/.ephe, the output "
        "path or /tmp) and open it from there.",
        resolved=str(resolved),
    )


