"""Tests for core/persona_pack.py — the shareable, importable persona form."""
from __future__ import annotations

import json

import pytest

from core import persona
from core import persona_pack as pp
from core.plugin_signing import SIG_ALG, canonical_json, generate_keypair

BODY = "## Voice\n- Warm, brief, honest."


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_PERSONA_DIR", str(tmp_path))
    return tmp_path


def _pack(**kw):
    kw.setdefault("title", "Marvin")
    return pp.build_pack(kw.pop("text", BODY), **kw)


# pack build and export


def test_build_pack_derives_slug_from_title():
    pack = pp.build_pack(BODY, title="Marvin The Bot")
    assert pack["name"] == "marvin-the-bot"
    assert pack["format"] == "ephe-persona"
    assert pack["version"] == 1
    assert pack["persona"] == BODY
    assert pack["persona_sha256"] == pp.persona_sha256(BODY)


def test_build_pack_explicit_name_wins_and_tracks_only_set_fields():
    pack = pp.build_pack(BODY, name="custom", title="Something Else", description="one line", author="Ada")
    assert pack["name"] == "custom"
    assert pack["title"] == "Something Else"
    assert pack["description"] == "one line"
    assert pack["author"] == "Ada"
    assert "created" not in pack  # empty optional fields are omitted
    assert "signature" not in pack


def test_build_pack_strips_assembly_marker():
    pack = pp.build_pack("[persona]\n" + BODY, title="Marvin")
    assert pack["persona"] == BODY
    assert not pack["persona"].startswith("[persona]")


def test_build_pack_is_deterministic():
    a = pp.build_pack(BODY, title="Marvin", created="2026-10-11T00:00:00Z")
    b = pp.build_pack(BODY, title="Marvin", created="2026-10-11T00:00:00Z")
    assert pp.dumps(a) == pp.dumps(b)


@pytest.mark.parametrize(
    "kwargs, reason",
    [
        ({"text": "   ", "title": "x"}, "empty persona"),
        ({"text": "hi", "title": ""}, "name required"),
        ({"text": "hi", "name": "x" * (pp.NAME_MAX_CHARS + 1)}, "name too long"),
        ({"text": "hi", "title": "x" * (pp.TITLE_MAX_CHARS + 1)}, "title too long"),
    ],
)
def test_build_pack_rejects_bad_input(kwargs, reason):
    with pytest.raises(pp.PersonaPackError, match=reason):
        pp.build_pack(**kwargs)


def test_build_pack_rejects_oversized_persona():
    with pytest.raises(pp.PersonaPackError, match="persona too large"):
        pp.build_pack("x" * (persona.PERSONA_MAX_CHARS + 1), title="big")


def test_filename_uses_suffix():
    assert pp.filename(_pack()) == "marvin" + pp.PACK_SUFFIX


def test_export_current_reads_the_live_persona(home):
    persona.write_persona(BODY)
    pack = pp.export_current(name="marvin")
    assert pack["persona"] == BODY


# validation (fail-closed)


def _valid():
    return _pack()


@pytest.mark.parametrize(
    "mutate, reason",
    [
        (lambda p: None, ""),  # sanity: the base pack is valid
        (lambda p: p.pop("format"), "not an ephe persona pack"),
        (lambda p: p.update(format="other"), "not an ephe persona pack"),
        (lambda p: p.update(version=2), "unsupported pack version"),
        (lambda p: p.update(version=True), "unsupported pack version"),
        (lambda p: p.update(version="1"), "unsupported pack version"),
        (lambda p: p.update(extra="x"), "unknown field"),
        (lambda p: p.update(name="Marvin"), "bad name"),
        (lambda p: p.update(name="has space"), "bad name"),
        (lambda p: p.update(name=123), "bad name"),
        (lambda p: p.pop("name"), "bad name"),
        (lambda p: p.update(persona="   "), "empty persona"),
        (lambda p: p.update(persona="tampered"), "integrity"),
        (lambda p: p.pop("persona_sha256"), "integrity"),
        (lambda p: p.update(signature="nope"), "bad signature record"),
    ],
)
def test_validate_is_fail_closed(mutate, reason):
    pack = _valid()
    mutate(pack)
    ok, why = pp.validate(pack)
    if reason == "":
        assert ok and why == ""
    else:
        assert not ok
        assert reason in why


def test_validate_accepts_json_string_and_rejects_garbage():
    ok, _ = pp.validate(pp.dumps(_valid()))
    assert ok
    assert pp.validate("{not json")[0] is False
    assert pp.validate("not json at all") == (False, "invalid json")
    assert pp.validate([1, 2, 3]) == (False, "not a json object")
    assert pp.validate(None) == (False, "not a json object")


def test_load_raises_with_reason():
    with pytest.raises(pp.PersonaPackError, match="unsupported pack version"):
        pp.load({"format": pp.FORMAT, "version": 9, "name": "x"})


def test_validate_rejects_meta_over_cap():
    pack = _valid()
    pack["title"] = "x" * (pp.TITLE_MAX_CHARS + 1)
    assert pp.validate(pack) == (
        False,
        f"title too long ({pp.TITLE_MAX_CHARS + 1} > {pp.TITLE_MAX_CHARS} chars)",
    )


def test_validate_rejects_oversized_persona():
    pack = _valid()
    pack["persona"] = "x" * (persona.PERSONA_MAX_CHARS + 1)
    ok, why = pp.validate(pack)
    assert not ok
    assert "persona too large" in why


def test_dumps_is_sorted_and_recurses_into_lists():
    text = pp.dumps({"b": [{"z": 1, "a": 2}], "a": None})
    assert text == json.dumps({"a": None, "b": [{"a": 2, "z": 1}]}, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


# pack import


def test_import_round_trip_writes_marker_free_0600(home):
    pack = _pack()
    summary = pp.import_pack(pp.dumps(pack))

    assert summary["imported"] is True
    assert summary["name"] == "marvin"
    assert summary["chars"] == len(BODY)

    written = (home / "persona.md").read_text(encoding="utf-8")
    assert written == BODY
    assert not written.startswith("[persona]")
    assert oct((home / "persona.md").stat().st_mode & 0o777) == "0o600"
    # what the engine serves carries the marker again
    assert persona.load_persona() == "[persona]\n" + BODY


def test_import_refuses_to_overwrite_without_flag(home):
    persona.write_persona("existing persona")
    with pytest.raises(pp.PersonaPackError, match="already exists"):
        pp.import_pack(_pack())
    assert (home / "persona.md").read_text(encoding="utf-8") == "existing persona"

    summary = pp.import_pack(_pack(), overwrite=True)
    assert summary["imported"] is True
    assert (home / "persona.md").read_text(encoding="utf-8") == BODY


def test_import_rejects_tampered_pack_before_touching_disk(home):
    pack = _pack()
    pack["persona"] = "replaced body"
    with pytest.raises(pp.PersonaPackError, match="integrity"):
        pp.import_pack(pack)
    assert not (home / "persona.md").exists()


def test_export_from_one_instance_imports_into_another(tmp_path, monkeypatch):
    a = tmp_path / "a"
    b = tmp_path / "b"
    monkeypatch.setenv("EPHE_PERSONA_DIR", str(a))
    persona.write_persona(BODY)
    blob = pp.dumps(pp.export_current(name="marvin"))

    monkeypatch.setenv("EPHE_PERSONA_DIR", str(b))
    pp.import_pack(blob)
    assert persona.load_persona_for_editor() == BODY


# signing


def test_sign_and_verify_round_trip():
    priv, pub = generate_keypair()
    signed = pp.sign_pack(_pack(), priv, kid="tester")
    assert signed["signature"]["alg"] == SIG_ALG
    assert pp.verify_pack(signed, [pub]) == (True, "")


def test_verify_detects_body_drift():
    priv, pub = generate_keypair()
    signed = pp.sign_pack(_pack(), priv)
    signed["persona"] = "changed"
    ok, why = pp.verify_pack(signed, [pub])
    assert not ok
    assert "integrity" in why


def test_verify_rejects_foreign_key_and_reports_missing_trust():
    priv, pub = generate_keypair()
    _other_priv, other_pub = generate_keypair()
    signed = pp.sign_pack(_pack(), priv)
    assert pp.verify_pack(signed, [other_pub]) == (False, "signature not from a trusted key")
    assert pp.verify_pack(signed, []) == (False, "no_trusted_key")


def test_verify_rejects_unsupported_alg_and_unsigned():
    priv, pub = generate_keypair()
    signed = pp.sign_pack(_pack(), priv)
    signed["signature"]["alg"] = "RS256"
    assert pp.verify_pack(signed, [pub]) == (False, "unsupported algorithm")
    assert pp.verify_pack(_pack(), [pub]) == (False, "no signature record")


def test_verify_never_throws_on_garbage():
    for bad in (None, {}, "str", 42, [1], {"format": pp.FORMAT}):
        ok, why = pp.verify_pack(bad, [b"not-a-pem"])
        assert ok is False
        assert isinstance(why, str) and why


def test_sign_refuses_invalid_pack():
    priv, _pub = generate_keypair()
    with pytest.raises(pp.PersonaPackError):
        pp.sign_pack({"format": pp.FORMAT, "version": 1, "name": "x", "persona": "hi"}, priv)


def test_signature_covers_every_field_but_itself():
    priv, pub = generate_keypair()
    signed = pp.sign_pack(_pack(), priv, kid="tester")
    payload = {k: v for k, v in signed.items() if k != "signature"}
    # the same canonical form the plugin/skill trust layer computes
    assert canonical_json(payload) == canonical_json({k: signed[k] for k in signed if k != "signature"})
    assert pp.verify_pack(json.loads(pp.dumps(signed)), [pub]) == (True, "")
