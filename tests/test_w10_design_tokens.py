"""The design-token gate `scripts/design_tokens_check.mjs`, held by pytest.

Mirrors `tests/test_r46_architecture_check.py`: a missing baseline is a hint run, and
every ratchet verdict is proved on a private copy under `tmp_path`, never on the
tracked `.design-tokens-baseline.json`. The last test recounts the three axes here in
Python and compares them with the committed snapshot, the anti-drift pin.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts" / "design_tokens_check.mjs"
BASELINE = ROOT / ".design-tokens-baseline.json"
APP_SRC = ROOT / "app" / "src"

# Same three axes and the same patterns the checker holds, so a recount agrees by
# construction rather than by coincidence.
AXES = {
    "radiusArbitrary": re.compile(r"rounded-\[[^\]]+\]"),
    "shadowArbitrary": re.compile(r"shadow-\[[^\]]+\]"),
    "colorLiteral": re.compile(
        r"\[#[0-9a-fA-F]{3,8}\]|\[rgb[^\]]*\]|\[hsl[^\]]*\]|#[0-9a-fA-F]{6}|rgb\([^)]*\)|hsl\([^)]*\)"
    ),
}
SKIP_NAME = re.compile(r"\.(test|spec)\.")
SCANNED_SUFFIXES = {".ts", ".tsx"}
FINDING_KEYS = {"axis", "file", "value", "limit", "severity"}


def run_checker(*args: str) -> subprocess.CompletedProcess[str]:
    """Run the checker from the repo root and capture both streams."""
    return subprocess.run(
        ["node", str(CHECKER), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )


def recount() -> dict[str, int]:
    """Per-axis occurrence tally over app/src, recomputed without the checker."""
    totals = {axis: 0 for axis in AXES}
    for path in sorted(APP_SRC.rglob("*")):
        if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
            continue
        if SKIP_NAME.search(path.name):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for axis, pattern in AXES.items():
            totals[axis] += len(pattern.findall(text))
    return totals


def test_checker_file_exists():
    assert CHECKER.is_file(), "scripts/design_tokens_check.mjs is missing"


def test_check_without_baseline_exits_zero(tmp_path):
    absent = tmp_path / "absent.json"
    done = run_checker("check", "--baseline", str(absent))
    assert done.returncode == 0, f"stdout={done.stdout}\nstderr={done.stderr}"
    assert "baseline=false" in done.stdout, done.stdout
    assert "0 errors" in done.stdout, done.stdout


def test_report_json_contract(tmp_path):
    absent = tmp_path / "absent.json"
    done = run_checker("report", "--baseline", str(absent))
    assert done.returncode == 0, done.stderr
    data = json.loads(done.stdout)
    for key in ("version", "findings", "counts", "perAxis", "baselinePresent"):
        assert key in data, f"report field {key!r} missing"
    assert set(data["perAxis"]) == set(AXES), data["perAxis"]
    assert isinstance(data["findings"], list)
    for finding in data["findings"]:
        assert set(finding) == FINDING_KEYS, f"finding schema drifted: {finding}"


def test_growth_above_the_freeze_is_an_error(tmp_path):
    absent = tmp_path / "absent.json"
    data = json.loads(run_checker("report", "--baseline", str(absent)).stdout)
    per_axis = data["perAxis"]
    assert any(per_axis.values()), "no raw values in this tree; nothing to ratchet"
    private = tmp_path / "frozen.json"
    private.write_text(
        json.dumps(
            {
                "version": data["version"],
                "frozenAt": "1970-01-01T00:00:00.000Z",
                "perAxis": {axis: count - 1 for axis, count in per_axis.items()},
                "total": sum(per_axis.values()),
            }
        ),
        encoding="utf-8",
    )
    done = run_checker("check", "--baseline", str(private))
    assert done.returncode == 1, f"stdout={done.stdout}\nstderr={done.stderr}"
    assert ", 0 hints)" in done.stdout, done.stdout


def test_baseline_update_writes_private_and_leaves_tracked_file(tmp_path):
    private = tmp_path / ".design-tokens-baseline.json"
    tracked_before = BASELINE.read_text(encoding="utf-8")
    done = run_checker("baseline:update", "--baseline", str(private))
    assert done.returncode == 0, done.stderr
    assert private.is_file(), f"private snapshot not written: {done.stdout}"
    snapshot = json.loads(private.read_text(encoding="utf-8"))
    assert set(snapshot) == {"version", "frozenAt", "perAxis", "total"}, snapshot
    assert isinstance(snapshot["perAxis"], dict) and snapshot["perAxis"], snapshot
    follow_up = run_checker("check", "--baseline", str(private))
    assert follow_up.returncode == 0, f"stdout={follow_up.stdout}\nstderr={follow_up.stderr}"
    assert BASELINE.read_text(encoding="utf-8") == tracked_before, (
        "a private-baseline run wrote the tracked .design-tokens-baseline.json"
    )


def test_tracked_baseline_matches_independent_recount():
    snapshot = json.loads(BASELINE.read_text(encoding="utf-8"))
    frozen = snapshot["perAxis"]
    measured = recount()
    assert {axis: frozen.get(axis, 0) for axis in AXES} == measured, (
        f"committed baseline {frozen} drifted from an in-test recount {measured}"
    )
