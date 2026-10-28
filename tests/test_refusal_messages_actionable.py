"""Every coded refusal leaves the reader a move, in the language they set.

The class this pins (driving the product, 2026-10-11): a gate refused with a code and a
statement of what did not happen — "Empty audio file.", "settings.json could not be written",
"[TOOL-DENIED] write_file was not executed." — and stopped. A refusal that names no next step
is half an answer: it costs the reader the round trip back to the surface to find out what to
do. The product refuses through four families — the HTTP routes (`server.refusals.REASONS`),
the chat approval gate (`core.tools.chat_gate`), the engine router
(`core.model_router.ROUTER_REFUSAL_TEXT`) and the silent chat stream
(`server.routes.chat.SILENT_TURN_CODES`) — and every code in each carries a next step, in
English in code and in the reader's bundle beside it.

The check is a marker set, not a matcher for one sentence: the wording stays free, the presence
of a move does not. A family emptied by a rename fails the same way a dead end does.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: a next step opens on one of these moves, or names where to go. `again`/`erneut` catch a
#: retry; a surface name or an environment assignment is a step all by itself.
NEXT_STEP_EN = re.compile(
    r"\b(try|retry|again|record|attach|check|enable|disable|choose|pick|select|set|run|"
    r"install|use|add|open|reload|save|allow|configure|enter|click|reduce)\b",
    re.IGNORECASE,
)
NEXT_STEP_DE = re.compile(
    r"\b(versuch|erneut|noch einmal|nimm|wähle|prüfe|aktiviere|deaktiviere|setze|starte|"
    r"installiere|nutze|öffne|lade|speichere|freigeben|reduziere|trage|klicke|gib)\b",
    re.IGNORECASE,
)
SURFACE_EN = re.compile(r"\bSettings\b")
SURFACE_DE = re.compile(r"\bEinstellungen\b")
ENV_ASSIGNMENT = re.compile(r"\b[A-Z][A-Z0-9_]{2,}=")

#: the slots each HTTP template fills (the same values `test_server_refusal_codes` uses)
HTTP_PARAMS = {
    "self_sign_forbidden": {},
    "audio_empty": {},
    "audio_model_download_required": {"model": "tiny", "size_mb": 78, "host": "huggingface.co"},
    "audio_model_fetch_failed": {"model": "tiny", "size_mb": 78, "host": "huggingface.co"},
    "tts_failed": {"error": "boom"},
    "proxy_port_out_of_range": {"port": 1, "min_port": 1024, "max_port": 65535},
    "proxy_port_is_service": {"port": 6379, "service": "redis", "env": "EPHE_PROXY_PORTS"},
    "vision_failed": {"error": "boom"},
    "settings_register_unwritable": {},
    "audit_log_unreadable": {},
    # The workspaces routes' fourteen raise sites, added 2026-10-14 with the reason-code wave:
    # this table is a completeness guard, so a new code that forgets its parameters fails here.
    "workspace_id_required": {},
    "workspace_unknown": {"workspace": "abc123"},
    "workspace_not_live": {"workspace": "abc123"},
    "change_set_unknown": {"change_set": "cs-1"},
    "change_set_no_author": {"change_set": "cs-1"},
    "change_set_tree_gone": {"reason": "the tree is gone"},
    "workspace_create_refused": {"reason": "no branch could be made"},
    "workspace_remove_refused": {"reason": "the tree carries local changes"},
    "change_set_build_refused": {"reason": "the worktree has no changes"},
    "review_refused": {"reason": "a reviewer cannot approve their own set"},
    "agent_limit_reached": {"reason": "agents is at its bound"},
    "publish_without_approval": {"change_set": "cs-1"},
    "publish_tree_moved": {"paths": "a.txt, b.txt"},
    "change_set_amend_refused": {"reason": "a published change set is final"},
    "change_set_state_refused": {"reason": "a change set in draft does not move to draft"},
    "change_set_state_reserved": {"change_set": "cs-1", "state": "published"},
    "change_set_approval_superseded": {"change_set": "cs-1"},
    "change_set_unpublish_refused": {"reason": "a change set in draft has no landing to take back"},
    "publish_path_claimed": {
        "paths": "a.txt",
        "holders": "agent-b (draft since 2026-10-14T16:05)",
    },
}

DENIAL_PARAMS = {
    "no_approval_channel": {},
    "not_approved_by_user": {},
    "approval_channel_failed": {"error": "RuntimeError"},
    "not_approved": {},
    "mode_read_only": {},
    "mode_no_tools": {},
    "secret_path_denied": {"path": "~/.ssh/id_rsa"},
}

#: per bundle: the directive set and the surface name to look for
LANGS = {
    "en.json": (NEXT_STEP_EN, SURFACE_EN),
    "de.json": (NEXT_STEP_DE, SURFACE_DE),
}


def _bundle(name: str) -> dict:
    return json.loads((ROOT / "app" / "src" / "locales" / name).read_text(encoding="utf-8"))


def _names_a_next_step(text: str, directives: re.Pattern, surface: re.Pattern) -> bool:
    return bool(directives.search(text) or surface.search(text) or ENV_ASSIGNMENT.search(text))


def test_every_http_refusal_names_a_next_step_in_its_english_fallback():
    from server.refusals import REASONS, Refused

    assert REASONS, "the HTTP refusal registry is gone"
    for code in REASONS:
        message = Refused(code, **HTTP_PARAMS[code]).message
        assert _names_a_next_step(message, NEXT_STEP_EN, SURFACE_EN), (code, message)


@pytest.mark.parametrize("lang", sorted(LANGS))
def test_every_http_refusal_names_a_next_step_in_the_reader_bundle(lang):
    from server.refusals import REASONS

    directives, surface = LANGS[lang]
    bundle = _bundle(lang)["serverError"]
    for code in REASONS:
        assert code in bundle, f"{lang} lost serverError.{code}"
        assert _names_a_next_step(bundle[code], directives, surface), (lang, code, bundle[code])


def test_every_chat_gate_denial_names_a_next_step():
    from core.tools.chat_gate import DENIAL_REASONS, denial_message

    assert DENIAL_REASONS, "the chat gate carries no coded denial"
    for code in DENIAL_REASONS:
        denial = str(denial_message("write_file", code, **DENIAL_PARAMS[code]))
        assert _names_a_next_step(denial, NEXT_STEP_EN, SURFACE_EN), (code, denial)


def test_the_router_refusal_names_a_next_step():
    from core.model_router import ROUTER_REFUSAL_TEXT

    assert _names_a_next_step(ROUTER_REFUSAL_TEXT, NEXT_STEP_EN, SURFACE_EN), ROUTER_REFUSAL_TEXT


@pytest.mark.parametrize("lang", sorted(LANGS))
def test_every_stream_refusal_names_a_next_step_in_the_reader_bundle(lang):
    from server.routes.chat import SILENT_TURN_CODES

    codes = set(SILENT_TURN_CODES.values())
    assert codes, "the silent stream carries no coded refusal"
    directives, surface = LANGS[lang]
    bundle = _bundle(lang)["serverError"]
    for code in codes:
        entry = bundle.get(code, "")
        assert entry.strip(), f"{lang} has no serverError.{code}"
        assert _names_a_next_step(entry, directives, surface), (lang, code, entry)


def test_the_router_and_stream_codes_are_stable_identifiers():
    from core.model_router import ROUTER_REFUSAL_CODE
    from server.routes.chat import SILENT_TURN_CODES

    for code in (ROUTER_REFUSAL_CODE, *SILENT_TURN_CODES.values()):
        assert re.fullmatch(r"[a-z][a-z0-9_]*", code), code
