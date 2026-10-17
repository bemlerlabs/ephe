"""Artifact marker tables — server ↔ tools ↔ frontend (W10).

The workbench learns of a produced file only when ``server/routes/chat.py``
registers the marker line the tool result carried. Three lists drift apart if
nothing pins them:

* the server table (``_FILE_RESULT_PREFIXES``) that feeds registration,
* the ``"..._FILE:"`` marker literals the tools and tables in ``core/`` name,
* the frontend copy ``app/src/lib/fileMarkers.ts``.

The user walkthrough (2026-10-12) found the server table stuck at 10 rows while
the deck and source tools emitted far more, found the emitter registering only
the *first* marker of a multi-marker result, and found the frontend copy missing
``WRITE_FILE:``. This module pins all three so none can drift silently again.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from server.routes.chat import _FILE_RESULT_PREFIXES, _emit_file_result_event

ROOT = Path(__file__).resolve().parents[1]
SERVER_PREFIXES = tuple(row[0] for row in _FILE_RESULT_PREFIXES)

_QUOTED_MARKER = re.compile(r'"([A-Z][A-Z0-9_]*_FILE:)"')
_TS_ARRAY = re.compile(r"const FILE_MARKERS = \[(.*?)\] as const", re.DOTALL)
_TS_ENTRY = re.compile(r"'([A-Z][A-Z0-9_]*_FILE:)'")


def _markers_named_in_sources() -> set[str]:
    """Every ``"..._FILE:"`` literal in ``core/`` and ``server/``.

    Declarations count, not only f-string emissions: ``registry._ARTIFACT_MARKERS``
    and ``quality._artifacts_from_raw`` name markers too, and a marker the code
    names must not be missing from the table that feeds the library.
    """
    found: set[str] = set()
    for base in ("core", "server"):
        for path in (ROOT / base).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            found.update(_QUOTED_MARKER.findall(path.read_text(encoding="utf-8")))
    return found


def _frontend_markers() -> tuple[str, ...]:
    src = (ROOT / "app" / "src" / "lib" / "fileMarkers.ts").read_text(encoding="utf-8")
    block = _TS_ARRAY.search(src)
    assert block, "FILE_MARKERS array not found in app/src/lib/fileMarkers.ts"
    return tuple(_TS_ENTRY.findall(block.group(1)))


class TestTablesAgree:
    def test_every_marker_named_in_the_sources_has_a_row(self):
        """A marker the code names but the table lacks never reaches the library."""
        missing = sorted(_markers_named_in_sources() - set(SERVER_PREFIXES))
        assert not missing, f"markers named in core/ or server/ with no table row: {missing}"

    def test_every_row_is_a_marker_someone_names(self):
        """No dead rows: a row nothing refers to is a marker nobody can emit."""
        extra = sorted(set(SERVER_PREFIXES) - _markers_named_in_sources())
        assert not extra, f"table rows no source names: {extra}"

    def test_table_has_no_duplicate_prefixes(self):
        assert len(SERVER_PREFIXES) == len(set(SERVER_PREFIXES))

    def test_frontend_and_server_tables_agree_both_ways(self):
        """The frontend copy documents itself as parity with the server table."""
        server, frontend = set(SERVER_PREFIXES), set(_frontend_markers())
        only_server = sorted(server - frontend)
        only_frontend = sorted(frontend - server)
        assert not only_server and not only_frontend, (
            f"only in server table: {only_server}; only in frontend fileMarkers.ts: {only_frontend}"
        )

    def test_frontend_table_has_no_duplicate_prefixes(self):
        fe = _frontend_markers()
        assert len(fe) == len(set(fe))


@pytest.fixture
def registrations(monkeypatch):
    """Records every artifact registration the emitter asks for."""
    calls: list[dict] = []

    def fake_register(path, kind, session_id, label="", *, turn_id="", call_id="", args_hash=""):
        calls.append({"path": path, "kind": kind, "label": label})
        return f"id-{len(calls)}"

    monkeypatch.setattr("server.routes.chat._register_artifact_safely", fake_register)
    return calls


def _emit(result: str):
    events: list[dict] = []
    _emit_file_result_event("create_pptx_deck", result, events.append, "s1")
    return events


def _file_events(events) -> list[dict]:
    return [e for e in events if e["type"] == "file_result"]


# The shape a real create_pptx_deck / create_pitch_deck result has: several
# markers, one per line (core/tools/_deck_public.py + core/deck_render.py).
_DECK_RESULT = "\n".join(
    [
        "PPTX_DECK_FILE:/out/deck.pptx",
        "SCORECARD_FILE:/out/deck.bundle/scorecard.json",
        "MANIFEST_FILE:/out/deck.bundle/manifest.json",
        "QA_FILE:/out/deck.bundle/qa.json",
        "CONTACT_SHEET_FILE:/out/deck.contact-sheet.html",
    ]
)


class TestEmitterRegistersEveryMarker:
    def test_multi_marker_result_emits_one_event_per_marker(self, registrations):
        events = _emit(_DECK_RESULT)
        file_events = _file_events(events)
        assert len(file_events) == 5, (
            "a multi-marker result must register every marker, not only the first"
        )
        assert {e["file_type"] for e in file_events} == {
            "pptx", "scorecard", "manifest", "qa", "html",
        }
        assert [c["path"] for c in registrations] == [
            "/out/deck.pptx",
            "/out/deck.bundle/scorecard.json",
            "/out/deck.bundle/manifest.json",
            "/out/deck.bundle/qa.json",
            "/out/deck.contact-sheet.html",
        ]

    def test_markers_the_old_table_lacked_now_register(self, registrations):
        """SCORECARD_FILE/MANIFEST_FILE/QA_FILE/CONTACT_SHEET_FILE were absent."""
        kinds = {e["file_type"] for e in _file_events(_emit(_DECK_RESULT))}
        assert {"scorecard", "manifest", "qa", "html"} <= kinds

    def test_marker_on_a_later_line_registers(self, registrations):
        """video_tools appends the hero PNG after the pipeline's file listing."""
        result = "clip-1.webm\nclip-2.gif\nhero: banner\nPNG_FILE:/out/hero.png"
        events = _file_events(_emit(result))
        assert [e["file_type"] for e in events] == ["png"]
        assert events[0]["path"] == "/out/hero.png"

    def test_two_markers_for_the_same_path_share_one_library_row(self, registrations):
        """deck_render writes one canonical QA report for RENDER_QA and VISUAL_QA."""
        result = "RENDER_QA_FILE:/out/render-qa.json\nVISUAL_QA_FILE:/out/render-qa.json"
        events = _file_events(_emit(result))
        assert [e["file_type"] for e in events] == ["render_qa", "visual_qa"]
        assert len(registrations) == 1, "one file, one library row"
        assert {e["id"] for e in events} == {"id-1"}

    def test_marker_mid_line_is_not_an_artifact(self, registrations):
        events = _file_events(_emit("See the PDF_FILE: mention inside a sentence."))
        assert events == []
        assert registrations == []

    def test_marker_inside_a_diff_body_is_not_a_phantom_artifact(self, registrations):
        """write_file's line 2 is a unified diff; its lines are indented by +/-/space."""
        result = (
            "WRITE_FILE:/out/notes.md\n"
            "(40 characters written, overwritten — diff:\n"
            "@@ -1 +1 @@\n"
            "-PDF_FILE:/old/phantom.pdf\n"
            "+SCORECARD_FILE:/new/phantom.json\n"
            " MANIFEST_FILE:/context/phantom.json\n"
            ")"
        )
        events = _file_events(_emit(result))
        assert [e["file_type"] for e in events] == ["file"]
        assert [c["path"] for c in registrations] == ["/out/notes.md"]

    def test_marker_without_a_path_is_skipped(self, registrations):
        assert _file_events(_emit("SCORECARD_FILE:")) == []
        assert registrations == []

    def test_multi_marker_result_still_reports_one_done_activity_per_marker(self, registrations):
        events = _emit(_DECK_RESULT)
        activities = [e for e in events if e["type"] == "activity"]
        assert len(activities) == 5
        assert all(a["status"] == "done" for a in activities)

    def test_result_without_a_marker_keeps_its_generic_done_activity(self, registrations):
        events = _emit("plain tool text, no artifact here")
        assert _file_events(events) == []
        assert [e["type"] for e in events] == ["activity"]
        assert "plain tool text" in events[0]["cmd"]


class TestRealStoreReceivesEveryMarker:
    """End to end through the real artifact_store, with no stub."""

    def test_every_marker_of_a_deck_result_lands_in_the_library(self, tmp_path, monkeypatch):
        from core import artifact_store

        root = tmp_path / "ephe-home"
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(root))
        monkeypatch.setattr(artifact_store, "ARTIFACTS_DB", tmp_path / "artifacts.db")

        paths = {
            "pptx": tmp_path / "deck.pptx",
            "scorecard": tmp_path / "scorecard.json",
            "manifest": tmp_path / "manifest.json",
            "qa": tmp_path / "qa.json",
            "contact": tmp_path / "deck.contact-sheet.html",
        }
        for path in paths.values():
            path.write_text("x", encoding="utf-8")
        result = "\n".join(
            [
                f"PPTX_DECK_FILE:{paths['pptx']}",
                f"SCORECARD_FILE:{paths['scorecard']}",
                f"MANIFEST_FILE:{paths['manifest']}",
                f"QA_FILE:{paths['qa']}",
                f"CONTACT_SHEET_FILE:{paths['contact']}",
            ]
        )

        events: list[dict] = []
        _emit_file_result_event("create_pptx_deck", result, events.append, "sess-w10")

        listed = artifact_store.list_artifacts(limit=50)
        names = {row["name"] for row in listed}
        assert names == {p.name for p in paths.values()}, (
            f"library holds {sorted(names)}; every marker must land there"
        )
        kinds = {row["kind"] for row in listed}
        assert kinds == {"pptx", "scorecard", "manifest", "qa", "html"}
        assert all(e.get("id") for e in _file_events(events)), "every card carries its id"
