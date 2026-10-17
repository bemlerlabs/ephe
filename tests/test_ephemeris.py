"""
◑ Ephe – The ephemerides (S-wave "sky"): Tau's orbit as an orbit constellation.
tests/test_ephemeris.py

The ephemeris is the agent's star catalogue: it records WHEN Ephe had
encounters — never WHAT happened. Pins:

1. record → load roundtrip (d/h/k/n); unknown kind → ValueError
   (fail-closed against rubbish, so junk never lands in the sky).
2. load fail-soft: a broken line gets skipped, it never raises.
3. chart: header lines + 7 day rows + hour ruler; the sown hour
   shows the full block (█).
4. empty chart → dotted sky + "Der Himmel wartet", never raises.  # language-gate: ignore (quoted chart line as it ships, core/ephemeris.py:134)
5. Per-day normalization: a quiet day still shows █ at its own
   maximum (every day its own constellation).
6. Faded: orbits outside the horizon count as "verblasst" and  # language-gate: ignore (quoted chart footer word as it ships, core/ephemeris.py:151)
   do not appear in the picture.
7. PRIVACY CONTRACT (value equality): the store file holds exclusively
   the keys d/h/k/n — no path, no message, no model name.
8. crystallize: month sums + peak hour + amber file in the target folder.
9. cmd_sky prints the ephemeris from the tmp store (no real home needed).
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import ephemeris as em  # noqa: E402

TODAY = date(2026, 9, 28)
NOW = datetime(2026, 9, 28, 14, 30)


@pytest.fixture
def store(tmp_path: Path) -> Path:
    return tmp_path / "ephemeris.jsonl"


class TestRecord:

    def test_roundtrip_and_strict_kinds(self, store: Path):
        em.record("session", now=NOW, store=store)
        em.record("tool", count=3, now=NOW, store=store)
        events = em.load(store)
        assert len(events) == 2
        assert events[0] == {"d": "2026-09-28", "h": 14, "k": "session", "n": 1}
        assert events[1]["n"] == 3
        with pytest.raises(ValueError):
            em.record("geheimprotokoll", now=NOW, store=store)
        with pytest.raises(ValueError):
            em.record("message", now=NOW, store=store)  # content is not an orbit point

    def test_privacy_contract_value_equality(self, store: Path):
        """The store knows only d/h/k/n — never paths, messages, model names."""
        em.record("tool", count=2, now=NOW, store=store)
        raw = store.read_text(encoding="utf-8")
        for line in raw.splitlines():
            keys = set(json.loads(line))
            assert keys == {"d", "h", "k", "n"}, keys
        # Value equality: an invented piece of content must not appear anywhere
        assert "geheimer-inhalt" not in raw
        assert "/Users/" not in raw

    def test_load_fail_soft_on_corrupt_line(self, store: Path):
        em.record("session", now=NOW, store=store)
        with open(store, "a", encoding="utf-8") as fh:
            fh.write("{ kaputte zeile !!\n")
            fh.write("\n")
        events = em.load(store)
        assert len(events) == 1  # the good line survives, the rubbish gets skipped


class TestChart:

    def _seeded(self) -> list[dict]:
        return [
            {"d": "2026-09-28", "h": 14, "k": "tool", "n": 5},
            {"d": "2026-09-28", "h": 9, "k": "session", "n": 1},
            {"d": "2026-09-22", "h": 20, "k": "artifact", "n": 2},
        ]

    def test_shape_header_rows_ruler(self):
        out = em.chart(self._seeded(), days=7, today=TODAY)
        lines = out.splitlines()
        assert lines[0].startswith("◍ Ephe Ephemeris")
        assert "Bahnen, keine Inhalte" in lines[1]
        day_rows = [ln for ln in lines if "│" in ln]
        assert len(day_rows) == 7
        assert day_rows[-1].startswith("Mo 28.09")  # 2026-09-28 is a Monday
        assert "0" in lines[-1] and "23h" in lines[-1]  # hour ruler

    def test_full_block_at_seeded_hour(self):
        out = em.chart(self._seeded(), days=7, today=TODAY)
        today_row = next(ln for ln in out.splitlines() if "28.09" in ln)
        bar = today_row.split("│")[1]
        assert bar[14] == "█"  # 14:00 = column 14, peak of the day
        assert bar.count("·") == 23

    def test_empty_sky_never_crashes(self):
        out = em.chart([], days=7, today=TODAY)
        assert "Der Himmel wartet" in out
        assert out.count("│") == 14  # 7 rows × 2 delimiters

    def test_per_day_normalization(self):
        events = [
            {"d": "2026-09-28", "h": 14, "k": "tool", "n": 9},
            {"d": "2026-09-27", "h": 8, "k": "tool", "n": 1},
        ]
        out = em.chart(events, days=7, today=TODAY)
        loud = next(ln for ln in out.splitlines() if "28.09" in ln)
        quiet = next(ln for ln in out.splitlines() if "27.09" in ln)
        assert loud.split("│")[1][14] == "█"
        assert quiet.split("│")[1][8] == "█"  # quiet day: own maximum = full block

    def test_faded_outside_horizon(self):
        events = self._seeded() + [{"d": "2026-05-01", "h": 3, "k": "tool", "n": 7}]
        out = em.chart(events, days=7, today=TODAY)
        assert "7 verblasst" in out
        assert "01.05" not in out


class TestCrystallize:

    def test_month_sums_peak_and_amber_file(self, tmp_path: Path):
        events = [
            {"d": "2026-09-01", "h": 10, "k": "session", "n": 2},
            {"d": "2026-09-15", "h": 10, "k": "tool", "n": 4},
            {"d": "2026-09-20", "h": 22, "k": "tool", "n": 6},
            {"d": "2026-08-30", "h": 5, "k": "tool", "n": 99},  # a different month
        ]
        amber_dir = tmp_path / "amber"
        amber = em.crystallize(events, month="2026-09", amber_dir=amber_dir)
        assert amber["monat"] == "2026-09"
        assert amber["sitzungen"] == 2
        assert amber["werkzeuge"] == 10
        assert amber["spitzstunde"].startswith("22:00")
        assert amber["tage_aktiv"] == 3
        out = amber_dir / "2026-09.json"
        assert out.is_file()
        assert json.loads(out.read_text(encoding="utf-8"))["werkzeuge"] == 10

    def test_empty_month_is_graceful(self):
        amber = em.crystallize([], month="2026-09")
        assert amber["sitzungen"] == 0
        assert amber["spitzstunde"] is None


class TestCli:

    def test_cmd_sky_prints_chart_from_tmp_store(self, tmp_path: Path, monkeypatch, capsys):
        import argparse

        from core import ephemeris as em2

        store = tmp_path / "e.jsonl"
        em2.record("session", now=NOW, store=store)
        monkeypatch.setattr(em2, "default_store", lambda: store)
        monkeypatch.setattr(em2, "real_today", lambda: date(2026, 9, 28))  # calendar-stable
        from ephe_cli import cmd_sky

        r = cmd_sky(argparse.Namespace(days=3))
        assert r == 0
        out = capsys.readouterr().out
        assert "Ephemeris" in out
        assert "28.09" in out

    def test_cmd_amber_writes_bernstein(self, tmp_path: Path, monkeypatch, capsys):
        import argparse

        from core import ephemeris as em2

        store = tmp_path / "e.jsonl"
        em2.record("tool", count=4, now=NOW, store=store)
        monkeypatch.setattr(em2, "default_store", lambda: store)
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        from ephe_cli import cmd_amber

        r = cmd_amber(argparse.Namespace(month="2026-09"))
        assert r == 0
        out = capsys.readouterr().out
        assert "werkzeuge" in out
        assert (tmp_path / ".ephe" / "amber" / "2026-09.json").is_file()
