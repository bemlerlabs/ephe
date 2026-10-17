"""Ephe — the four shapes the prose census could not see, each with its plant.

The owner rule of 2026-10-09 (`AGENTS.md`, "Writing quality") is measured by
`scripts/prose_inventory.py` and held by `scripts/prose_tells.py`. Eight classes shipped
with it; four more were added on 2026-10-10 after counting what each one costs this tree,
and one adjective widening went straight into the ratchet because it found nothing there.
Each class below gets the same proof: the plant is found, the bounded version of the same
sentence is not, and the gate either flips over it or stays shut while it is measured only.

Plants live inside string literals, which is what the instrument itself proves is developer
prose — a fixture is a fixture, and this file scores nothing while carrying all of them.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
INVENTORY = REPO / "scripts" / "prose_inventory.py"
WIDE_PATH = REPO / "scripts" / "prose_wide.py"
TELLS_PATH = REPO / "scripts" / "prose_tells.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rules = _load("prose_inventory_under_test", INVENTORY)
pw = _load("prose_wide_under_test", WIDE_PATH)


pt = _load("prose_tells_under_test", TELLS_PATH)


def wide(source: str, path: str = "app/src/lib/a.ts") -> list[pw.Finding]:
    return pw.wide_findings_for(path, source)


def ratcheted(source: str, path: str = "core/order.py") -> list[pw.Finding]:
    return rules.findings_for(path, source)


def rows_file() -> str:
    return '"""Order rows, newest first, capped at the page size the store already holds."""\n\n\ndef pick():\n    return rows\n'


def test_javadoc_that_echoes_the_function_it_sits_over_is_a_tell_now():
    line = "// Gets the user.\nexport function getUser(id: string) {\n  return store.get(id);\n}\n"
    assert [f.cls for f in wide(line)] == [pw.CLIKE_RESTATED_DOC]
    block = "/**\n * Formats a label.\n */\nexport function formatLabel(x: string) {\n  return x;\n}\n"
    assert [f.row for f in wide(block)] == [1]
    method = "class Panel {\n  // Renders the rows\n  renderRows(): void {}\n}\n"
    assert [f.cls for f in wide(method, "app/src/lib/a.ts")] == [pw.CLIKE_RESTATED_DOC]


def test_a_clike_comment_that_bounds_anything_passes_and_a_value_needs_no_rule():
    bounded = (
        "// Gets the user, and refuses a row whose owner left the workspace.\n"
        "export function getUser(id: string) {\n  return id;\n}\n"
    )
    assert wide(bounded) == []
    field = "// The rows.\nconst rows = load();\n"
    assert wide(field) == []
    python = "# Gets the user.\ndef get_user():\n    return 1\n"
    assert wide(python, "core/order.py") == []


def test_the_figure_written_across_two_lines_counts_once_a_file_carries_two():
    one = "x = 1  # the store — not a cache\n"
    assert wide(one, "core/order.py") == []
    twice = "x = 1  # the store — not a cache\ny = 2  # the label — not the value\nz = 3\n"
    assert [f.cls for f in wide(twice, "core/order.py")] == [pw.SPLIT_RHETORIC]
    run_over = (
        "def pick():\n"
        "    # keeps the tier the router asked for,\n"
        "    # not the machine that served it\n"
        "    return tier\n\n"
        "def other():\n"
        "    # reads the row the store wrote,\n"
        "    # not the copy the caller passed\n"
        "    return row\n"
    )
    assert [f.row for f in wide(run_over, "core/order.py")] == [8]
    assert ratcheted(run_over) == []


def test_a_control_keyword_is_no_callable_for_this_rule():
    switch = (
        "export function route(kind: string) {\n"
        "  // Switch on the kind\n"
        "  switch (kind) {\n"
        '    case "a": return 1;\n'
        "  }\n"
        "}\n"
    )
    assert wide(switch) == []


def test_the_comma_form_keeps_the_ratchet_and_the_new_forms_leave_it_alone():
    comma = "x = 1  # the store is a cache, not a source\ny = 2  # the label is German, not translated\n"
    assert [f.cls for f in ratcheted(comma)] == [rules.STACKED_RHETORIC]
    assert ratcheted("x = 1  # the store — not a cache\n") == []


def test_the_adjectives_that_joined_the_ratchet_were_found_nowhere_in_the_tree():
    assert [f.cls for f in ratcheted("x = 1  # a seamlessly ordered reader\n")] == [rules.MARKETING_ADJECTIVE]
    assert [f.cls for f in ratcheted("x = 1  # delve into the rows\n")] == [rules.MARKETING_ADJECTIVE]
    assert ratcheted("x = 1  # leverage the existing gate\n") == []
    assert [f.cls for f in wide("x = 1  # leverage the existing gate\n", "core/order.py")] == [pw.MARKETING_ADJECTIVE_WIDE]


def test_a_banner_wording_counts_the_repeats_from_the_third_file_on():
    line = "# Rows newest first, capped at the page size here.\n"
    three = {f"core/tools/a{i}.py": line + "x = 1\n" for i in range(3)}
    assert [len(v) for v in pw.banner_wordings(three).values()] == [3]
    two = {f"core/tools/a{i}.py": line + "x = 1\n" for i in range(2)}
    assert pw.banner_wordings(two) == {}
    counts, by_class, _ = pw.wide_score(three)
    assert by_class[pw.REPEATED_BANNER] == 2
    assert "core/tools/a0.py" not in counts and counts["core/tools/a2.py"] == 1


def test_brand_line_step_convention_and_pragma_are_never_banners():
    brand = {f"core/b{i}.py": "# Ephe – Bad Liebenzell, Schwarzwald\nx = 1\n" for i in range(4)}
    steps = {f"tests/t{i}.py": "# Given / When / Then, strictly.\nx = 1\n" for i in range(4)}
    order = {f"tests/o{i}.py": "# RULE: tests before implementation.\nx = 1\n" for i in range(4)}
    shebang = {f"scripts/s{i}.sh": "#!/usr/bin/env bash\nset -e\n" for i in range(4)}
    pragma = {f"core/p{i}.py": "# type: ignore[arg-type]\nx = 1\n" for i in range(4)}
    for texts in (brand, steps, order, shebang, pragma):
        assert pw.banner_wordings(texts) == {}


def test_the_gate_breaks_on_a_planted_adjective_and_closes_over_the_fix(tmp_path):
    clean = {"core/order.py": rows_file()}
    baseline = tmp_path / "baseline.json"
    assert pt.main(["--update", "--baseline", str(baseline)], list_files=lambda: sorted(clean), read_text=lambda rel: clean[rel]) == 0
    assert pt.main(["--strict", "--baseline", str(baseline)], list_files=lambda: sorted(clean), read_text=lambda rel: clean[rel]) == 0
    planted = dict(clean)
    planted["server/rows.py"] = "x = 1  # a seamlessly ordered reader\n"
    code = pt.main(["--strict", "--baseline", str(baseline)], list_files=lambda: sorted(planted), read_text=lambda rel: planted[rel])
    assert code == 1
    assert pt.main(["--update", "--baseline", str(baseline)], list_files=lambda: sorted(planted), read_text=lambda rel: planted[rel]) == 1
    fixed = dict(clean)
    fixed["server/rows.py"] = "x = 1  # ordered by the row key, newest first\n"
    assert pt.main(["--strict", "--baseline", str(baseline)], list_files=lambda: sorted(fixed), read_text=lambda rel: fixed[rel]) == 0


def test_a_wide_plant_moves_the_census_and_nothing_in_the_gate(tmp_path):
    clean = {"core/order.py": rows_file()}
    baseline = tmp_path / "baseline.json"
    assert pt.main(["--update", "--baseline", str(baseline)], list_files=lambda: sorted(clean), read_text=lambda rel: clean[rel]) == 0
    planted = dict(clean)
    planted["app/src/lib/a.ts"] = "// Gets the user.\nexport function getUser(id: string) {\n  return id;\n}\n"
    planted["core/util.py"] = "x = 1  # leverage the gate\ny = 2  # the row — not the cache\nz = 3  # the label — not the value\n"
    assert pt.main(["--strict", "--baseline", str(baseline)], list_files=lambda: sorted(planted), read_text=lambda rel: planted[rel]) == 0
    wide_tree = {"core/order.py": rows_file(), "core/util.py": "x = 1  # leverage the gate\n"}
    counts, by_class, _ = pw.wide_score(wide_tree)
    assert by_class[pw.MARKETING_ADJECTIVE_WIDE] == 1
    assert counts["core/util.py"] == 1
    assert ratcheted(wide_tree["core/util.py"]) == []


def test_a_baseline_refuses_to_be_read_in_the_other_scope(tmp_path):
    tree = {"core/order.py": "x = 1  # the row — not the cache\ny = 2  # the label — not the value\n"}
    wide_base = tmp_path / "wide.json"
    assert pt.main(["--update", "--wide", "--baseline", str(wide_base)], list_files=lambda: sorted(tree), read_text=lambda rel: tree[rel]) == 0
    assert json.loads(wide_base.read_text(encoding="utf-8"))["scope"] == pt.MEASURED_SCOPE
    assert pt.main(["--strict", "--baseline", str(wide_base)], list_files=lambda: sorted(tree), read_text=lambda rel: tree[rel]) == 2
    assert pt.main(["--strict", "--wide", "--baseline", str(wide_base)], list_files=lambda: sorted(tree), read_text=lambda rel: tree[rel]) == 0
