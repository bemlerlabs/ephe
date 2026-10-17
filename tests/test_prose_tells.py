"""Ephe — the prose-tells census keeps the hand-written rule measurable.

Owner rule 2026-10-09 (`AGENTS.md`, "Writing quality"): generated-code tells have to
stay out of developer prose, and a rule nobody measures is a wish.
`scripts/prose_inventory.py` finds the tells in one file, `scripts/prose_tells.py`
turns that into a census over tracked source and a gate on a committed baseline. These
tests drive both with an injected file list and reader, so no git checkout, no server
and no model is involved.

The planted tells live inside string literals, which is what the instrument itself
proves is not developer prose — so this file carries the defect it hunts without
scoring one.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TELLS_PATH = REPO / "scripts" / "prose_tells.py"


def _load_tells():
    spec = importlib.util.spec_from_file_location("prose_tells_under_test", TELLS_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pt = _load_tells()
CLEAN_PY = "def load(name):\n    return store[name]\n"


def scan_py(prose: str) -> set[str]:
    """The classes this Python source earns, for a file outside every protection."""
    found = pt.rules.findings_for("core/order.py", CLEAN_PY + prose)
    return {f.cls for f in found}


def gate(main: Path, tree: dict[str, str]) -> tuple[Path, dict[str, str]]:
    baseline = main / "baseline.json"
    code = pt.main(
        ["--update", "--baseline", str(baseline)],
        list_files=lambda: sorted(tree),
        read_text=lambda rel: tree[rel],
    )
    assert code == 0
    return baseline, tree


def test_ui_label_inside_a_literal_is_not_developer_prose():
    source = 'const label = "Löschen ▸ ✓ ─────";  // ── nothing ─────\n'
    classes = {f.cls for f in pt.rules.findings_for("app/src/lib/x.ts", source)}
    assert "decorative" in classes
    assert len([f for f in pt.rules.findings_for("app/src/lib/x.ts", source) if f.row == 1]) == 1


def test_decorative_rule_bullet_and_filler_head_are_tells():
    assert scan_py("# ──── section ────\nx = 1\n") == {"decorative"}
    assert scan_py("# Note: nothing new here.\nx = 1\n") == {"filler-block"}
    assert scan_py("# TODO: implement the retry\nx = 1\n") == {"filler-block"}
    assert scan_py("# This function returns early\nx = 1\n") == {"filler-block"}
    assert scan_py("# a robust, seamless design\nx = 1\n") == {"marketing-adjective"}


def test_a_docstring_that_only_shouts_the_function_name_back_is_a_tell():
    assert pt.rules.restates("Load the config.", "load_config")
    assert pt.rules.restates("Config loader", "config_loader")
    assert not pt.rules.restates("Load the config, refusing a file that is world-writable.", "load_config")
    assert not pt.rules.restates("GIVEN a stale row WHEN loading THEN the cache is empty", "load_stale_rows")
    found = pt.rules.findings_for("core/order.py", "def load_config(name):\n    \"\"\"Load the config.\"\"\"\n    return 1\n")
    assert [f.cls for f in found] == ["restated-docstring"]


def test_a_comment_that_says_what_the_next_line_does_is_a_tell():
    assert pt.rules.narrates("# Returns the rows", "return rows")
    assert not pt.rules.narrates("# Returns the rows, newest first (measured 20 rows per page)", "return rows")
    found = pt.rules.findings_for("core/order.py", "def pick():\n    # Returns the rows\n    return rows\n")
    assert [f.cls for f in found] == ["narrating-comment"]


def test_one_rhetorical_turn_is_a_boundary_and_the_next_is_a_tell():
    once = "# the store is a cache, not a source of truth\nx = 1\n"
    twice = once + "# the label is German, not translated\ny = 2\n"
    assert scan_py(once) == set()
    assert len([f for f in pt.rules.findings_for("core/order.py", CLEAN_PY + twice) if f.cls == "stacked-rhetoric"]) == 1


def test_a_short_body_annotated_line_by_line_is_a_tell():
    source = (
        "def area(w, h):\n"
        "    # width in metres\n"
        "    a = w\n"
        "    # height in metres\n"
        "    b = h\n"
        "    # the product\n"
        "    return a * b\n"
    )
    found = pt.rules.findings_for("core/order.py", source)
    assert [f.cls for f in found] == ["symmetric-block"]


def test_a_repeated_banner_counts_the_repeats_not_the_survivor():
    banner = "# Ephe - one tool per file, nothing more here.\n"
    texts = {f"core/tools/t{i}.py": banner + "x = 1\n" for i in range(4)}
    assert pt.header_duplicates(texts) == {"core/tools/t1.py", "core/tools/t2.py", "core/tools/t3.py"}
    shebang = {"core/a.py": "#!/usr/bin/env python3\nx = 1\n", "core/b.py": "#!/usr/bin/env python3\ny = 2\n"}
    assert pt.header_duplicates(shebang) == set()


def test_the_long_comment_voice_is_measured_and_left_out_of_the_ratchet():
    voice = "".join(f"# line {i} of the paragraph that explains the invariant\n" for i in range(6))
    assert pt.essay_blocks("core/order.py", voice) == 1
    assert pt.rules.findings_for("core/order.py", voice) == []


def test_baseline_is_refused_in_any_shape_that_could_hide_growth(tmp_path):
    bad = tmp_path / "prose-tells-baseline.json"
    bad.write_text(json.dumps({"policy": "prose-tells-ratchet", "version": 1, "files": {}, "exempt": []}), encoding="utf-8")
    assert pt.main(["--strict", "--baseline", str(bad)]) == 2
    bad.write_text(
        json.dumps({"policy": "prose-tells-ratchet", "version": 1, "total": 0, "files": {"skills/x.md": 1}}),
        encoding="utf-8",
    )
    assert pt.main(["--strict", "--baseline", str(bad)]) == 2


def test_the_gate_holds_at_the_baseline_and_breaks_on_a_planted_tell(tmp_path):
    tree = {"core/order.py": '"""Order rows, newest first, and never a world-writable file."""\n\n\ndef pick():\n    return rows\n'}
    baseline, _ = gate(tmp_path, tree)
    assert pt.main(["--strict", "--baseline", str(baseline)], list_files=lambda: sorted(tree), read_text=lambda rel: tree[rel]) == 0
    grown = dict(tree)
    grown["server/x.py"] = '"""Server rows, and the reader keeps them ordered."""\n\n\n# ──── section ────\n'
    assert pt.main(["--strict", "--baseline", str(baseline)], list_files=lambda: sorted(grown), read_text=lambda rel: grown[rel]) == 1
    lowered = {k: v for k, v in tree.items() if k != "core/order.py"}
    assert pt.main(["--update", "--baseline", str(baseline)], list_files=lambda: sorted(lowered), read_text=lambda rel: lowered[rel]) == 0


def test_update_refuses_to_raise_the_baseline(tmp_path):
    tree = {"core/order.py": "x = 1  # plain\n"}
    baseline, _ = gate(tmp_path, tree)
    grown = {"core/order.py": "x = 1  # plain\ny = 2  # ──── rule ────\n"}
    assert pt.main(["--update", "--baseline", str(baseline)], list_files=lambda: sorted(grown), read_text=lambda rel: grown[rel]) == 1
    assert json.loads(baseline.read_text(encoding="utf-8"))["total"] == 0


GONE = "core/gone.py"
#: one decorative rule — a tell the ratchet scores, planted inside a literal so this file stays clean
WITH_A_TELL = '"""Rows, ordered."""\n\n\n# ──── section ────\n'
QUIET = "x = 1  # plain\n"


def test_a_baseline_entry_for_a_path_the_tree_no_longer_holds_refuses_the_strict_pass(tmp_path, capsys):
    """GIVEN a baseline that counts a file the tree has dropped WHEN --strict runs THEN exit 2.

    `evaluate` compares the union of the baseline and the measured keys, so the dead entry scores
    `old = N, new = 0` and lands in `lowered`. Nothing fails, and the number stays in the JSON as a
    budget for whoever recreates that path.
    """
    tree = {"core/order.py": QUIET, GONE: WITH_A_TELL}
    baseline, _ = gate(tmp_path, tree)
    assert pt.counts_for([GONE], lambda rel: tree[rel])[GONE] == 1
    living = {k: v for k, v in tree.items() if k != GONE}
    code = pt.main(
        ["--strict", "--baseline", str(baseline)],
        list_files=lambda: sorted(living),
        read_text=lambda rel: living[rel],
    )
    assert code == 2, "a stale entry must not read as a tree that is under its budget"
    assert GONE in capsys.readouterr().err


def test_a_recreated_path_gets_no_inheritance_once_the_entry_is_pruned(tmp_path):
    """The order the refusal protects: prune while the tree is cleaner, then the path starts at zero."""
    tree = {"core/order.py": QUIET, GONE: WITH_A_TELL}
    baseline, _ = gate(tmp_path, tree)
    living = {k: v for k, v in tree.items() if k != GONE}
    assert pt.main(
        ["--update", "--baseline", str(baseline)],
        list_files=lambda: sorted(living),
        read_text=lambda rel: living[rel],
    ) == 0
    grown = dict(living)
    grown[GONE] = WITH_A_TELL
    assert pt.main(
        ["--strict", "--baseline", str(baseline)],
        list_files=lambda: sorted(grown),
        read_text=lambda rel: grown[rel],
    ) == 1


def test_a_path_that_is_present_and_clean_is_lowered_rather_than_refused(tmp_path, capsys):
    """The rule is about paths outside the tree; a quiet file is the ratchet working as intended."""
    tree = {GONE: WITH_A_TELL}
    baseline, _ = gate(tmp_path, tree)
    quiet = {GONE: QUIET}
    assert pt.main(
        ["--strict", "--baseline", str(baseline)],
        list_files=lambda: sorted(quiet),
        read_text=lambda rel: quiet[rel],
    ) == 0
    assert "below" in capsys.readouterr().out


def test_the_github_root_is_measured_and_records_a_baseline_row():
    """`.github/` is a measured root, and the baseline carries a row for its tells.

    The root sat outside `PROSE_ROOTS` for most of the tree's life, so the CI-operator
    prose in it was never counted. Adding the root without the rows would red the gate on
    tells that were always there, so the two have to move together.
    """
    assert ".github" in pt.PROSE_ROOTS
    rows = {rel for rel in pt.load_baseline(pt.BASELINE_DEFAULT) if rel.startswith(".github/")}
    assert rows, "the .github root is measured but the baseline records none of its tells"
