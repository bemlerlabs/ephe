"""`scripts/citation_check.py` over planted trees, so the gate is provable rather than trusted.

The instrument reads comments and docstrings of a tree, so every plant here is a directory of
small files: no git checkout, no network, no product import. The cases follow the two shapes the
gate exists for - a comment pointing at a page that was never written, and a dated name in the
style the suite grew - plus the exclusions that keep it a gate and not noise: a fixture path a
test invents in a string, and a deeper root whose path merely contains a scanned prefix.

One case runs the gate over this repository. That is the claim `ci-gates.yml` makes on every
push, and it is the reason the gate shipped with zero findings: a check that reports its own
fixtures is worse than no check.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GATE_PATH = REPO / "scripts" / "citation_check.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("citation_check_under_test", GATE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module through this map
    spec.loader.exec_module(module)
    return module


gate = _load_gate()

#: The document the planted comments cite. Its absence is what a case asserts.
PHANTOM_PAGE = "docs/NEVER_WRITTEN.md"
#: A page that exists and is cited by a comment in a plant.
REAL_PAGE = "docs/REAL_PAGE.md"


def plant(root: Path, *, extra_python: str = "", extra_yaml: str = "") -> Path:
    """Write a two-file tree: one real document, one module whose comments cite things.

    `extra_python` is appended to the module's comments, `extra_yaml` to the workflow's, so a
    case adds one citation without rebuilding the tree.
    """
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (root / REAL_PAGE).write_text("# Real page\n\nTen lines of it.\n", encoding="utf-8")
    (root / "scripts" / "carrier.py").write_text(
        '"""Cites the real page, which is allowed: docs/REAL_PAGE.md holds the rule."""\n'
        "\n"
        "# The budget comes from docs/REAL_PAGE.md and nothing else.\n"
        f"{extra_python}\n"
        "VALUE = 1\n",
        encoding="utf-8",
    )
    (root / ".github" / "workflows" / "carrier.yml").write_text(
        "# The leg runs the gate described in docs/REAL_PAGE.md.\n"
        "jobs:\n  leg:\n    runs-on: ubuntu-latest\n"
        f"{extra_yaml}\n",
        encoding="utf-8",
    )
    return root


def findings_of(root: Path) -> list[str]:
    findings, _scanned = gate.scan(root)
    return [str(finding) for finding in findings]


class TestACitationIsCheckedAgainstTheTree:
    def test_a_clean_tree_passes_and_the_gate_says_so(self, tmp_path, capsys):
        # GIVEN a tree whose comments cite only files it contains
        plant(tmp_path)
        # WHEN the gate runs over it
        code = gate.main(["--root", str(tmp_path)])
        # THEN it passes and counts what it read
        assert code == 0, capsys.readouterr().err
        assert "0 problem(s)" in capsys.readouterr().out

    def test_a_comment_naming_a_page_that_was_never_written_is_refused_by_name(self, tmp_path):
        # GIVEN a comment citing a document this tree does not contain
        plant(tmp_path, extra_python=f"# The design is in {PHANTOM_PAGE}.")
        # WHEN the tree is scanned
        findings = findings_of(tmp_path)
        # THEN the refusal names the citing file, its line and the cited path
        assert len(findings) == 1, findings
        assert "scripts/carrier.py:" in findings[0]
        assert PHANTOM_PAGE in findings[0]
        assert "dangling citation" in findings[0]

    def test_a_dated_name_is_refused_even_when_the_page_exists(self, tmp_path):
        # GIVEN a page whose name carries a date stamp, and a comment that cites it truthfully
        plant(tmp_path, extra_python="# The number comes from docs/MEASURED_2026-11-24.md.")
        (tmp_path / "docs" / "MEASURED_2026-11-24.md").write_text("# Dated\n", encoding="utf-8")
        # WHEN the tree is scanned
        findings = findings_of(tmp_path)
        # THEN the naming style alone is the refusal, marker or no marker
        assert len(findings) == 1, findings
        assert "docs/MEASURED_2026-11-24.md" in findings[0]
        assert "dated citation" in findings[0]

    def test_a_pointer_past_the_end_of_a_real_file_is_refused(self, tmp_path):
        # GIVEN a comment citing a line range the real document does not reach
        plant(tmp_path, extra_python=f"# See {REAL_PAGE}:12-99 for the table.")
        # WHEN the tree is scanned
        findings = findings_of(tmp_path)
        # THEN the refusal says how long the file actually is
        assert len(findings) == 1, findings
        assert "past the end" in findings[0]
        assert "3 line(s)" in findings[0]

    def test_a_workflow_comment_is_held_to_the_same_rule(self, tmp_path):
        # GIVEN a workflow comment citing an absent page
        plant(tmp_path, extra_yaml=f"#  capacity note: {PHANTOM_PAGE}")
        # WHEN the tree is scanned
        findings = findings_of(tmp_path)
        # THEN the workflow file is named as the carrier
        assert len(findings) == 1, findings
        assert ".github/workflows/carrier.yml:" in findings[0]


class TestWhatTheGateDoesNotTouch:
    def test_a_fixture_name_in_a_string_literal_is_no_citation(self, tmp_path):
        # GIVEN a test file that writes a fixture named after a document nobody wrote
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_fixture.py").write_text(
            '"""Pins the reader over a fixture tree."""\n'
            "\n"
            "def test_reads_the_fixture(tmp_path):\n"
            f'    (tmp_path / "{PHANTOM_PAGE}").write_text("x", encoding="utf-8")\n'
            '    assert (tmp_path / "docs").is_dir()\n',
            encoding="utf-8",
        )
        plant(tmp_path)
        # WHEN the tree is scanned
        # THEN the invented path in the string is not read as a claim
        assert findings_of(tmp_path) == []

    def test_a_comment_in_a_test_is_still_a_claim(self, tmp_path):
        # GIVEN the same fixture named in a comment instead of a string
        tests = tmp_path / "tests"
        tests.mkdir()
        (tests / "test_fixture.py").write_text(
            '"""Pins the reader over a fixture tree."""\n'
            "\n"
            "\n"
            "def test_reads_the_fixture(tmp_path):\n"
            f"    # the fixture is {PHANTOM_PAGE}, written by the case below\n"
            '    assert True\n',
            encoding="utf-8",
        )
        plant(tmp_path)
        # WHEN the tree is scanned
        findings = findings_of(tmp_path)
        # THEN the comment is judged, because an author vouches for it
        assert len(findings) == 1, findings
        assert "tests/test_fixture.py:" in findings[0]

    def test_a_path_under_a_deeper_root_is_that_path_and_not_the_prefix_inside_it(self, tmp_path):
        """A citation rooted deeper is judged as that path, whole."""
        plant(tmp_path, extra_python="# The budget tool is app/scripts/bundle_budget.py.")
        assert findings_of(tmp_path) == []

    def test_a_front_end_source_beside_a_cited_page_stays_a_front_end_source(self, tmp_path):
        # GIVEN a comment naming a `.tsx` file and a real page, in one line
        plant(tmp_path, extra_python="# The route table lives in app/src/App.tsx beside docs/REAL_PAGE.md.")
        assert findings_of(tmp_path) == []


class TestTheOneExemption:
    def test_a_named_absent_path_is_allowed_and_the_next_one_is_not(self, tmp_path):
        # GIVEN a fence that names two absent paths and marks only one of them
        plant(
            tmp_path,
            extra_python=(
                "# core/gone.py is gone; citation:absent core/gone.py - the fence forbids it.\n"
                "# core/also_gone.py is gone too."
            ),
        )
        # WHEN the tree is scanned
        findings = findings_of(tmp_path)
        # THEN the marked path passes and the unmarked one is still a finding
        assert len(findings) == 1, findings
        assert "core/also_gone.py" in findings[0]

    def test_a_marker_does_not_lift_the_dated_refusal(self, tmp_path):
        # GIVEN a dated citation beside a marker naming it
        plant(
            tmp_path,
            extra_python=(
                "# citation:absent docs/MEASURED_2026-11-24.md - historical.\n"
                "# The number comes from docs/MEASURED_2026-11-24.md."
            ),
        )
        # WHEN the tree is scanned
        findings = findings_of(tmp_path)
        # THEN both mentions are refused: the marker buys nothing against a stamp, and the
        # marker line itself carries the stamped name it was written to excuse
        assert len(findings) == 2, findings
        assert all("dated citation" in finding for finding in findings), findings
        assert all("docs/MEASURED_2026-11-24.md" in finding for finding in findings), findings

    def test_a_marker_only_reaches_inside_its_own_comment_block(self, tmp_path):
        # GIVEN a marker in one comment and the same path cited in another
        plant(
            tmp_path,
            extra_python=(
                "# citation:absent core/gone.py - the fence forbids it.\n"
                "def f():\n"
                "    # core/gone.py was deleted\n"
                "    return 1\n"
            ),
        )
        # WHEN the tree is scanned
        findings = findings_of(tmp_path)
        # THEN the second comment is judged on its own
        assert len(findings) == 1, findings
        assert "core/gone.py" in findings[0]


class TestTheTreeItShipsWith:
    def test_this_repository_is_clean_today(self):
        """The claim `ci-gates.yml` makes on every push, measured here."""
        findings, scanned = gate.scan(REPO)
        # THEN the gate has no finding of its own to explain, and it read real files
        assert scanned > 900, f"only {scanned} files scanned; the roots moved?"
        assert [str(finding) for finding in findings] == []
