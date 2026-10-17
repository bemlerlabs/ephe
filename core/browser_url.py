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

# URL-Policy: what the headless browser is allowed to load at all
# The browser cluster does NOT gate itself through a dialog (SELF_GATED_TOOLS
# claims that, but core/browser.py never calls check_sandbox). It gates itself
# through its reach: a model line "open file://~/.ssh/id_rsa" was, right up to
# here, an ordinary file reader without any question.

def _artifact_roots() -> list[Path]:
    """Ephe's own storage folders — the only ones whose content gets rendered.

    Deliberately NOT ``core.tools.base._get_allowed_roots()``: the preview
    whitelist contains the complete home directory, and ``~/.ssh/id_rsa``
    is not an artifact.
    """
    roots = [
        Path(os.environ.get("EPHE_CONFIG_DIR") or str(Path.home() / ".ephe")),
        Path(os.environ.get("EPHE_IMAGE_DIR") or str(Path.home() / ".ephe" / "sessions" / "images")),
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


