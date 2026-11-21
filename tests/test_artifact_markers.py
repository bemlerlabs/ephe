"""What a WAV card says about the WAV (audit finding 41, half 1).

``WAV_FILE:`` is one marker with three producers: ``synthesize`` speaks a line,
``film_music`` renders a bed and ``film_sound`` one named effect. All three reached
the workbench as a voice, because the marker carried one label for all of them. An
emitter now states the role it knows on the line above its marker and
``core/artifact_markers.artifact_label`` turns that into the card; this module reads
the card the chat route emits, so it breaks when a role collapses back onto another.

The two language halves of a card belong to ``app/src/locales/{en,de}.json``, so the
German is looked up there by the code the server sends rather than restated here.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.artifact_markers import (
    AUDIO_MARKER,
    AUDIO_ROLE_LINE_PREFIX,
    AUDIO_ROLES,
    DEFAULT_AUDIO_ROLE,
    MARKER_BY_KIND,
    artifact_label,
    stated_audio_role,
)
from core.tools import registry
from core.tools.film_tools import film_music, film_sound
from server.routes.chat import _emit_file_result_event

ROOT = Path(__file__).resolve().parents[1]
LOCALES = ROOT / "app" / "src" / "locales"

# The answer `core/voice_synth.py` writes: a marker line and the rung that spoke. Its
# role is the marker row's own, so it needs no role line — that is what an unlabelled
# WAV has to survive, and the plugin path (`tests/test_plugin_bridge.py`) relies on it.
VOICE_RESULT = "WAV_FILE:/out/take.wav\nSpoken by piper: 22050 Hz, 1 channel, 2.10 s"


@pytest.fixture
def cards(monkeypatch):
    """The `file_result` events one tool result turns into, registration stubbed."""
    monkeypatch.setattr(
        "server.routes.chat._register_artifact_safely",
        lambda path, kind, session_id, label="", **_kw: f"id-{path}",
    )

    def emit(result: str) -> list[dict]:
        events: list[dict] = []
        _emit_file_result_event("film_music", result, events.append, "s1")
        return [e for e in events if e["type"] == "file_result"]

    return emit


@pytest.fixture
def artifacts(tmp_path, monkeypatch):
    """The birth place the two film verbs write into."""
    import core.engine_config as engine_config

    folder = tmp_path / "artifacts"
    monkeypatch.setattr(engine_config, "artifact_output_dir", lambda: folder)
    return folder


def bundle(name: str) -> dict:
    return json.loads((LOCALES / name).read_text(encoding="utf-8"))


def card_word(card: dict) -> str:
    """The words a card says about the file, without the file name it carries."""
    return card["label"].split(":")[0].strip()


class TestThreeRolesReadDifferently:
    async def test_the_three_wavs_do_not_come_back_as_one_card(
        self, cards, artifacts
    ):
        """GIVEN a bed, an effect and a spoken line WHEN each is announced THEN no two cards read alike."""
        bed = cards(await film_music("calm", bars=1, bpm=120))[0]
        effect = cards(await film_sound("click"))[0]
        spoken = cards(VOICE_RESULT)[0]

        assert {bed["label"], effect["label"], spoken["label"]} == {
            bed["label"],
            effect["label"],
            spoken["label"],
        }
        assert len({bed["label"], effect["label"], spoken["label"]}) == 3
        assert len({bed["label_code"], effect["label_code"], spoken["label_code"]}) == 3

    async def test_the_bed_and_the_effect_are_not_announced_as_a_voice(
        self, cards, artifacts
    ):
        """GIVEN a spoken line names itself WHEN a bed and an effect are announced THEN neither repeats that word."""
        spoken_word = card_word(cards(VOICE_RESULT)[0])
        bed = cards(await film_music("tense", bars=1, bpm=90))[0]
        effect = cards(await film_sound("whoosh"))[0]

        assert spoken_word
        assert spoken_word not in bed["label"], "a user who asked for music reads music"
        assert spoken_word not in effect["label"]

    async def test_a_stated_role_names_the_role_and_nothing_else(self, cards):
        """GIVEN one role line above one marker WHEN the result is read THEN exactly one card comes out."""
        events = cards(f"{AUDIO_ROLE_LINE_PREFIX}music_bed\nWAV_FILE:/out/calm.wav")
        assert len(events) == 1
        assert events[0]["label_code"] == AUDIO_ROLES["music_bed"][2]
        assert events[0]["label"].endswith("calm.wav"), "the card still carries the file"

    async def test_the_emitted_card_is_the_english_bundle_card(self, cards):
        """The server's English sentence and the English bundle must not drift apart."""
        en = bundle("en.json")["artifactLabel"]
        for role, (_label, _word, leaf) in AUDIO_ROLES.items():
            card = cards(f"{AUDIO_ROLE_LINE_PREFIX}{role}\nWAV_FILE:/out/take.wav")[0]
            assert card["label"] == en[leaf].replace("{{name}}", "take.wav")

    async def test_the_activity_rail_words_are_three_different_words(
        self, artifacts
    ):
        """GIVEN the same three WAVs WHEN the rail is read THEN each verb says its own word."""
        words = []
        for result in (
            await film_music("driving", bars=1, bpm=120),
            await film_sound("pop"),
            VOICE_RESULT,
        ):
            events: list[dict] = []
            _emit_file_result_event("tool", result, events.append, "s1")
            words.append([e["cmd"] for e in events if e["type"] == "activity"][-1])
        assert len(set(words)) == 3


class TestARoleNobodyStated:
    def test_a_wav_with_no_role_line_reads_as_a_voice(self, cards):
        """The default is the voice rung this machine has — never a mystery file."""
        card = cards("WAV_FILE:/out/whatever.wav")[0]
        assert card["label_code"] == AUDIO_ROLES[DEFAULT_AUDIO_ROLE][2]
        assert card["label"] == artifact_label(AUDIO_MARKER, "whatever.wav").label
        assert "whatever" in card["label"]

    def test_a_role_the_table_does_not_name_falls_back_to_the_voice(self, cards):
        card = cards(f"{AUDIO_ROLE_LINE_PREFIX}ambience\nWAV_FILE:/out/x.wav")[0]
        assert card["label_code"] == AUDIO_ROLES[DEFAULT_AUDIO_ROLE][2]

    def test_a_role_line_with_nothing_behind_it_announces_nothing(self, cards):
        assert cards(f"{AUDIO_ROLE_LINE_PREFIX}music_bed") == []

    def test_a_role_line_does_not_cross_a_different_marker(self, cards):
        """A stated role belongs to the WAV under it, not to every WAV that follows."""
        events = cards(
            f"{AUDIO_ROLE_LINE_PREFIX}music_bed\nPNG_FILE:/out/card.png\nWAV_FILE:/out/take.wav"
        )
        png, wav = events
        assert png["file_type"] == "png" and "label_code" not in png
        assert wav["label_code"] == AUDIO_ROLES[DEFAULT_AUDIO_ROLE][2]

    def test_a_role_line_is_not_an_artifact_row(self, cards):
        """The reader must not hand the workbench a file called `music_bed`."""
        events = cards(f"{AUDIO_ROLE_LINE_PREFIX}music_bed\nWAV_FILE:/out/calm.wav")
        assert [e["path"] for e in events] == ["/out/calm.wav"]

    def test_stated_audio_role_passes_a_plain_line_through(self):
        assert stated_audio_role(f"{AUDIO_MARKER}/out/x.wav") is None
        assert stated_audio_role(f"{AUDIO_ROLE_LINE_PREFIX}sound_effect") == "sound_effect"


class TestTheMarkerStillMeansWhatItMeant:
    """The fix moved a label; it moved no marker, no kind and no registered path."""

    def test_audio_is_still_one_kind_for_all_three_roles(self, cards):
        kinds = {
            cards(f"{AUDIO_ROLE_LINE_PREFIX}{role}\nWAV_FILE:/out/x.wav")[0]["file_type"]
            for role in AUDIO_ROLES
        }
        assert kinds == {"audio"}
        assert MARKER_BY_KIND["audio"] == AUDIO_MARKER

    def test_the_role_line_is_not_the_path_the_evidence_gate_stamps(
        self, artifacts
    ):
        """The gate appends its stamp for the WAV, so the role line cannot become the artifact."""
        import asyncio

        result = asyncio.run(film_music("calm", bars=1, bpm=120, out="calm.wav"))
        stamped = registry._evidence_gate_post_hook("film_music", {}, result)
        assert stamped is not None
        assert stamped.rstrip().endswith("calm.wav")

    def test_a_wav_still_lands_in_the_library_under_its_own_name(self, tmp_path, monkeypatch, artifacts):
        from core import artifact_store

        monkeypatch.setattr(artifact_store, "ARTIFACTS_DB", tmp_path / "artifacts.db")
        events: list[dict] = []
        _emit_file_result_event(
            "film_sound",
            f"{AUDIO_ROLE_LINE_PREFIX}sound_effect\nWAV_FILE:/out/click.wav",
            events.append,
            "sess-41",
        )
        rows = artifact_store.list_artifacts(limit=10)
        assert [(row["name"], row["kind"]) for row in rows] == [("click.wav", "audio")]


class TestBothLanguageSurfaces:
    """German and English each have to name all three roles, in three different words."""

    def test_every_role_has_a_leaf_in_both_bundles(self):
        en, de = bundle("en.json")["artifactLabel"], bundle("de.json")["artifactLabel"]
        for _role, (_label, _word, leaf) in AUDIO_ROLES.items():
            assert leaf in en and leaf in de, f"{leaf} is missing from one bundle"
            assert "{{name}}" in en[leaf] and "{{name}}" in de[leaf]

    def test_the_three_roles_are_three_words_in_each_language(self):
        for name in ("en.json", "de.json"):
            leaves = bundle(name)["artifactLabel"]
            words = {
                leaves[leaf].split(":")[0] for _r, (_l, _w, leaf) in AUDIO_ROLES.items()
            }
            assert len(words) == len(AUDIO_ROLES)

    def test_the_german_surface_is_no_paste_of_the_english_one(self):
        en, de = bundle("en.json")["artifactLabel"], bundle("de.json")["artifactLabel"]
        for _role, (_label, _word, leaf) in AUDIO_ROLES.items():
            assert de[leaf] != en[leaf], f"{leaf} reached the German surface untranslated"

    def test_the_frontend_strips_the_role_line_with_the_marker(self):
        """The line is plumbing; a surface that shows a marker's text hides it too.

        Read from the shipped file for the same reason `test_artifact_marker_tables.py`
        reads it: the parity exists only in a file the product cannot import.
        """
        src = (ROOT / "app" / "src" / "lib" / "fileMarkers.ts").read_text(
            encoding="utf-8"
        )
        assert f"'{AUDIO_ROLE_LINE_PREFIX}'" in src
