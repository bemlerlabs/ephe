"""Ephe — the home-isolation ratchet holds: recorded debt is bounded, growth fails.

``tests/test_home_isolation.py`` installs the in-process tripwire; ``scripts/home_isolation_gate.py``
owns the decision over a committed baseline. These tests drive the gate with an injected
measurement, so they need no full suite run — they check the ratchet policy itself:

* an offender already in the baseline is tolerated, one that grows or is new fails;
* the ratchet is per offender, so a clean-up cannot pay for a new leak elsewhere;
* ``--update`` only ever lowers the baseline, never raises it;
* a baseline shape that could hide growth (an absolute home path, a non-``tests/``
  key, an exemption entry, a missing file) is refused as an error, not accepted.

Given / When / Then, strictly.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parent.parent
GATE_PATH = REPO / "scripts" / "home_isolation_gate.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("home_isolation_gate_under_test", GATE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_gate()

#: A recorded offender: a pytest test id that leaks into the real home.
OFFENDER = "tests/test_cli_desktop.py::test_desktop_starts_backend"
#: Other offender ids used to prove the per-offender ratchet.
SECOND = "tests/test_parity_tools.py::test_skill_manage_create_and_delete"


def baseline(tmp_path: Path, offenders: dict[str, int], **extra) -> Path:
    path = tmp_path / "home-isolation-baseline.json"
    payload: dict = {
        "policy": gate.POLICY,
        "version": gate.VERSION,
        "instrument": "tests/test_home_isolation.py",
        "offenders": offenders,
    }
    payload.update(extra)
    payload["total"] = sum(offenders.values())
    path.write_text(json.dumps(payload, sort_keys=True, indent=1), encoding="utf-8")
    return path


def run(tmp_path: Path, path: Path, measured: dict[str, int], *flags: str) -> int:
    read_measured: Callable[[], dict[str, int]] = lambda: measured
    return gate.main(["--baseline", str(path), *flags], read_measured=read_measured)


class TestGrowthFails:
    def test_an_offender_that_wrote_more_fails_and_is_named(self, tmp_path, capsys):
        """GIVEN a baseline of one write WHEN that test writes twice THEN the gate fails by name."""
        path = baseline(tmp_path, {OFFENDER: 1})
        code = run(tmp_path, path, {OFFENDER: 2})
        out = capsys.readouterr().out
        assert code == 1
        assert "FAIL" in out
        assert OFFENDER in out
        assert "1 -> 2" in out

    def test_a_new_offender_fails_even_when_the_total_shrinks(self, tmp_path, capsys):
        """GIVEN one offender cleaned up and a new one leaking WHEN measured THEN growth wins."""
        path = baseline(tmp_path, {OFFENDER: 9, SECOND: 0})
        code = run(tmp_path, path, {OFFENDER: 1, SECOND: 4})
        out = capsys.readouterr().out
        assert code == 1
        assert SECOND in out
        # the total fell from nine writes to five, and the gate still failed: the
        # ratchet is per offender, so one clean-up cannot pay for a new leak.
        assert "total 9 -> 5" in out

    def test_an_unchanged_tree_passes_quietly(self, tmp_path, capsys):
        """GIVEN a baseline that matches the measurement WHEN the gate runs THEN it passes."""
        path = baseline(tmp_path, {OFFENDER: 2})
        code = run(tmp_path, path, {OFFENDER: 2})
        out = capsys.readouterr().out
        assert code == 0
        assert "PASS" in out
        assert "lowered" not in out


class TestShrinkagePasses:
    def test_a_cleaner_run_passes_and_offers_to_lower_the_baseline(self, tmp_path, capsys):
        """GIVEN three writes baselined WHEN only one is left THEN the gate says: lower it."""
        path = baseline(tmp_path, {OFFENDER: 3})
        code = run(tmp_path, path, {OFFENDER: 1})
        out = capsys.readouterr().out
        assert code == 0
        assert "PASS" in out
        assert "the baseline can be lowered" in out
        assert "home_isolation_gate.py --update" in out

    def test_update_lowers_the_baseline(self, tmp_path, capsys):
        """GIVEN a cleaner run WHEN --update runs THEN the committed number follows it down."""
        path = baseline(tmp_path, {OFFENDER: 3})
        assert run(tmp_path, path, {OFFENDER: 1}, "--update") == 0
        assert "baseline lowered" in capsys.readouterr().out
        assert json.loads(path.read_text())["offenders"] == {OFFENDER: 1}

    def test_an_offender_now_clean_is_dropped_by_update(self, tmp_path, capsys):
        """GIVEN a leaked offender WHEN its suite is made hermetic THEN --update removes it."""
        path = baseline(tmp_path, {OFFENDER: 2, SECOND: 5})
        assert run(tmp_path, path, {SECOND: 5}, "--update") == 0
        assert "1 offender(s) now clean" in capsys.readouterr().out
        assert json.loads(path.read_text())["offenders"] == {SECOND: 5}

    def test_update_refuses_to_raise_the_baseline(self, tmp_path, capsys):
        """GIVEN a run that grew WHEN --update runs THEN the baseline stays put and it fails."""
        path = baseline(tmp_path, {OFFENDER: 1})
        before = path.read_text()
        assert run(tmp_path, path, {OFFENDER: 5}, "--update") == 1
        assert "only lowers" in capsys.readouterr().err
        assert path.read_text() == before


class TestNoAccidentalWhitelist:
    def test_an_absolute_home_path_in_the_baseline_is_refused(self, tmp_path, capsys):
        """GIVEN an absolute path recorded as an offender WHEN the gate reads it THEN error."""
        path = tmp_path / "b.json"
        path.write_text(
            json.dumps({
                "policy": gate.POLICY, "version": gate.VERSION,
                "instrument": "tests/test_home_isolation.py", "total": 1,
                "offenders": {"/Users/dev/.ephe/desktop.json": 1},
            }),
            encoding="utf-8",
        )
        code = run(tmp_path, path, {})
        err = capsys.readouterr().err
        assert code == 2
        assert "repo-relative test id" in err
        assert "/Users/dev/.ephe/desktop.json" in err

    def test_a_non_test_key_in_the_baseline_is_refused(self, tmp_path, capsys):
        """GIVEN a bare core/ path recorded WHEN the gate reads it THEN it is refused."""
        path = baseline(tmp_path, {"core/order.py": 3})
        code = run(tmp_path, path, {})
        err = capsys.readouterr().err
        assert code == 2
        assert "repo-relative test id" in err

    def test_an_exemption_key_in_the_baseline_is_refused(self, tmp_path, capsys):
        """GIVEN a whitelist-shaped key WHEN the gate reads the baseline THEN it refuses the shape."""
        path = baseline(tmp_path, {OFFENDER: 1}, exempt=[OFFENDER])
        code = run(tmp_path, path, {})
        err = capsys.readouterr().err
        assert code == 2
        assert "no exemption list" in err
        assert "exempt" in err

    def test_a_missing_baseline_is_an_error_not_a_pass(self, tmp_path, capsys):
        """GIVEN no baseline WHEN the gate runs THEN it says so instead of tolerating all."""
        report = tmp_path / "report.json"
        report.write_text(json.dumps({}), encoding="utf-8")
        missing = tmp_path / "home-isolation-baseline.json"
        code = gate.main(["--baseline", str(missing), "--report", str(report)])
        err = capsys.readouterr().err
        assert code == 2
        assert "--update" in err

    def test_the_committed_baseline_itself_loads(self):
        """The file in the tree must pass every shape check the gate enforces."""
        offenders = gate.load_baseline(gate.BASELINE_DEFAULT)
        assert all(gate.is_offender_key(k) for k in offenders)
