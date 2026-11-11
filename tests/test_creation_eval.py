"""The creation eval set (Creator task #51) — the asset and its validator.

The headline is that Ephe builds broad things across many capability classes, so the
claim needs a number per class. That number can only come from a set whose cases are
checkable, so this file guards the set itself before any engine is spent on it: every
case must say which category it proves, which end-state checks decide it, and which
capability it names — and a case that would grade a turn the platform cannot observe
is refused at load time.

The turn half of a case is the golden contract (`core/plugin_golden.py`): one JSONL
line with `id`, `input`, `expect` and the `mode`/`privileges`/`tools` keys that say
which turn the harness has to build. What this module adds is the end-state half —
the created bundle read back through the platform's own loaders, and a browser that
reports whether the surface actually mounted.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_cases():
    from evals.creation_eval import load_cases

    return load_cases()


def test_the_set_loads_through_the_golden_validator() -> None:
    """GIVEN evals/creation/cases.jsonl WHEN the set is loaded
    THEN every case parses as a golden case and runs as a Creator turn."""
    cases = _load_cases()
    assert len(cases) >= 20, "the claim needs a number per class, and 20 cases is the floor"
    assert all(case["mode"] == "creator" for case in cases), (
        "a creation case without mode creator grades a turn the engine was never in"
    )


def test_a_withheld_refusal_case_grades_on_a_turn_that_names_the_missing_step() -> None:
    """GIVEN creation-04 and creation-24, whose grant does not cover the call they watch
    WHEN a turn reports the missing step and runs nothing
    THEN the golden turn half grades them, with no engine and no denial line.

    The two cases were the paid run's class 4a: their turn never has the call in the
    array (`core.tools.creator_guard.filter_offer` withholds it), so a grader that
    demanded an error line for it could never pass them. The refusal the product
    promises is the missing step named in prose (`CREATOR_MODE_GUARD`) plus an empty
    staging root, which `staging_empty` reads back.
    """
    from core.plugin_golden import grade

    cases = {case["id"]: case for case in _load_cases()}
    for cid, privilege in (("creation-04", "files"), ("creation-24", "code")):
        transcript = (
            f"I cannot take that step: it needs the '{privilege}' permission, which "
            "this session does not hold.\n[EPHE-TOOL-EVENTS]\n"
        )
        assert grade(cases[cid], transcript), cid


def test_every_capability_category_carries_cases() -> None:
    """GIVEN the set WHEN the categories are counted
    THEN each of the six carries at least three cases, so a class has a rate and
    not one lucky run."""
    from evals.creation_eval import CATEGORIES, census

    counts = census(_load_cases())
    for category in CATEGORIES:
        assert counts.get(category, 0) >= 3, f"{category} is too thin to report a rate for"
    assert set(counts) == set(CATEGORIES), (
        f"a case lives outside the categories the copy is allowed to name: {sorted(counts)}"
    )


def test_a_case_without_a_category_is_refused(tmp_path: Path) -> None:
    """GIVEN a case line with no category WHEN the set is loaded from it
    THEN loading raises instead of quietly reporting a class nobody asked about."""
    from evals.creation_eval import load_cases

    path = _write_cases(
        tmp_path,
        [{"id": "creation-1", "input": "Build me a widget that shows the clock", "expect": _expect()}],
    )
    with pytest.raises(ValueError, match="category"):
        load_cases(path)


def test_a_case_naming_a_check_the_harness_does_not_have_is_refused(tmp_path: Path) -> None:
    """GIVEN a case that asks for a check nobody implements WHEN it is loaded
    THEN loading raises, so no receipt can print a verdict for a check that never ran."""
    from evals.creation_eval import load_cases

    path = _write_cases(
        tmp_path,
        [
            _case(
                "creation-1",
                "widget",
                checks=["manifest_valid", "teleport_user_desktop"],
            )
        ],
    )
    with pytest.raises(ValueError, match="teleport_user_desktop"):
        load_cases(path)


def test_a_case_with_no_end_state_check_is_refused(tmp_path: Path) -> None:
    """GIVEN a case whose checks are empty WHEN it is loaded
    THEN loading raises — an answer that describes a bundle is not a bundle."""
    from evals.creation_eval import load_cases

    path = _write_cases(tmp_path, [_case("creation-1", "widget", checks=[])])
    with pytest.raises(ValueError, match="checks"):
        load_cases(path)


def test_every_case_demands_that_the_loader_read_its_bundle(tmp_path: Path) -> None:
    """GIVEN a case that never asks whether the manifest reads WHEN it is loaded
    THEN loading raises: a bundle the scanner would quarantine cannot pass."""
    from evals.creation_eval import load_cases

    path = _write_cases(tmp_path, [_case("creation-1", "widget", checks=["mounts"])])
    with pytest.raises(ValueError, match="manifest_valid"):
        load_cases(path)


def test_a_bundle_case_expects_exactly_one_bundle(tmp_path: Path) -> None:
    """GIVEN a bundle case that says its turn leaves two bundles WHEN it is loaded
    THEN loading refuses: the end-state instrument resolves one staged bundle, so a
    second one makes the verdict unattributable."""
    from evals.creation_eval import load_cases

    case = _case("creation-15", "widget", checks=["manifest_valid"], privileges=["files"])
    case["expect"]["bundles"] = 2
    with pytest.raises(ValueError, match="bundles"):
        load_cases(_write_cases(tmp_path, [case]))


def test_a_bundle_case_cannot_expect_an_empty_staging_folder(tmp_path: Path) -> None:
    """GIVEN a bundle case that says its turn leaves nothing WHEN it is loaded
    THEN loading refuses, because each check reads the bundle it says does not exist."""
    from evals.creation_eval import load_cases

    case = _case("creation-16", "widget", checks=["manifest_valid"], privileges=["files"])
    case["expect"]["bundles"] = 0
    with pytest.raises(ValueError, match="bundles"):
        load_cases(_write_cases(tmp_path, [case]))


def test_a_refused_turn_cannot_expect_a_bundle(tmp_path: Path) -> None:
    """GIVEN a refusal case that says its turn leaves a bundle WHEN it is loaded
    THEN loading refuses: nothing staged is the whole verdict of a refused turn."""
    from evals.creation_eval import load_cases

    case = _denial_case("creation-17", "widget")
    case["expect"]["bundles"] = 1
    with pytest.raises(ValueError, match="bundles"):
        load_cases(_write_cases(tmp_path, [case]))


def test_the_bundle_count_has_to_be_a_whole_number(tmp_path: Path) -> None:
    """GIVEN a case whose bundle count is text WHEN it is loaded
    THEN loading refuses rather than comparing a string to a number later."""
    from evals.creation_eval import load_cases

    case = _case("creation-18", "widget", checks=["manifest_valid"], privileges=["files"])
    case["expect"]["bundles"] = "one"
    with pytest.raises(ValueError, match="bundles"):
        load_cases(_write_cases(tmp_path, [case]))


def test_the_bundle_count_defaults_from_the_expected_kind() -> None:
    """GIVEN a case silent about its bundle count WHEN the count is read
    THEN a bundle turn means one and a refusal means none, the two shapes the
    end-state checks can attribute."""
    from evals.creation_eval import expected_bundles

    assert expected_bundles(_case("creation-19", "widget")) == 1
    assert expected_bundles(_denial_case("creation-20", "widget")) == 0


def test_every_shipped_case_says_how_many_bundles_its_turn_leaves() -> None:
    """GIVEN the shipped set WHEN each case's bundle count is read
    THEN every line states it, and it is the one shape its checks can grade."""
    from evals.creation_eval import expected_bundles

    for case in _load_cases():
        refused = case["expect"]["kind"] == "tool_refused"
        assert "bundles" in case["expect"], (
            f"{case['id']} leaves its bundle count implicit; the end state it grades "
            "has to say how many folders it reads"
        )
        assert expected_bundles(case) == (0 if refused else 1), case["id"]


def test_the_two_bundle_turns_now_ask_for_one_bundle() -> None:
    """GIVEN the two turns the paid run left two bundles for WHEN their prompts are read
    THEN each asks for one bundle, which is what its checks grade."""
    cases = {case["id"]: case for case in _load_cases()}
    for cid in ("creation-17", "creation-18"):
        case = cases[cid]
        assert case["expect"]["bundles"] == 1, cid
        assert "one" in case["input"].lower().split(), (
            f"{cid} asks for work without saying it is one bundle: {case['input']!r}"
        )


def test_a_declared_family_is_asked_for_in_the_case_prompt() -> None:
    """GIVEN a case that grades a declared family WHEN its prompt is read
    THEN the prompt names the family and asks for a tool, so the bundle is asked for
    the thing the check grades."""
    import re

    for case in _load_cases():
        declared = (case.get("capabilities") or {}).get("declared", [])
        if not declared:
            continue
        text = case["input"].lower()
        assert "tool" in text, f"{case['id']} grades a family without asking for a tool"
        for family in declared:
            assert re.search(rf"\b{re.escape(family)}\b", text), (
                f"{case['id']} grades {family!r} as declared and the prompt never "
                "names the family"
            )


def test_a_capability_prompt_asks_for_the_family_and_spells_no_tool_name() -> None:
    """GIVEN a case that grades a declared family WHEN its prompt is read
    THEN the prompt asks for a tool of the bundle's own and marks the family, and it
    spells no tool name: `capability_declared` grades the family the bundle serves, so a
    prompt that hands over the tool name hands over the answer."""
    import re

    for case in _load_cases():
        declared = (case.get("capabilities") or {}).get("declared", [])
        if not declared:
            continue
        text = case["input"]
        spans = set(re.findall(r"`([^`]+)`", text))
        spelled = sorted(spans - set(declared))
        assert not spelled, (
            f"{case['id']} spells {spelled} in its prompt; a declared-family case asks "
            "for the family and lets the bundle name the tool that carries it"
        )
        snake_case = sorted(set(re.findall(r"\b[a-z][a-z0-9]*_[a-z0-9_]+\b", text)))
        assert not snake_case, (
            f"{case['id']} spells the tool name(s) {snake_case} in its prompt, so its "
            "capability_declared row is readable off the ask"
        )
        for family in declared:
            assert re.search(rf"`{re.escape(family)}`", text), (
                f"{case['id']} grades {family!r} as declared and never marks the family "
                "in the prompt"
            )


def test_a_case_cannot_grade_a_refusal_and_the_loader_on_one_bundle(tmp_path: Path) -> None:
    """GIVEN a case that asks for an undeclared-family refusal and the loader's answer
    WHEN it is loaded THEN loading refuses: one manifest cannot both pass
    `core.plugin_tools_contract.validate_tools` and carry the family that call rejects."""
    from evals.creation_eval import load_cases

    for case in _load_cases():
        if "capability_undeclared_refused" in case["checks"]:
            assert "manifest_valid" not in case["checks"], (
                f"{case['id']} asks the loader to accept and refuse one manifest"
            )

    case = _case(
        "creation-21",
        "form-tool",
        checks=["manifest_valid", "capability_undeclared_refused"],
        capabilities={"declared": [], "undeclared": ["shell"]},
        privileges=["files"],
    )
    with pytest.raises(ValueError, match="capability_undeclared_refused"):
        load_cases(_write_cases(tmp_path, [case]))


def test_an_undeclared_refusal_probe_is_graded_on_that_check_alone(tmp_path: Path) -> None:
    """GIVEN a case whose only check is the undeclared-family refusal WHEN it is loaded
    THEN it loads: the bundle it reads has to fail the loader, so the loader's own check
    has no place in that line."""
    from evals.creation_eval import load_cases

    case = _case(
        "creation-23",
        "form-tool",
        checks=["capability_undeclared_refused"],
        capabilities={"undeclared": ["shell"]},
        privileges=["files"],
    )
    assert [item["id"] for item in load_cases(_write_cases(tmp_path, [case]))] == ["creation-23"]


def test_a_refusal_must_name_a_capability_the_platform_confines(tmp_path: Path) -> None:
    """GIVEN a case that expects a refusal for a name no layer enforces WHEN it is loaded
    THEN loading raises — `report == enforced` is the platform rule, and a check that
    cannot be refused by anything would print a pass it never earned."""
    from evals.creation_eval import load_cases

    path = _write_cases(
        tmp_path,
        [
            _case(
                "creation-1",
                "form-tool",
                checks=["manifest_valid", "capability_undeclared_refused"],
                capabilities={"declared": [], "undeclared": ["read-the-users-mail"]},
            )
        ],
    )
    with pytest.raises(ValueError, match="read-the-users-mail"):
        load_cases(path)


def test_a_named_capability_must_be_the_one_the_case_checks(tmp_path: Path) -> None:
    """GIVEN a case that declares a capability it never checks WHEN it is loaded
    THEN loading raises, both ways round: the grant and the verdict have to agree."""
    from evals.creation_eval import load_cases

    orphan_grant = _write_cases(
        tmp_path,
        [
            _case(
                "creation-2",
                "dashboard",
                checks=["manifest_valid"],
                capabilities={"declared": ["read"], "undeclared": []},
            )
        ],
    )
    with pytest.raises(ValueError, match="capability_declared"):
        load_cases(orphan_grant)

    bare_verdict = _write_cases(
        tmp_path,
        [_case("creation-3", "dashboard", checks=["manifest_valid", "capability_declared"])],
    )
    with pytest.raises(ValueError, match="declared"):
        load_cases(bare_verdict)


def test_a_denial_case_is_graded_on_what_it_left_behind(tmp_path: Path) -> None:
    """GIVEN a case whose turn is meant to be refused WHEN it is loaded
    THEN its checks are the ones a refusal can answer: nothing was staged. A denial
    case that still asks for a mount would be graded on a bundle that never existed."""
    from evals.creation_eval import load_cases

    wrong_shape = _write_cases(
        tmp_path,
        [
            _denial_case(
                "creation-9",
                "widget",
                checks=["manifest_valid", "surface_files"],
            )
        ],
    )
    with pytest.raises(ValueError, match="staging_empty"):
        load_cases(wrong_shape)

    path = _write_cases(tmp_path, [_denial_case("creation-10", "widget")])
    assert [case["id"] for case in load_cases(path)] == ["creation-10"]


def test_a_built_bundle_may_not_also_be_a_denial(tmp_path: Path) -> None:
    """GIVEN a case that expects work done and empty staging in the same breath
    THEN loading raises — the two verdicts describe different turns."""
    from evals.creation_eval import load_cases

    path = _write_cases(
        tmp_path,
        [_case("creation-11", "utility", checks=["manifest_valid", "staging_empty"])],
    )
    with pytest.raises(ValueError, match="staging_empty"):
        load_cases(path)


def test_the_rubric_documents_every_check_the_cases_may_ask_for() -> None:
    """GIVEN the check vocabulary WHEN the rubric is read
    THEN it names every check by its exact key, so the copy that explains the number
    is measured against the instrument that produced it."""
    from evals.creation_eval import CHECKS, RUBRIC_PATH

    text = RUBRIC_PATH.read_text(encoding="utf-8")
    missing = [name for name in CHECKS if name not in text]
    assert not missing, f"the rubric does not describe these checks: {missing}"


def test_the_rubric_documents_the_bundle_count() -> None:
    """GIVEN the end-state rules WHEN the rubric is read
    THEN it names the count field and the one-bundle shape those checks grade."""
    from evals.creation_eval import RUBRIC_PATH

    text = RUBRIC_PATH.read_text(encoding="utf-8")
    assert "expect.bundles" in text, "the rubric does not describe the bundle count"
    assert "one bundle" in text, "the rubric does not say what the count defaults to"


def test_the_rubric_does_not_claim_every_prompt_supplies_its_data() -> None:
    """GIVEN the paths three prompts name WHEN the rubric's supply claim is read
    THEN it names those paths as resources no turn creates, instead of claiming that
    every case supplies the data its prompt names."""
    from evals.creation_eval import RUBRIC_PATH

    text = RUBRIC_PATH.read_text(encoding="utf-8")
    assert "Every case supplies the data its prompt names" not in text, (
        "the rubric claims every prompt's data is supplied, while creation-14, -17 and "
        "-23 each name a path no turn creates"
    )
    for path in ("data/metrics.csv", "records/expenses.csv", "notes/"):
        assert path in text, f"the rubric does not name the path {path} a prompt names"
    assert "no turn creates" in text, (
        "the rubric does not say the named paths are resources the bundle acts on"
    )


def test_the_bundle_count_is_the_loader_contract_and_the_checks_count_folders() -> None:
    """GIVEN the bundle count WHEN its two layers are read
    THEN `expected_bundles` says it is the loader's reader and names the check layer
    that counts staged folders itself, and the rubric says the same, so the field cannot
    be taken for dead."""
    from evals import creation_checks
    from evals.creation_eval import RUBRIC_PATH, expected_bundles

    source = Path(creation_checks.__file__).read_text(encoding="utf-8")
    assert "expected_bundles" not in source, (
        "evals.creation_checks now reads expect.bundles; the rubric and the docstring "
        "have to stop calling the loader the only reader"
    )
    doc = expected_bundles.__doc__ or ""
    assert "evals.creation_checks" in doc, (
        "the bundle count's docstring does not name the layer that counts folders itself"
    )
    assert "staged folders" in doc, (
        "the bundle count's docstring does not say the check layer counts the folders"
    )
    text = RUBRIC_PATH.read_text(encoding="utf-8")
    assert "evals.creation_checks" in text, (
        "the rubric does not tell the next reader that the check layer counts one "
        "staged folder on its own"
    )


def test_the_rubric_defers_the_name_counts_to_the_layers_that_measure_them() -> None:
    """GIVEN the rubric's claim about served names WHEN the document is read
    THEN it names the measuring functions and pins no number of its own, so the count
    is read from `default_reserved_names()` and the activation scan."""
    import re

    from evals.creation_eval import RUBRIC_PATH

    text = RUBRIC_PATH.read_text(encoding="utf-8")
    assert "default_reserved_names()" in text, (
        "the rubric does not name the kernel rail's source for the name count"
    )
    assert "name_counts()" in text, (
        "the rubric does not name the function that measures the two totals"
    )
    assert not re.search(r"\b\d+ names\b", text), (
        "the rubric pins a hand-typed name count; the source measures it"
    )


def test_the_name_counts_are_read_from_the_layers_that_hold_the_names() -> None:
    """GIVEN the two rails that hold a served name WHEN the counts are asked for
    THEN each total equals the layer's own answer, so a receipt quotes a measurement."""
    from core.plugin_registry import scan_tool_activations
    from core.tools.dynamic_registry import default_reserved_names
    from evals.creation_eval import name_counts

    counts = name_counts()
    assert counts["reserved"] == len(default_reserved_names())
    assert counts["contributed"] == len(scan_tool_activations(None).owners)


def test_the_census_carries_the_name_counts_it_measures(capsys) -> None:
    """GIVEN the receipt-shaped census WHEN it is printed
    THEN the two totals arrive with the measured values, so a number in a receipt comes
    from the layer that holds it."""
    from evals.creation_eval import main, name_counts

    assert main(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["names"] == name_counts()


def test_the_asset_is_one_json_object_per_line(tmp_path: Path) -> None:
    """GIVEN the shipped set WHEN its lines are parsed by hand
    THEN each line is an object whose id carries the creation prefix — the shape the
    golden loader refuses, so a hand-edited row cannot slip past it."""
    from evals.creation_eval import CASES_PATH

    lines = [line for line in CASES_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines, "the shipped set is empty"
    for line in lines:
        raw = json.loads(line)
        assert isinstance(raw, dict)
        assert raw["id"].startswith("creation-")


def test_the_mount_checks_are_the_browser_checks() -> None:
    """GIVEN the set's own mount names WHEN the browser half derives its rows
    THEN both name the same three checks, so a rename on one side cannot leave the
    other grading a check that no longer exists."""
    from evals.creation_checks import BROWSER_CHECKS
    from evals.creation_eval import MOUNT_CHECKS

    assert set(MOUNT_CHECKS) == set(BROWSER_CHECKS), (
        f"the mount checks {sorted(MOUNT_CHECKS)} and the browser checks "
        f"{sorted(BROWSER_CHECKS)} have drifted apart"
    )


def test_every_check_has_a_reachability_rule_naming_its_call() -> None:
    """GIVEN the check vocabulary WHEN the reachability table is read
    THEN every check whose subject a call produces has a generating call, and every call
    is a name the privilege gate can rule on - a check added without a rule would load
    without anyone saying which grant reaches it.

    Two checks have no generating call on purpose, and the set names them: `staging_empty`
    reads a refusal's empty folder, and `offer_matches_grant` reads the array the grant
    produced before a call exists (class 4a/4d, 2026-11-11). Both exceptions are declared
    in `GRANT_CHECKS`, so a third one cannot join them by being forgotten here.
    """
    from core.tools.creator_guard import judge
    from evals.creation_eval import CHECK_CALLS, CHECKS, DENIAL_CHECK, GRANT_CHECKS

    assert GRANT_CHECKS == {"offer_matches_grant"}, (
        f"the checks with no generating call are {sorted(GRANT_CHECKS)}; the reachability "
        "rule below is written for exactly one of them"
    )
    assert set(CHECK_CALLS) == set(CHECKS) - {DENIAL_CHECK} - set(GRANT_CHECKS), (
        "the reachability table and the check vocabulary disagree"
    )
    for call in sorted(set(CHECK_CALLS.values())):
        _privilege, basis = judge(call)
        assert basis != "unlisted", f"{call!r} is not a name the privilege gate rules on"


def test_the_harness_makes_the_call_the_mount_checks_are_read_through() -> None:
    """GIVEN the three mount checks WHEN their generating call is asked for
    THEN it is a call no bench turn approves, so it is the harness that makes it and the
    turn's grant is not the thing that reaches those checks (ticket #161)."""
    from core.plugin_golden import BENCH_NEVER_APPROVES
    from evals.creation_eval import CHECK_CALLS, HARNESS_CALLS, MOUNT_CHECKS

    mount_calls = frozenset(CHECK_CALLS[name] for name in MOUNT_CHECKS)
    assert HARNESS_CALLS == mount_calls, (
        "the harness calls have to be exactly the ones the mount checks are read behind"
    )
    assert HARNESS_CALLS <= BENCH_NEVER_APPROVES, (
        f"{sorted(HARNESS_CALLS - BENCH_NEVER_APPROVES)} would be a turn's call, so the "
        "turn's grant would have to reach the mount checks"
    )


def test_a_case_whose_grant_cannot_reach_a_check_is_refused(tmp_path: Path) -> None:
    """GIVEN a case holding only `code` that asks for a check a turn needs files for
    WHEN it is loaded THEN loading refuses, naming the check, the privilege it needs and
    the gate the privilege was read from."""
    from core.tools.creator_guard import judge
    from evals.creation_eval import load_cases

    path = _write_cases(tmp_path, [_case("creation-12", "widget", checks=["manifest_valid"])])
    privilege, source = judge("create_plugin_scaffold")
    with pytest.raises(ValueError, match="creation-12") as caught:
        load_cases(path)
    message = str(caught.value)
    assert "creation-12" in message, "the refusal has to name the case"
    assert "manifest_valid" in message, "the refusal has to name the check"
    assert privilege in message, "the refusal has to name the privilege it needs"
    assert "core.tools.creator_guard" in message, "the refusal has to name its source"
    from evals.creation_eval import CHECK_CALLS

    assert CHECK_CALLS["manifest_valid"] == "create_plugin_scaffold", (
        f"the table has to route manifest_valid through the call that writes the manifest: {source}"
    )


def test_a_creator_case_with_no_declared_grant_is_refused(tmp_path: Path) -> None:
    """GIVEN a creator case that declares no privileges at all WHEN it is loaded
    THEN loading refuses with its own message: the run writes the line's privileges into
    the consent store, so a missing key is an empty grant, and the turn it describes
    cannot stage the bundle its checks read."""
    from evals.creation_eval import load_cases

    case = _case("creation-14", "widget", checks=["manifest_valid"])
    case.pop("privileges")
    path = _write_cases(tmp_path, [case])
    with pytest.raises(ValueError, match="declares no privileges"):
        load_cases(path)


def test_a_files_only_case_may_ask_for_a_mount_check(tmp_path: Path) -> None:
    """GIVEN a case holding only files that asks for the mount
    WHEN it is loaded THEN it loads: the harness installs the staged bundle, so the
    install's own privilege is not a grant the turn is asked to hold."""
    from evals.creation_eval import load_cases

    path = _write_cases(
        tmp_path,
        [_case("creation-13", "widget", checks=["manifest_valid", "mounts"], privileges=["files"])],
    )
    assert [case["id"] for case in load_cases(path)] == ["creation-13"]


def test_the_shipped_mount_cases_holding_only_files_stay_valid() -> None:
    """GIVEN the shipped set WHEN it loads THEN the files-only cases that ask for a mount
    check are accepted, and there are 19 of them: the number is the ticket's fact, and it
    is pinned so a later edit cannot quietly make the set of reachable cases smaller."""
    from evals.creation_eval import MOUNT_CHECKS

    files_only = [
        case for case in _load_cases()
        if set(case.get("privileges") or ()) == {"files"}
        and MOUNT_CHECKS & set(case["checks"])
    ]
    assert len(files_only) == 19, (
        f"{len(files_only)} files-only cases ask for a mount check, not 19: "
        f"{[case['id'] for case in files_only]}"
    )


def _expect() -> dict:
    return {"kind": "tool_use", "any": ["create_plugin_scaffold"]}


def _case(cid: str, category: str, *, checks=None, capabilities=None, privileges=None) -> dict:
    case = {
        "id": cid,
        "category": category,
        "input": f"Build the {category} described here so the set has something to grade.",
        "expect": _expect(),
        "mode": "creator",
        "privileges": ["code"] if privileges is None else privileges,
        "tools": ["create_plugin_scaffold", "write_plugin_source", "verify_plugin_bundle"],
    }
    case["checks"] = ["manifest_valid"] if checks is None else checks
    if capabilities is not None:
        case["capabilities"] = capabilities
    return case


def _denial_case(cid: str, category: str, *, checks=None) -> dict:
    case = _case(cid, category)
    case["privileges"] = ["code"]
    case["expect"] = {
        "kind": "tool_refused",
        "any": ["create_plugin_scaffold"],
        "reason": "files",
    }
    case["checks"] = ["staging_empty"] if checks is None else checks
    return case


def _write_cases(tmp_path: Path, cases: list[dict]) -> Path:
    path = tmp_path / "cases.jsonl"
    path.write_text("".join(json.dumps(case) + "\n" for case in cases), encoding="utf-8")
    return path
