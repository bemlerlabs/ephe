"""Ephe – security_config: approval profile + sandbox switch (R23).

One source: ~/.ephe/security.json (not a secret, still 0600).
  - approval_profile: "strict" (default — always ask on mutating) | "session"
    ("remember for this session" allowed — the EXCEPTION is run_shell: per
    command a tool-type remember is never enough)
  - sandbox_enabled: Seatbelt around the shell (opt-in, macOS sandbox-exec)

Release bar stays: mutating tools without a session profile are ALWAYS asked;
run_shell is never freed by a tool-type remember, not even in the session profile.
"""
from __future__ import annotations

import json

from core import engine_config

#: Four composer modes (parity with the reference selector in the chat window):
#:   strict  – „Ask before changes“  : a mutating tool is always asked
#:   session – „Edit automatically“   : remember per tool type for the session
#:   plan    – „Plan mode“            : agree the plan first, then work it off
#:   full    – „Full access“          : fewer confirmations, runs straight through
VALID_APPROVAL_PROFILES = ("strict", "session", "plan", "full")
#: Tools that are never released via the "remember for this session" checkbox.
NEVER_REMEMBER = frozenset({"run_shell"})


#: The categories a user may ask MORE often about (Wave 2/B3). Only the two that
#: auto-run on the chat path are offered: MUTATING and DANGEROUS already prompt, so
#: there is nothing to raise there, and no override may lower a category.
ASKABLE_CATEGORIES = ("SAFE", "NETWORK")


class SecurityConfig:
    __slots__ = ("approval_profile", "sandbox_enabled", "ask_categories")

    def __init__(
        self,
        approval_profile: str = "strict",
        sandbox_enabled: bool = False,
        ask_categories: tuple[str, ...] = (),
    ) -> None:
        self.approval_profile = approval_profile
        self.sandbox_enabled = sandbox_enabled
        self.ask_categories = ask_categories

    def __repr__(self) -> str:  # no trouble with secrets — there are none here
        return (
            f"SecurityConfig(approval_profile={self.approval_profile!r}, "
            f"sandbox_enabled={self.sandbox_enabled!r}, ask_categories={self.ask_categories!r})"
        )


def security_config_path():
    return engine_config.CONFIG_DIR / "security.json"


def load_security_config() -> SecurityConfig:
    try:
        raw = json.loads(security_config_path().read_text(encoding="utf-8"))
        return SecurityConfig(
            approval_profile=str(raw.get("approval_profile", "strict") or "strict"),
            sandbox_enabled=bool(raw.get("sandbox_enabled", False)),
            ask_categories=tuple(
                category
                for category in raw.get("ask_categories", ())
                if category in ASKABLE_CATEGORIES
            ),
        )
    except Exception:
        return SecurityConfig()


def save_security_config(
    approval_profile: str | None = None,
    sandbox_enabled: bool | None = None,
    ask_categories: list[str] | tuple[str, ...] | None = None,
    path=None,
) -> SecurityConfig:
    existing = load_security_config()
    cfg = SecurityConfig(
        approval_profile=(approval_profile if approval_profile is not None else existing.approval_profile),
        sandbox_enabled=(sandbox_enabled if sandbox_enabled is not None else existing.sandbox_enabled),
        ask_categories=(
            tuple(c for c in ask_categories if c in ASKABLE_CATEGORIES)
            if ask_categories is not None
            else existing.ask_categories
        ),
    )
    if cfg.approval_profile not in VALID_APPROVAL_PROFILES:
        raise ValueError(
            f"Unbekanntes Approval-Profil: {cfg.approval_profile!r} (erlaubt: {', '.join(VALID_APPROVAL_PROFILES)})"
        )
    target = path or security_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.parent.chmod(0o700)
    except OSError:
        pass
    tmp = target.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {
                "approval_profile": cfg.approval_profile,
                "sandbox_enabled": cfg.sandbox_enabled,
                "ask_categories": list(cfg.ask_categories),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    tmp.replace(target)
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return cfg


# R23: session remember (profiles "session" and "full")
# Process-wide: session_id → set of remembered tools/heads. Deliberately NOT
# persisted — after a restart it asks again (the conservative
# default trust boundary).

_session_approved: dict[str, set[str]] = {}
# B-7 (full audit 2026-09-18): a second switch for run_shell alone — the
# type-remember does not suffice here; what gets remembered is the segment HEAD
# of each released command ('git', 'npx', …). Same pattern = no dialog.
_session_shell_heads: dict[str, set[str]] = {}


def _profile_remembers(profile: str | None) -> bool:
    p = profile if profile is not None else load_security_config().approval_profile
    return p in ("session", "full")


def session_auto_approved(session_id: str | None, tool: str, profile: str | None = None) -> bool:
    """True when this tool was already remembered for this session.

    Gates: approval_profile must be "session"/"full", session_id must
    exist, and run_shell (NEVER_REMEMBER) is never freed by a type
    remember — the head memo covers it (shell_head_auto_approved).
    """
    if not _profile_remembers(profile):
        return False
    if not session_id or tool in NEVER_REMEMBER:
        return False
    return tool in _session_approved.get(session_id, set())


def shell_head_auto_approved(
    session_id: str | None, heads: list[str] | None, profile: str | None = None
) -> bool:
    """True when every segment head of the command is remembered for the session."""
    if not _profile_remembers(profile):
        return False
    if not session_id or not heads:
        return False
    known = _session_shell_heads.get(session_id, set())
    return all(head in known for head in heads)


def remember_shell_heads(session_id: str | None, heads: list[str] | None) -> None:
    """Remembers the segment heads of a released shell command for the session."""
    if not session_id or not heads:
        return
    _session_shell_heads.setdefault(session_id, set()).update(heads)


def remember_tool(session_id: str | None, tool: str) -> None:
    """Remembers a tool for the session — unless it is listed in NEVER_REMEMBER."""
    if not session_id or tool in NEVER_REMEMBER:
        return
    _session_approved.setdefault(session_id, set()).add(tool)


def clear_session_approvals(session_id: str | None = None) -> None:
    """Test/revoke helper: drop session approvals (the revoke UI follows in R24)."""
    if session_id is None:
        _session_approved.clear()
        _session_shell_heads.clear()
    else:
        _session_approved.pop(session_id, None)
        _session_shell_heads.pop(session_id, None)
