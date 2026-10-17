"""Every coded refusal answers in English and carries a code both bundles answer.

Measured by driving the running product (2026-10-11): an empty upload answered 422 with a
German sentence and `app/src/lib/api/http.ts` put it in front of a reader who had asked for the
English interface. The fix is the pairing this pins — the route states a stable reason code and an
English fallback, the two bundles hold the sentence in each language, and the client answers from
the bundle when it knows the code. A code with no key, a key with no reader, and a "translation"
that repeats the English are all failures here, because each one has already shipped once.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.refusals import REASONS, Refused

ROOT = Path(__file__).resolve().parents[1]

#: what the route answers when the reader's bundle has no entry for the code
SERVER_SENTENCES = {
    "audio_empty": (
        "Empty audio file — record the message again or attach a file that carries audio."
    ),
    "audio_model_download_required": (
        "Transcription needs the local speech model 'tiny' (~78 MB from huggingface.co) and it "
        "is not on this machine yet — set EPHE_STT_DOWNLOAD=1 (with EPHE_OFFLINE unset), or "
        "set stt_allow_download in voice.json, then send the recording again."
    ),
    "audio_model_fetch_failed": (
        "The speech model 'tiny' (~78 MB from huggingface.co) could not be fetched — check the "
        "connection, then send the recording again."
    ),
    "tts_failed": (
        "Speech synthesis failed: boom. Try again; if it stays, check the audio engine "
        "under Settings - Audio."
    ),
    "proxy_port_out_of_range": (
        "port 1 is outside the preview range 1024..65535 — pick a port in that range "
        "(privileged services sit below it)."
    ),
    "proxy_port_is_service": (
        "port 6379 is redis, not a dev server — allow it for the preview explicitly "
        "with EPHE_PROXY_PORTS=6379"
    ),
    "vision_failed": (
        "Image analysis failed: boom. Try again; if it stays, check the active engine "
        "under Settings - Engine."
    ),
    "settings_register_unwritable": (
        "settings.json could not be written — check that the file is writable, then save again."
    ),
    "audit_log_unreadable": (
        "The audit log exists but cannot be read — check the file's permissions, then "
        "reload the view."
    ),
    # The workspaces routes (2026-10-14). The six whose sentence is the module's own text carry
    # it whole in the `reason` slot and are framed beside it — the module says what happened,
    # the template adds the move the reader still has, so the fallback is that pairing and no
    # longer the bare reason.
    "workspace_id_required": (
        "a workspace_id is required — pass your project folder from Settings - Engine"
    ),
    "workspace_unknown": (
        "workspace 'alpha' is neither a register id nor a directory "
        "— pick your folder in Settings - Engine"
    ),
    "workspace_not_live": "workspace 'alpha' is not live — pick a live tree on the Workspaces page",
    "change_set_unknown": "change set 'cs-1' is not in the store — check it on the Workspaces page",
    "change_set_no_author": (
        "change set 'cs-1' names no author in its provenance "
        "— record it again with an author named"
    ),
    "change_set_tree_gone": (
        "the workspace directory is gone — record the set again from a live tree"
    ),
    "workspace_create_refused": (
        "git worktree add failed for owner 'agent-a' on base 'no-such-ref'; row 4f2a1c0d is "
        "marked discarded for the reaper — check the base branch and retry"
    ),
    "workspace_remove_refused": (
        "git kept /tmp/wt; take it down with force=True — retry with force=True"
    ),
    "change_set_build_refused": (
        "provenance needs a non-empty why — check what it names and record it again"
    ),
    "review_refused": (
        "a reason needs a why for README.md:1 — check the reviewer and the reasons, then retry"
    ),
    "agent_limit_reached": "agent-limit: 2 agents running, cap 1 — reduce the wave, then retry",
    "publish_without_approval": (
        "change set 'cs-1' carries no approval from a reviewer other than its author "
        "— ask another reviewer on the Workspaces page"
    ),
    "publish_tree_moved": (
        "the tree moved after this set was recorded: README.md "
        "— record the set again and publish"
    ),
    "change_set_amend_refused": (
        "a published change set is final — record the set again from the live tree"
    ),
    "change_set_state_refused": (
        "a change set in draft does not move to draft — check the set's stage on the "
        "Workspaces page and move it with a verdict or a publish"
    ),
    "change_set_state_reserved": (
        "change set 'cs-1' is not set to 'published' by hand — record a verdict or publish it"
    ),
    "change_set_approval_superseded": (
        "change set 'cs-1' carries an approval filed against bytes an amend replaced "
        "— record a fresh verdict on it as it now stands, then publish on that"
    ),
    "change_set_unpublish_refused": (
        "a change set in draft has no landing to take back "
        "— check the set's stage on the Workspaces page"
    ),
    "publish_path_claimed": (
        "README.md is held by agent-b (draft since 2026-10-14T16:05) "
        "— check that run on the Workspaces page, then publish with force=True to write over it"
    ),
}

#: the slots each template fills, and therefore the keys `reason_params` has to carry
PARAMS = {
    "audio_empty": {},
    "audio_model_download_required": {"model": "tiny", "size_mb": 78, "host": "huggingface.co"},
    "audio_model_fetch_failed": {"model": "tiny", "size_mb": 78, "host": "huggingface.co"},
    "tts_failed": {"error": "boom"},
    "proxy_port_out_of_range": {"port": 1, "min_port": 1024, "max_port": 65535},
    "proxy_port_is_service": {"port": 6379, "service": "redis", "env": "EPHE_PROXY_PORTS"},
    "vision_failed": {"error": "boom"},
    "settings_register_unwritable": {},
    "audit_log_unreadable": {},
    "workspace_id_required": {},
    "workspace_unknown": {"workspace": "alpha"},
    "workspace_not_live": {"workspace": "alpha"},
    "change_set_unknown": {"change_set": "cs-1"},
    "change_set_no_author": {"change_set": "cs-1"},
    "change_set_tree_gone": {"reason": "the workspace directory is gone"},
    "workspace_create_refused": {
        "reason": (
            "git worktree add failed for owner 'agent-a' on base 'no-such-ref'; "
            "row 4f2a1c0d is marked discarded for the reaper"
        )
    },
    "workspace_remove_refused": {"reason": "git kept /tmp/wt; take it down with force=True"},
    "change_set_build_refused": {"reason": "provenance needs a non-empty why"},
    "review_refused": {"reason": "a reason needs a why for README.md:1"},
    "agent_limit_reached": {"reason": "agent-limit: 2 agents running, cap 1"},
    "publish_without_approval": {"change_set": "cs-1"},
    "publish_tree_moved": {"paths": "README.md"},
    "change_set_amend_refused": {"reason": "a published change set is final"},
    "change_set_state_refused": {"reason": "a change set in draft does not move to draft"},
    "change_set_state_reserved": {"change_set": "cs-1", "state": "published"},
    "change_set_approval_superseded": {"change_set": "cs-1"},
    "change_set_unpublish_refused": {"reason": "a change set in draft has no landing to take back"},
    "publish_path_claimed": {
        "paths": "README.md",
        "holders": "agent-b (draft since 2026-10-14T16:05)",
    },
}

#: the status each route answered with before the code existed, and still answers with
STATUSES = {
    "audio_empty": 422,
    "audio_model_download_required": 409,
    "audio_model_fetch_failed": 503,
    "tts_failed": 500,
    "proxy_port_out_of_range": 400,
    "proxy_port_is_service": 400,
    "vision_failed": 500,
    "settings_register_unwritable": 500,
    "audit_log_unreadable": 500,
    "workspace_id_required": 422,
    "workspace_unknown": 404,
    "workspace_not_live": 404,
    "change_set_unknown": 404,
    "change_set_no_author": 422,
    "change_set_tree_gone": 409,
    "workspace_create_refused": 409,
    "workspace_remove_refused": 409,
    "change_set_build_refused": 422,
    "review_refused": 422,
    "agent_limit_reached": 429,
    "publish_without_approval": 409,
    "publish_tree_moved": 409,
    "change_set_amend_refused": 409,
    "change_set_state_refused": 422,
    "change_set_state_reserved": 409,
    "change_set_approval_superseded": 409,
    "change_set_unpublish_refused": 409,
    "publish_path_claimed": 409,
}


def _bundle(name: str) -> dict:
    return json.loads((ROOT / "app" / "src" / "locales" / name).read_text(encoding="utf-8"))


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-zäöüß]{4,}", text.lower())}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import os

    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "profile.json"))
    os.environ.pop("EPHE_SETUP_MODE", None)
    from server.main import create_app

    return TestClient(create_app())


def test_every_coded_refusal_renders_the_english_fallback():
    assert set(SERVER_SENTENCES) == set(REASONS), "a code was added or dropped without this table"
    for code, expected in SERVER_SENTENCES.items():
        assert Refused(code, **PARAMS[code]).message == expected, code


def test_the_registry_holds_the_status_the_route_answered_before():
    assert {code: status for code, (status, _) in REASONS.items()} == STATUSES


def test_a_code_is_a_stable_identifier_and_never_a_sentence():
    for code in REASONS:
        assert re.fullmatch(r"[a-z][a-z0-9_]*", code), code


def test_an_uncoded_refusal_is_a_bug_caught_at_the_raise():
    with pytest.raises(KeyError, match="uncoded refusal"):
        Refused("audio_empty_but_typed_wrong")


def test_the_running_route_answers_with_the_code_beside_the_message(client):
    """A request through the running app, which is the shape the client actually parses."""
    response = client.post(
        "/api/audio/transcribe",
        files={"file": ("voice.webm", b"", "audio/webm")},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["reason_code"] == "audio_empty"
    assert error["message"] == SERVER_SENTENCES["audio_empty"]
    assert error["code"] == "validation_error", "the transport code the envelope already carried"


def test_a_refusal_with_slots_sends_its_params_so_the_surface_can_fill_its_own_words(client):
    response = client.get("/api/proxy/6379/")
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["reason_code"] == "proxy_port_is_service"
    assert error["reason_params"] == {"port": 6379, "service": "redis", "env": "EPHE_PROXY_PORTS"}


def test_every_code_has_a_key_in_both_bundles():
    """The pair the last two waves broke: a code no bundle answers, or a key no client reads."""
    for name in ("de.json", "en.json"):
        bundle = _bundle(name)["serverError"]
        for code in REASONS:
            assert code in bundle, f"{name} has no serverError.{code}"
            assert bundle[code].strip(), f"{name} carries an empty serverError.{code}"


def test_the_slots_survive_the_translation():
    """A bundle entry that dropped `{{port}}` cannot be filled and reads as a broken sentence."""
    for code, (status, template) in REASONS.items():
        slots = set(re.findall(r"{(\w+)}", template))
        for name in ("de.json", "en.json"):
            entry = _bundle(name)["serverError"][code]
            assert set(re.findall(r"{{(\w+)}}", entry)) == slots, f"{name}:{code} (status {status})"


def test_the_german_answer_is_a_translation_and_not_the_english_one():
    de, en = _bundle("de.json")["serverError"], _bundle("en.json")["serverError"]
    assert set(de) == set(en)
    for code in REASONS:
        assert de[code] != en[code], code
        assert _words(de[code]) - _words(en[code]), f"{code} adds no German word to the reader's text"


def test_the_registry_is_the_only_place_a_reason_is_born():
    """A second table of the same codes would let the two sinks drift apart unnoticed."""
    assert len(set(REASONS)) == len(REASONS)


#: the two sentences the chat stream can end a mute turn with — same rule as the HTTP codes:
#: English in code, the reader's language in the bundle, a stable code on the frame
STREAM_CODES = ("silent_engine_turn", "silent_after_tools_turn")


def test_the_stream_family_carries_its_codes_in_both_bundles_too():
    """The frame and the route are two sinks of one class; a gate over one leaves the other open."""
    from server.routes.chat import SILENT_TURN_CODES

    assert set(SILENT_TURN_CODES.values()) == set(STREAM_CODES)
    for name in ("de.json", "en.json"):
        bundle = _bundle(name)["serverError"]
        for code in STREAM_CODES:
            assert bundle.get(code, "").strip(), f"{name} has no serverError.{code}"

    de, en = _bundle("de.json")["serverError"], _bundle("en.json")["serverError"]
    for code in STREAM_CODES:
        assert _words(de[code]) - _words(en[code]), f"{code} is not translated, only copied"


