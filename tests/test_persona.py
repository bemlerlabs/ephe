"""R28 Agent Identity Core — persona as a file, generated identity block.

Reference-A/B pattern: the agent's identity is user-editable markdown that
survives every engine switch, NOT a hardcoded prompt. Ephe reads
`~/.ephe/persona.md` (accepting a Reference-B-style `SOUL.md` as fallback),
generates a factual identity block (incl. honest model disclosure) and builds
dynamic tool guidelines from the tool registry instead of a static list.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def persona_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect persona storage into the test tmp dir (lazy env read)."""
    monkeypatch.setenv("EPHE_PERSONA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import os

    os.environ["EPHE_MEMORY_DIR"] = os.environ["EPHE_MEMORY_DIR"] = str(tmp_path / "chroma_db")
    os.environ["EPHE_PROFILE_PATH"] = os.environ["EPHE_PROFILE_PATH"] = str(tmp_path / "user_profile.json")
    import core.engine_config as engine_config

    monkeypatch.setattr(engine_config, "CONFIG_DIR", tmp_path / "config")

    from fastapi.testclient import TestClient
    from server.main import create_app

    return TestClient(create_app())


class TestPersonaFile:
    def test_default_persona_is_created_on_first_use(self, persona_env):
        from core.persona import create_default_persona_if_missing, load_persona

        create_default_persona_if_missing()
        file = persona_env / "persona.md"
        assert file.exists()
        text = load_persona()
        # The default persona carries the R26 personality forward
        assert "warm" in text.lower()
        assert "Ephe" not in text  # identity lives in the generated block, not the persona
        # restrictive permissions like every config file
        assert (file.stat().st_mode & 0o777) == 0o600

    def test_creation_is_idempotent_and_never_overwrites(self, persona_env):
        from core.persona import create_default_persona_if_missing

        create_default_persona_if_missing()
        file = persona_env / "persona.md"
        file.write_text("My custom persona", encoding="utf-8")
        create_default_persona_if_missing()
        assert file.read_text(encoding="utf-8") == "My custom persona"

    def test_soul_md_is_accepted_as_fallback(self, persona_env):
        from core.persona import load_persona

        (persona_env / "SOUL.md").write_text("Referenz-B-style soul", encoding="utf-8")
        assert load_persona() == "[persona]\nReferenz-B-style soul"

    def test_corrupt_persona_falls_back_to_default(self, persona_env):
        from core.persona import create_default_persona_if_missing, load_persona

        create_default_persona_if_missing()
        (persona_env / "persona.md").write_text("x" * 10, encoding="utf-8")
        # unreadable bytes → honest fallback to the default, never a crash
        (persona_env / "persona.md").write_bytes(b"\xff\xfe\x00broken")
        text = load_persona()
        assert "warm" in text.lower()

    def test_persona_is_capped(self, persona_env):
        from core.persona import PERSONA_MAX_CHARS, load_persona

        (persona_env / "persona.md").write_text("a" * (PERSONA_MAX_CHARS + 5000), encoding="utf-8")
        # the persona CONTENT is capped (the [persona] marker adds a fixed prefix)
        assert len(load_persona()) <= PERSONA_MAX_CHARS + len("[persona]\n")

    def test_env_dir_is_read_lazily(self, tmp_path, monkeypatch):
        # The binding must NOT be baked at import time (engine_config lesson)
        from core import persona as persona_mod

        monkeypatch.setenv("EPHE_PERSONA_DIR", str(tmp_path))
        (tmp_path / "persona.md").write_text("lazy read works", encoding="utf-8")
        assert "lazy read works" in persona_mod.load_persona()


class TestIdentityBlock:
    def test_identity_names_ephe_and_discloses_model(self):
        from core.persona import build_identity_block

        block = build_identity_block("qwen3.8-flash-next")
        assert "Ephe" in block
        assert "qwen3.8-flash-next" in block
        assert "agent" in block.lower()
        # honest positioning: local, no cloud claims
        assert "locally" in block.lower()
        # the name rule survives engine switches
        assert "Ephe" in block and "regardless" in block.lower() or "never claim" in block.lower()

    def test_identity_never_hardcodes_a_model_name_as_identity(self):
        from core.persona import build_identity_block

        block = build_identity_block("deepseek-r1")
        assert "You are deepseek" not in block.lower()
        assert "You are qwen" not in block.lower()


class TestDynamicToolGuidelines:
    def test_guidelines_are_generated_from_the_registry(self):
        from core.persona import build_tool_guidelines

        text = build_tool_guidelines()
        assert "web_search" in text  # known tool
        assert "read_file" in text
        # security model is visible to the model itself
        assert "approval" in text.lower()

    def test_guidelines_split_safe_and_action_tools(self):
        from core.persona import build_tool_guidelines

        text = build_tool_guidelines()
        assert "read-only" in text.lower()
        assert "approval" in text.lower()


class TestSystemPromptAssembly:
    def test_assembly_order_identity_persona_skill_extra_profile(self):
        from core.chat import assemble_system_prompt

        prompt = assemble_system_prompt(
            model="test-model",
            incoming_system="[Skill prompt]",
            extra_system_prompt="[Extra]",
            profile_ctx="[Profile]",
            memory_ctx="[Memory]",
            corrections_ctx="[Corrections]",
            feedback_ctx="[Feedback]",
        )
        pos_identity = prompt.find("You are Ephe")
        pos_persona = prompt.find("[persona]")
        pos_skill = prompt.find("[Skill prompt]")
        pos_extra = prompt.find("[Extra]")
        pos_profile = prompt.find("[Profile]")
        pos_memory = prompt.find("[Memory]")
        assert 0 <= pos_identity < pos_persona < pos_skill < pos_extra < pos_profile < pos_memory

    def test_reflexion_prompt_is_english(self):
        from core.react import REFLEXION_SYSTEM_PROMPT

        assert "Du bist" not in REFLEXION_SYSTEM_PROMPT
        assert "quality" in REFLEXION_SYSTEM_PROMPT.lower()


class TestPersonaSettingsRoute:
    def test_get_and_put_persona(self, client, persona_env):
        from core.persona import create_default_persona_if_missing

        create_default_persona_if_missing()
        resp = client.get("/api/settings/persona")
        assert resp.status_code == 200
        body = resp.json()
        assert "persona.md" in body["source"]
        assert body["text"]

        resp = client.put("/api/settings/persona", json={"text": "Custom persona text"})
        assert resp.status_code == 200
        assert (persona_env / "persona.md").read_text(encoding="utf-8") == "Custom persona text"

    def test_put_persona_rejects_oversized(self, client, persona_env):
        resp = client.put("/api/settings/persona", json={"text": "x" * 100_000})
        assert resp.status_code == 413

    def test_editor_text_carries_no_runtime_marker(self, client, persona_env):
        """I7-4: the [persona] prefix belongs in the prompt, not in the editor.

        The user saw their own persona with "[persona]" as its first line and
        counted it inside the 8000 characters — an internal assembly marker
        shown as the interface. Saving only had to strip it so far, so that it
        would not nest once per save.
        """
        from core.persona import create_default_persona_if_missing

        create_default_persona_if_missing()
        body = client.get("/api/settings/persona").json()
        assert not body["text"].startswith("[persona]")
        assert "[persona]" not in body["text"]

        saved = client.put("/api/settings/persona", json={"text": "Ruhig, sachlich, kurz."})
        assert saved.json()["text"] == "Ruhig, sachlich, kurz."


class TestMarkerIdempotence:
    def test_repeated_save_never_nests_markers(self, persona_env):
        """The editor round-trips load_persona() output — saving it back must not
        accumulate one '[persona]' marker per save cycle."""
        from core.persona import load_persona, write_persona

        write_persona("## Personality\n- warm")
        for _ in range(4):
            write_persona(load_persona())  # editor: GET then PUT unchanged
        raw = (persona_env / "persona.md").read_text(encoding="utf-8")
        assert raw.count("[persona]") == 0, "stored file must stay marker-free"
        assert load_persona().count("[persona]") == 1


class TestTheDefaultWorkContract:
    """The four rules the product's own behaviour depends on, in the seed persona.

    They were learned from the field: claims without a tool result, "start my
    project" read as a question, a switched-off tool silently faked, and a long
    run going quiet. A new install must not relearn them.
    """

    def test_the_seed_persona_states_proof_start_switches_and_long_runs(self):
        from core.persona import DEFAULT_PERSONA

        text = DEFAULT_PERSONA.lower()
        assert "tool result" in text, "no proof-first rule"
        assert "start command" in text, "no start-my-project rule"
        assert "capabilities" in text, "no switched-off-capability rule"
        assert "background" in text, "no long-run rule"

    def test_the_seed_persona_stays_identity_free(self):
        from core.persona import DEFAULT_PERSONA

        # Identity is the generated block's job; a name here would drift from it.
        assert "ephe" not in DEFAULT_PERSONA.lower()

