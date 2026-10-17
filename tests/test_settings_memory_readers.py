"""I6-7 — the memory sliders reach the core and the injection.

Five fields that used to be literals (`_MIN_ANSWER_CHARS`,
`_DUP_SCORE_THRESHOLD`, `max_entries=10`, `score < 0.3`) or only travelled over an
environment variable (`EPHE_MEMORY_ENABLED`). Checked the way I6-3 does:
not the call but the effect — including who wins when
the environment and the slider contradict each other.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, ROOT)

from core.settings_schema import save_deep_settings, validate_sections  # noqa: E402

LONG_ANSWER = (
    "Ephe merkt sich: Die Kunde nennt im Meridian-Interview drei Huerden — "
    "die Datenuebernahme aus dem Altsystem, die Freigabe der Rollen und die "
    "Monatsabrechnung nach neuem Schema."
)
LONG_QUESTION = "Welche drei Huerden nennt die Kunde im Meridian-Interview?"


def _set(**fields) -> None:
    assert save_deep_settings(validate_sections({"memory": fields}))


@pytest.fixture
def memory_home(tmp_path, monkeypatch):
    """Empty device folder, no env switch, fresh factory (the process
    singleton would pin the first instance)."""
    from core import auto_memory

    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))
    monkeypatch.delenv("EPHE_MEMORY_ENABLED", raising=False)
    auto_memory._memory_factory = None
    yield cfg
    auto_memory._memory_factory = None


class _StubMemory:
    """Only what the injection reads: one search run with preset hits."""

    def __init__(self, hits):
        self.hits = hits
        self.calls: list[int] = []
        self.stored: list[str] = []

    def search(self, query: str, top_k: int = 15):
        self.calls.append(top_k)
        return self.hits

    def store(self, text, metadata=None, **options):
        self.stored.append(text)
        return "stub-id"

    def count(self):
        return len(self.stored)


def test_schalter_aus_schreibt_nichts_mehr(memory_home) -> None:
    from core import auto_memory

    _set(**{"memory.capture_enabled": False})
    out = auto_memory.maybe_store_turn(LONG_QUESTION, LONG_ANSWER)
    assert out == {"stored": False, "reason": "disabled"}

    _set(**{"memory.capture_enabled": True})
    stub = _StubMemory([])
    auto_memory._memory_factory = lambda: stub
    ok = auto_memory.maybe_store_turn(LONG_QUESTION, LONG_ANSWER)
    assert ok["stored"] is True
    assert stub.stored, "der Eintrag liegt wirklich beim Speicher, nicht nur im Return"


def test_die_umgebung_gewinnt_gegen_den_regler(memory_home, monkeypatch) -> None:
    """`EPHE_MEMORY_ENABLED=0` is the emergency switch of the start script and the tests —
    a file in the device folder must not undo it."""
    from core import auto_memory

    monkeypatch.setenv("EPHE_MEMORY_ENABLED", "0")
    _set(**{"memory.capture_enabled": True})
    assert auto_memory.capture_enabled() is False


def test_die_antworthoeshe_liest_den_regler(memory_home) -> None:
    from core import auto_memory

    _set(**{"memory.capture_min_answer_chars": 400})
    assert auto_memory.maybe_store_turn(LONG_QUESTION, LONG_ANSWER)["reason"] == "too-short"

    # the same answer that drops out at the default height of 120 — the threshold
    # of the register must not go below 20 characters
    _set(**{"memory.capture_min_answer_chars": 20})
    stub = _StubMemory([])
    auto_memory._memory_factory = lambda: stub
    short = "kurz, aber schon gemeint"
    assert 20 <= len(short) < 120
    assert auto_memory.maybe_store_turn(LONG_QUESTION, short)["stored"] is True
    assert len(LONG_ANSWER) >= 120, "die Probe muss die Default-Hoeshe ueberqueren"


def test_die_duplikatschwelle_liest_den_regler(memory_home) -> None:
    from core import auto_memory

    hit = {"id": "x", "text": "bereits gewusst", "score": 0.87, "metadata": {"source": "auto_memory"}}
    _set(**{"memory.dedupe_score_threshold": 0.85})
    auto_memory._memory_factory = lambda: _StubMemory([hit])
    assert auto_memory.maybe_store_turn(LONG_QUESTION, LONG_ANSWER)["reason"] == "duplicate"

    _set(**{"memory.dedupe_score_threshold": 0.95})
    auto_memory._memory_factory = lambda: _StubMemory([hit])
    assert auto_memory.maybe_store_turn(LONG_QUESTION, LONG_ANSWER)["stored"] is True


def test_injection_hoelt_sich_an_beide_Regler(memory_home) -> None:
    from core.memory import Memory

    hits = [
        {"id": str(i), "text": f"Fakt {i}", "score": 0.9 - i * 0.2, "metadata": {}}
        for i in range(5)
    ]
    stub = _StubMemory(list(hits))
    _set(**{"memory.inject_max_entries": 3, "memory.inject_min_score": 0.5})
    block = Memory.get_context_injection(stub, "Fragen")
    assert stub.calls == [3], "der Suchlauf bekommt die gesetzte Grenze"
    assert "Fakt 0" in block and "Fakt 1" in block
    # 0.9, 0.7, 0.5 pass the threshold of 0.5; 0.3 and 0.1 fall away
    assert "Fakt 3" not in block, "unter der Aehnlichkeitsschwelle bleibt er draussen"

    stub_low = _StubMemory(list(hits))
    _set(**{"memory.inject_max_entries": 5, "memory.inject_min_score": 0.0})
    block_all = Memory.get_context_injection(stub_low, "Fragen")
    assert "Fakt 4" in block_all


def test_die_schranken_sind_im_payload(memory_home) -> None:
    from core.settings_schema import deep_view

    entries = {f["key"]: f for s in deep_view() for f in s["fields"]}
    number_fields = [
        "memory.capture_min_answer_chars",
        "memory.dedupe_score_threshold",
        "memory.inject_max_entries",
        "memory.inject_min_score",
    ]
    for key in number_fields:
        entry = entries[key]
        assert entry["type"] == "number", key
        assert entry["min"] < entry["default"] <= entry["max"], key
        assert entry["hint"] and entry["hintEn"], key
    with pytest.raises(ValueError):
        validate_sections({"memory": {"memory.inject_max_entries": 99}})
