"""
◑ Ephe – W3a (2026-09-24): the architecture checker (plan step 2).
tests/test_r46_architecture_check.py

RULE: tests BEFORE the implementation (convention from test_r44).

Pins:
1. `check` mode ends with exit 0 as long as no baseline is frozen at the
   path it is given (no baseline => every finding is only a hint); the
   path in this pin is private, the way the freeze path below is.
2. `report` returns JSON with the fields policyVersion, managedModules,
   findings, counts, baselinePresent; per finding the 6 schema fields.
3. The maxFileLines tally for app-frontend agrees exactly with an
   independent wc-style count over the 5 roots.
4. `baseline:update --baseline <path>` writes exactly that path and
   `check` stays exit 0 against it (actual == baseline); the tracked
   .architecture-baseline.json is untouched by either call.
5. --module filters the findings down to one module.
6. A per-rule count above the frozen value flips that rule's findings to
   `error` and exits 1; pinned on a private baseline, so the verdict does
   not depend on where the tracked freeze sits above the tree.

The tracked `.architecture-baseline.json` is a read-only input here.
`tests/test_harness_lab_gate.py` loads it at import,
`scripts/harness_lab_gate.py` reads it inside a round, and the `check`
mode reads it too — so the earlier shape of pin 4, an update
against the tracked path plus a restore in `finally`, wrote state every
parallel worker could see: under `pytest tests -n 8` the updater's write
overlaps the readers' `JSON.parse`. Private paths keep the suite off
that overlap. What `check` reports against the tracked freeze is
deliberately unpinned: the freeze is refreshed by hand, the tree is
shared, and no test here can say when the two are meant to coincide.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "architecture_check.mjs"
BASELINE = ROOT / ".architecture-baseline.json"

FRONTEND_ROOTS = [
    "app/src/components",
    "app/src/hooks",
    "app/src/lib",
    "app/src/store",
    "app/src/pages",
]
FINDING_KEYS = {"rule", "module", "file", "value", "limit", "severity"}


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["node", str(CHECKER), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )


def _expected_big_files(limit: int = 400) -> list[str]:
    """Independent reference tally: .ts/.tsx files over `limit` lines."""
    out: list[str] = []
    for root in FRONTEND_ROOTS:
        base = ROOT / root
        for p in sorted(base.rglob("*")):
            if p.is_file() and p.suffix in {".ts", ".tsx"}:
                n = len(p.read_text(encoding="utf-8", errors="replace").splitlines())
                if n > limit:
                    out.append(str(p.relative_to(ROOT)).replace("\\", "/"))
    return sorted(out)


def test_checker_file_exists():
    assert CHECKER.is_file(), "scripts/architecture_check.mjs fehlt"


def test_check_mode_exits_zero_without_baseline(tmp_path: Path) -> None:
    """No baseline at the path it is given => every finding is a hint => exit 0.

    The frozen file is not a stand-in for "no baseline": the absent path is private, so the
    run cannot owe its verdict to the tracked freeze or to when the tree last outgrew it.
    """
    missing = tmp_path / "absent.json"
    r = _run("check", "--baseline", str(missing))
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"
    assert "baseline=false" in r.stdout, r.stdout
    assert "0 errors" in r.stdout, r.stdout


def test_check_flips_findings_to_errors_above_the_freeze(tmp_path: Path) -> None:
    """A per-rule count above the frozen value turns that rule's findings into errors.

    The freeze is private and built from the live report with every count lowered by one,
    so the error path is pinned no matter how the tracked freeze and the checked-out tree
    currently line up.
    """
    data = json.loads(_run("report", "--baseline", str(tmp_path / "absent.json")).stdout)
    per_rule: dict[str, int] = {}
    for finding in data["findings"]:
        per_rule[finding["rule"]] = per_rule.get(finding["rule"], 0) + 1
    if not per_rule:
        pytest.skip("no findings in this tree; nothing to ratchet")
    frozen = tmp_path / "frozen.json"
    frozen.write_text(
        json.dumps(
            {
                "policyVersion": data["policyVersion"],
                "frozenAt": "1970-01-01T00:00:00.000Z",
                "perRule": {rule: count - 1 for rule, count in per_rule.items()},
                "total": data["counts"]["total"],
            }
        ),
        encoding="utf-8",
    )
    r = _run("check", "--baseline", str(frozen))
    assert r.returncode == 1, f"stdout={r.stdout}\nstderr={r.stderr}"
    # With every rule count one below, no finding can stay a hint: the summary's hint
    # count reads zero (a plain `"0 errors" not in` would also match "50 errors").
    assert ", 0 hints)" in r.stdout, r.stdout


def test_report_json_contract():
    r = _run("report")
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    for key in ("policyVersion", "managedModules", "findings", "counts", "baselinePresent"):
        assert key in data, f"report-Feld '{key}' fehlt"
    assert data["policyVersion"] == 1
    assert isinstance(data["managedModules"], int)
    assert isinstance(data["findings"], list)
    assert isinstance(data["counts"], dict)
    assert isinstance(data["baselinePresent"], bool)
    for f in data["findings"]:
        assert set(f.keys()) == FINDING_KEYS, f"Finding-Schema: {f}"


def test_max_file_lines_parity_with_independent_count():
    """Checker tally == own splitlines count over the 5 roots."""
    for _attempt in range(2):
        data = json.loads(_run("report").stdout)
        got = sorted(
            f["file"]
            for f in data["findings"]
            if f["rule"] == "maxFileLines" and f["module"] == "app-frontend"
        )
        expected = _expected_big_files()
        if got == expected:
            assert len(expected) >= 1, "Referenzzahlung leer — Wurzeln falsch?"
            return
    assert got == expected, f"maxFileLines-Paritaet: got={got} expected={expected}"


def test_module_filter():
    data = json.loads(_run("report", "--module", "scripts").stdout)
    assert all(f["module"] == "scripts" for f in data["findings"])
    assert data["counts"]["total"] == len(data["findings"])


def test_baseline_update_then_check_zero(tmp_path: Path) -> None:
    """baseline:update --baseline <path> writes it; check stays exit 0 against it.

    The private path keeps the suite's own parallelism out of the picture: an update
    against the tracked path rewrote a file that `check` here, tests/test_harness_lab_gate
    at import, and scripts/harness_lab_gate.py inside a round all read, so the restore in
    `finally` raced readers in other workers.
    """
    private = tmp_path / ".architecture-baseline.json"
    before = BASELINE.read_text(encoding="utf-8") if BASELINE.is_file() else None
    r = _run("baseline:update", "--baseline", str(private))
    assert r.returncode == 0, r.stderr
    assert private.is_file()
    snap = json.loads(private.read_text(encoding="utf-8"))
    assert isinstance(snap.get("perRule"), dict) and snap["perRule"]
    r2 = _run("check", "--baseline", str(private))
    assert r2.returncode == 0, f"stdout={r2.stdout}\nstderr={r2.stderr}"
    after = BASELINE.read_text(encoding="utf-8") if BASELINE.is_file() else None
    assert after == before, "a private-baseline update touched the tracked file"
