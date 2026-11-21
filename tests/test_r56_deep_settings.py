"""R56 — Deep settings (wave 6): deep schema, persistence, plugin visibility.

These tests check the register as I3-6 left it: only fields a consumer pulls through
the wire. What is checked:
1. core.settings_schema delivers SCHEMA/SECTIONS internally consistent (every field
   with type/default, numbers with min/max, selects with options).
2. normalize() clamps and types correctly, unknown keys pass straight through.
3. load/save roundtrip over EPHE_CONFIG_DIR (settings.json).
4. GET /api/settings appends 'deep' as a section list; POST sections
   validates (422 on a range violation) and persists.
5. Every register section has a title in both languages (otherwise the section
   names itself in the client after its own key).
6. A save of the embedding-model switch hands the running process the model it names.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.test_r58_register_vertrag import SECTION_KEYS  # noqa: E402
from core.settings_schema import (  # noqa: E402
    SECTIONS,
    SCHEMA,
    load_deep_settings,
    normalize_deep,
    save_deep_settings,
    validate_sections,
)


# 1. Schema completeness

def test_schema_carries_every_contract_section():
    """The yardstick is the contract's section list (test_r58), not a
    second copy here — otherwise I6-4 had to be caught up in two places at once."""
    keys = {s["key"] for s in SECTIONS}
    assert keys == SECTION_KEYS
    # safety (double approval button), engine/browser/voice/delegation/moa/
    # skills/time/kanban/notifications: dropped, because no consumer reads them.
    # 'memory' was one of them and has not been since I6-7 — the section now has
    # five fields that core/auto_memory.py and core/memory.py read under the full
    # key, which is exactly what it was missing back then.
    for removed in ("safety", "engine", "browser", "voice", "delegation",
                "moa", "skills", "zeit", "kanban", "notifications"):
        assert removed not in keys, removed
    for s in SECTIONS:
        assert s["fields"], s["key"]


def test_every_field_has_a_type_and_default():
    for fkey, meta in SCHEMA.items():
        assert "type" in meta and "default" in meta, fkey
        assert meta["type"] in ("bool", "number", "select", "text"), fkey
        if meta["type"] == "select":
            assert isinstance(meta["options"], list) and meta["options"], fkey
            assert meta["default"] in meta["options"], fkey
        if meta["type"] == "number":
            assert "min" in meta and "max" in meta, fkey
            assert meta["min"] <= meta["default"] <= meta["max"], fkey


def test_field_keys_carry_their_section_prefix():
    # Every field key starts with the section prefix.
    section_keys = {s["key"] for s in SECTIONS}
    for fkey in SCHEMA:
        head = fkey.split(".", 1)[0]
        assert head in section_keys, fkey


# 2. normalize: clamping, types, unknown keys

def test_normalize_clamps_numbers_and_forces_defaults():
    out = normalize_deep({"appearance": {"appearance.font_scale": 9999},
                          "chat": {"chat.details_mode": "wild"}})
    assert out["appearance"]["appearance.font_scale"] == 150      # upper bound
    assert out["chat"]["chat.details_mode"] == "expanded"         # invalid -> default


def test_normalize_coerces_bools_and_text():
    out = normalize_deep({
        "appearance": {"appearance.animations_enabled": "true",
                       "appearance.update_check": "nein"},
        "unknown-section": {"x.y": 1},
    })
    assert out["appearance"]["appearance.animations_enabled"] is True
    assert out["appearance"]["appearance.update_check"] is False
    assert "unknown-section" not in out


def test_normalize_drops_unknown_fields_of_a_section():
    out = normalize_deep({"chat": {"chat.nicht_vorhanden": 5}})
    assert "chat.nicht_vorhanden" not in out["chat"]
    # known fields stay at their default
    assert out["chat"]["chat.show_reasoning"] is True


# 3. Persistence roundtrip

def test_roundtrip_through_the_config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    payload = normalize_deep({"advanced": {"advanced.api_timeout": 300},
                             "chat": {"chat.details_mode": "collapsed"}})
    assert save_deep_settings(payload) is True
    back = load_deep_settings()
    assert back["advanced"]["advanced.api_timeout"] == 300
    assert back["chat"]["chat.details_mode"] == "collapsed"
    # the file really lands in the config folder
    assert (tmp_path / "settings.json").is_file()


def test_loading_without_a_file_yields_only_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    loaded = load_deep_settings()
    assert loaded == {}  # empty file => only defaults in the endpoint
    merged = normalize_deep(loaded)
    assert merged == {}
    # defaults only appear through the merge in deep_view
    from core.settings_schema import deep_defaults
    assert deep_defaults()["plugins"]["plugins.plugin_signature_check"] is True


# 4. API: GET/POST /api/settings deep block

def _client():
    from fastapi.testclient import TestClient
    from server.main import app
    return TestClient(app)


def test_get_settings_attaches_deep_as_a_section_list(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    client = _client()
    body = client.get("/api/settings").json()
    assert "deep" in body
    sec_keys = {s["key"] for s in body["deep"]}
    assert sec_keys == SECTION_KEYS
    chat = next(s for s in body["deep"] if s["key"] == "chat")
    reasoning = next(f for f in chat["fields"] if f["key"] == "chat.show_reasoning")
    assert reasoning["value"] is True and reasoning["type"] == "bool"


def test_post_sections_validates_and_persists(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    client = _client()
    res = client.post("/api/settings", json={
        "sections": {"plugins": {"plugins.plugin_autorun": True}},
    })
    assert res.status_code == 200
    assert (tmp_path / "settings.json").is_file()
    body = client.get("/api/settings").json()
    plugins = next(s for s in body["deep"] if s["key"] == "plugins")
    autorun = next(f for f in plugins["fields"] if f["key"] == "plugins.plugin_autorun")
    assert autorun["value"] is True


def test_post_sections_rejects_a_range_breach_with_422(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    client = _client()
    res = client.post("/api/settings", json={
        "sections": {"advanced": {"advanced.api_timeout": -5}},
    })
    assert res.status_code == 422


# 5. Every register section has a title in both languages

def test_every_section_has_a_title_in_both_languages():
    """The nav block used to show a copied section list; the order
    now comes from the server alone. What the client needs is the title — without
    it `t(..., {defaultValue: sec.key})` silently falls back to 'appearance',
    and the section is suddenly named after its own key."""
    titles = {}
    for lang in ("de", "en"):
        raw = json.loads(
            (ROOT / "app" / "src" / "locales" / f"{lang}.json").read_text(encoding="utf-8")
        )
        titles[lang] = {
            k.split("deepSection.", 1)[1]
            for k in raw["settings"]
            if k.startswith("deepSection.")
        }
    declared = {s["key"] for s in SECTIONS}
    for lang in ("de", "en"):
        fehlend = sorted(declared - titles[lang])
        assert not fehlend, f"{lang}: Sektionstitel fehlen: {fehlend}"
        orphans = sorted(titles[lang] - declared)
        assert not orphans, f"{lang}: Titel ohne Sektion (alt): {orphans}"


def test_the_plugins_route_serves_the_catalog():
    client = _client()
    body = client.get("/api/plugins").json()
    assert "public" in body and "personal" in body
    ids = {p["id"] for p in body["public"]}
    assert "web/crawl4ai" in ids or len(ids) >= 1


# 6. POST merges: a write carries the fields it did not send (QD-008, F1)

def _non_default(field_key: str):
    """A value the schema accepts that differs from the field's default."""
    meta = SCHEMA[field_key]
    if meta["type"] == "bool":
        return not meta["default"]
    if meta["type"] == "select":
        others = [o for o in meta["options"] if o != meta["default"]]
        return others[0] if others else meta["default"]
    if meta["type"] == "number":
        return meta["min"] if meta["default"] != meta["min"] else meta["max"]
    return f"{meta['default']}-kept"


def test_a_partial_section_write_keeps_every_field_it_did_not_send(tmp_path, monkeypatch):
    """One field in, twelve kept: the write merges into the stored section.

    Measured before the fix: the omitted fields fell back to their defaults and
    whole sections vanished, while the answer stayed 200.
    """
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    client = _client()
    appearance = [s for s in SECTIONS if s["key"] == "appearance"][0]["fields"]
    memory = [s for s in SECTIONS if s["key"] == "memory"][0]["fields"]
    seeded = {k: _non_default(k) for k in appearance[:3]}
    seeded_memory = {memory[0]: _non_default(memory[0])}

    first = client.post("/api/settings", json={
        "sections": {"appearance": seeded, "memory": seeded_memory},
    })
    assert first.status_code == 200

    touched = next(k for k in appearance if k not in seeded)
    second = client.post("/api/settings", json={"sections": {"appearance": {touched: _non_default(touched)}}})
    assert second.status_code == 200

    stored = json.loads((tmp_path / "settings.json").read_text())["sections"]
    for key, value in seeded.items():
        assert stored["appearance"].get(key) == value, f"{key} was dropped by a partial write"
    assert stored["appearance"][touched] == _non_default(touched)
    assert stored.get("memory", {}).get(memory[0]) == seeded_memory[memory[0]], "a write dropped another section"


def test_an_unknown_field_key_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    res = _client().post("/api/settings", json={
        "sections": {"appearance": {"appearance.zzz_bogus_key": "x"}},
    })
    assert res.status_code == 400, res.text


def test_an_unknown_section_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    res = _client().post("/api/settings", json={"sections": {"nonsense": {"nonsense.key": 1}}})
    assert res.status_code == 400, res.text


# 6. The embedder switch hands the running process the model it names

def _sentinel_embedders(monkeypatch):
    """The two graphs as sentinels plus a count of how often each was loaded.

    Loading either artifact in a test is the wrong layer, and the claim under test is about
    which one the process serves after a save. `model_present` and its two companions are
    patched so the gemma label resolves on a machine that never fetched the 540 MB graph.
    """
    from core import memory_embed
    import core.memory_embed_gemma as gemma_module

    loads = {"gemma": 0, "minilm": 0}

    def gemma():
        loads["gemma"] += 1
        return ("gemma", loads["gemma"])

    def minilm():
        loads["minilm"] += 1
        return ("minilm", loads["minilm"])

    monkeypatch.delenv(memory_embed.ENV_DISABLE, raising=False)
    monkeypatch.setattr(memory_embed, "_CACHE", {})
    monkeypatch.setattr(memory_embed, "_build_gemma", gemma)
    monkeypatch.setattr(memory_embed, "_build_minilm", minilm)
    monkeypatch.setattr(gemma_module, "model_present", lambda: True)
    monkeypatch.setattr(gemma_module, "download_consent", lambda: True)
    monkeypatch.setattr(gemma_module, "offline", lambda: False)
    return loads


def test_saving_the_embedder_hands_the_process_the_other_model(tmp_path, monkeypatch):
    """The register promises the switch applies from the next stored entry on.

    `core/memory_embed.py` caches the loaded graph for the process while the label written
    into `chunks.embedding_model` is read per write, so a save that did not hand over
    stamped the next entry with the new model's name and had the old model compute it.
    """
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    from core import memory_embed

    loads = _sentinel_embedders(monkeypatch)
    assert save_deep_settings(validate_sections({"memory": {"memory.embedder": "all-MiniLM-L6-v2"}}))
    assert memory_embed.get_embedder()[0] == "minilm"

    res = _client().post("/api/settings", json={
        "sections": {"memory": {"memory.embedder": "embeddinggemma-2"}},
    })
    assert res.status_code == 200

    assert memory_embed.get_embedder()[0] == "gemma", "the register saved, the process kept the old graph"
    assert memory_embed.model_name() == memory_embed.GEMMA_LABEL
    assert loads == {"gemma": 1, "minilm": 1}


def test_a_save_that_cannot_change_the_model_keeps_the_loaded_graph(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    from core import memory_embed

    loads = _sentinel_embedders(monkeypatch)
    assert save_deep_settings(validate_sections({"memory": {"memory.embedder": "all-MiniLM-L6-v2"}}))
    loaded = memory_embed.get_embedder()

    res = _client().post("/api/settings", json={
        "sections": {"chat": {"chat.show_reasoning": False}},
    })
    assert res.status_code == 200

    assert memory_embed.get_embedder() is loaded, "an unrelated save dropped a loaded graph"
    assert loads == {"gemma": 0, "minilm": 1}


def test_saving_the_same_embedder_again_keeps_the_loaded_graph(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    from core import memory_embed

    loads = _sentinel_embedders(monkeypatch)
    assert save_deep_settings(validate_sections({"memory": {"memory.embedder": "all-MiniLM-L6-v2"}}))
    loaded = memory_embed.get_embedder()

    res = _client().post("/api/settings", json={
        "sections": {"memory": {"memory.embedder": "all-MiniLM-L6-v2"}},
    })
    assert res.status_code == 200

    assert memory_embed.get_embedder() is loaded, "the same value reopened a model that was already loaded"
    assert loads == {"gemma": 0, "minilm": 1}
