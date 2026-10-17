"""
◑ Ephe – E4 golden tests per plugin (benchmark targets Opus 5.5 / GPT Astra 6)
tests/test_r74_plugin_golden.py

Every production plugin carries prompts/golden.jsonl (≥ 6 mechanically gradable
cases) and prompts/rubric.md (quality criteria). Output quality is MEASURED
against the reference models (pass³ matrix), not claimed.
Pins:

1. EVERY production plugin has a golden suite: ≥ 6 valid cases + rubric.md.
2. Schema fail-closed: missing field / unknown expect.kind / duplicate id →
   ValueError (rubbish never reaches the matrix).
3. Case.command (when set) has to be a command in the manifest.
4. Ids unique and carrying the plugin prefix.
5. verify_all(): the CI gate — zero findings across all 14 plugins.
6. Every grader rule is mechanical (artifact→suffix, tool_use/contains/
   not_contains→any not empty).
7. Anti-slop: every suite has at least one not_contains marker
   (placeholder/TODO traps).
8. pass³ runner: fake engine, 3 runs per case, ALL have to pass
   (TAU reliability as in evals/bench_option_b.py); report as JSON.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_golden as pg  # noqa: E402

PLUGINS = sorted(p for p in (ROOT / "plugins").iterdir() if (p / "ephe-plugin.json").is_file())


class TestSuites:

    def test_every_production_plugin_has_golden_suite(self):
        assert len(PLUGINS) == 14
        for pdir in PLUGINS:
            golden = pdir / "prompts" / "golden.jsonl"
            rubric = pdir / "prompts" / "rubric.md"
            assert golden.is_file(), f"{pdir.name}: golden.jsonl fehlt"
            assert rubric.is_file() and len(rubric.read_text(encoding="utf-8")) > 200, (
                f"{pdir.name}: rubric.md fehlt oder nichtssagend"
            )
            cases = pg.load_golden(golden, plugin=pdir.name)
            assert len(cases) >= 6, f"{pdir.name}: only {len(cases)} cases"

    def test_command_references_resolve(self):
        for pdir in PLUGINS:
            manifest = json.loads((pdir / "ephe-plugin.json").read_text(encoding="utf-8"))
            names = {c["name"] for c in manifest.get("components", {}).get("commands", [])}
            for case in pg.load_golden(pdir / "prompts" / "golden.jsonl", plugin=pdir.name):
                cmd = case.get("command")
                assert cmd is None or cmd in names, f"{pdir.name}: Case {case['id']} referenziert unbekanntes Command {cmd!r}"


class TestSchema:

    def _write(self, tmp_path: Path, line: str) -> Path:
        p = tmp_path / "golden.jsonl"
        p.write_text(line + "\n", encoding="utf-8")
        return p

    def test_missing_field_fails_closed(self, tmp_path):
        p = self._write(tmp_path, json.dumps({"id": "x-1", "input": "task"}))
        with pytest.raises(ValueError):
            pg.load_golden(p, plugin="x")

    def test_unknown_expect_kind_fails_closed(self, tmp_path):
        bad = {"id": "x-1", "input": "task", "expect": {"kind": "magie", "any": ["a"]}}
        p = self._write(tmp_path, json.dumps(bad))
        with pytest.raises(ValueError):
            pg.load_golden(p, plugin="x")

    def test_duplicate_id_fails_closed(self, tmp_path):
        case = {"id": "x-1", "input": "task", "expect": {"kind": "contains", "any": ["a"]}}
        p = tmp_path / "golden.jsonl"
        p.write_text(json.dumps(case) + "\n" + json.dumps(case) + "\n", encoding="utf-8")
        with pytest.raises(ValueError):
            pg.load_golden(p, plugin="x")

    def test_ids_prefixed_and_unique_across_repo(self):
        seen: set[str] = set()
        for pdir in PLUGINS:
            for case in pg.load_golden(pdir / "prompts" / "golden.jsonl", plugin=pdir.name):
                assert case["id"].startswith(pdir.name + "-"), case["id"]
                assert case["id"] not in seen, f"doppelte id {case['id']}"
                seen.add(case["id"])

    def test_grader_rules_are_mechanical(self):
        for pdir in PLUGINS:
            for case in pg.load_golden(pdir / "prompts" / "golden.jsonl", plugin=pdir.name):
                expect = case["expect"]
                kind = expect["kind"]
                if kind == "artifact":
                    assert expect.get("suffix", "").startswith("."), case["id"]
                else:
                    assert expect.get("any"), f"{case['id']}: {kind} braucht any"
                    assert isinstance(expect["any"], list)

    def test_every_suite_has_anti_slop_marker(self):
        for pdir in PLUGINS:
            kinds = [
                c["expect"]["kind"]
                for c in pg.load_golden(pdir / "prompts" / "golden.jsonl", plugin=pdir.name)
            ]
            assert "not_contains" in kinds, f"{pdir.name}: keine Anti-Slop-Falle"


class TestVerifyAll:

    def test_ci_gate_reports_zero_issues(self):
        report = pg.verify_all(ROOT / "plugins")
        bad = [r for r in report if r["issues"]]
        assert not bad, json.dumps(bad, ensure_ascii=False)[:800]
        assert len(report) == 14
        total = sum(r["cases"] for r in report)
        assert total >= 84, f"Matrix zu klein: {total} < 84 (60-Task-Ziel übererfüllt sein)"

    def test_ephe_bench_verify_gate_exits_zero(self, capsys):
        """The product command 'ephe bench' (verify path) is the CI gate."""
        import ephe_cli

        args = ephe_cli.build_parser().parse_args(["bench"])
        assert ephe_cli.cmd_bench(args) == 0
        assert "92 cases" in capsys.readouterr().out


class TestPass3Runner:

    @pytest.fixture
    def suite(self, tmp_path: Path) -> Path:
        cases = [
            {"id": "t-1", "input": "Aufgabe eins mit etwas Kontext", "expect": {"kind": "contains", "any": ["ok"]}},
            {"id": "t-2", "input": "Aufgabe zwei mit Kontext", "expect": {"kind": "contains", "any": ["nein"]}},
            {"id": "t-3", "input": "Aufgabe drei mit Kontext", "expect": {"kind": "contains", "any": ["ok"]}},
        ]
        d = tmp_path / "plugins" / "t"
        d.mkdir(parents=True)
        (d / "prompts").mkdir()
        (d / "prompts" / "golden.jsonl").write_text(
            "\n".join(json.dumps(c) for c in cases) + "\n", encoding="utf-8"
        )
        return d

    def test_pass3_requires_all_runs(self, suite, monkeypatch):
        """Repo semantics (TAU): pass³ = ALL runs, a majority does not count."""
        answers = {"t-1": ["ok", "ok", "leider fail"], "t-2": ["x", "y", "z"], "t-3": ["ok", "ok", "ok"]}
        monkeypatch.setattr(pg, "run_once", lambda case, engine=None: answers[case["id"]].pop(0))
        rows = pg.pass3_matrix(suite, runs=["a", "b", "c"])
        by_id = {r["id"]: r for r in rows}
        assert by_id["t-1"]["passes"] == 2 and by_id["t-1"]["pass3"] is False  # 2/3 is not ENOUGH
        assert by_id["t-2"]["pass3"] is False
        assert by_id["t-3"]["passes"] == 3 and by_id["t-3"]["pass3"] is True

    def test_report_written(self, suite, tmp_path, monkeypatch):
        monkeypatch.setattr(pg, "run_once", lambda case, engine=None: "ok")
        out = tmp_path / "matrix.json"
        pg.pass3_matrix(suite, runs=["a", "b", "c"], report=out)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["plugin"] == "t" and len(data["rows"]) == 3
        assert data["pass3_rate"] == pytest.approx(2 / 3)  # t-2 demands 'nein', the engine says 'ok'
