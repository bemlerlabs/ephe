"""Ephe · Creator — the creation eval set (task #51).
evals/creation_eval.py

The headline says Ephe builds broad things. A headline like that needs a number per
capability class, and a number needs cases that can be checked by a machine. This
module owns the set and the rules that keep it honest before a single token is spent:

  * one JSONL line per case, in the golden contract (`core/plugin_golden.py`), so the
    turn half — `expect`, `mode`, `privileges`, `tools` — is graded by the code that
    already grades every plugin matrix;
  * an end-state half that says what the harness reads back from the bundle the turn
    produced, because an answer describing a widget is not a widget;
  * a bundle count per case (`expect.bundles`), because one staged folder is the only end
    state the checks can attribute, and a line that asks for two bundles is refused here,
    while `evals.creation_checks` counts the staged folders itself;
  * a reachability rule over the grant: a check whose subject only the turn can produce
    has to be paid for by `privileges`, while the checks read behind the harness install
    are reached by the harness itself (task #161), so the files-only cases stay valid;
  * a category per case, and a rate per category in the receipt, so a class that
    cannot pass shows up as work in the plan instead of copy in a marketing page.

A refusal is only allowed to be measured where a layer actually refuses. The kernel
declares which tool families a bundle may activate (`core.capability_policy`), and the
consent gate holds the three Creator privileges, so those two are the vocabulary here.
The `ui.capabilities` names are deliberately absent: every row of
`core.plugin_ui_capabilities.UI_CAPABILITY_ENFORCEMENT` still reads `enforced=False`,
and a check built on them would print a pass for confinement nobody enforces yet.

Run the set with `python evals/creation_eval.py --help`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.plugin_golden import load_golden

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "evals" / "creation" / "cases.jsonl"
RUBRIC_PATH = ROOT / "evals" / "creation" / "rubric.md"

#: The id prefix the golden loader insists on, kept here so the asset and its tests
#: name one number instead of two.
ID_PREFIX = "creation"

#: The floor the claim is built on. Below this a category has a count, not a rate.
MIN_CASES = 20
MIN_PER_CATEGORY = 3

CATEGORIES: tuple[str, ...] = ("widget", "game", "scene3d", "dashboard", "form-tool", "utility")

#: The end-state the harness can read back from a created bundle.
CHECKS: tuple[str, ...] = (
    "manifest_valid",
    "surface_files",
    "capability_declared",
    "capability_undeclared_refused",
    "staging_empty",
    "mounts",
    "no_console_errors",
    "survives_reload",
    "state_bridge_used",
)

#: Every bundle case has to ask this, because the platform's own loader is the floor a
#: staged tree has to clear before anything else about it is interesting.
REQUIRED_CHECK = "manifest_valid"

#: The one check a refused turn can answer.
DENIAL_CHECK = "staging_empty"

#: How many bundles a case says its turn leaves. The end-state instrument resolves one
#: staged folder, so a bundle turn leaves one; a refusal leaves none, which is the
#: absence `staging_empty` measures. A line states the number in `expect.bundles`; a
#: line that omits it takes the default for its expected kind.
DEFAULT_BUNDLES = 1
REFUSED_BUNDLES = 0

#: The end states that only exist in a running app, once the staged bundle has been
#: installed and its mount is served. They are named here, beside the check vocabulary,
#: because the reachability rule below reads "the harness makes this call" off this set;
#: `evals.creation_checks.BROWSER_CHECKS` derives its rows from the offline split instead,
#: and `tests/test_creation_eval.py` pins the two sets equal so a rename cannot drift
#: one away from the other.
MOUNT_CHECKS: frozenset[str] = frozenset({"mounts", "no_console_errors", "survives_reload"})

#: The call that has to succeed before each check can read a subject. The privilege is
#: deliberately absent: it is read from `core.tools.creator_guard.judge` - the one
#: function the tool loop refuses on - so a re-ruling in the gate reaches this table
#: without a second name list to update. `staging_empty` has no row because its subject
#: is a refused call.
CHECK_CALLS: dict[str, str] = {
    "manifest_valid": "create_plugin_scaffold",
    "surface_files": "create_plugin_scaffold",
    "capability_declared": "create_plugin_scaffold",
    "capability_undeclared_refused": "create_plugin_scaffold",
    "state_bridge_used": "write_plugin_source",
    "mounts": "install_plugin_bundle",
    "no_console_errors": "install_plugin_bundle",
    "survives_reload": "install_plugin_bundle",
}

#: The calls the harness makes on a case's behalf. Derived from `MOUNT_CHECKS`, so a
#: fourth mount check forces its generating call into the same ruling: `install_plugin_bundle`
#: is the one path a staged folder takes to becoming loadable, and a bench turn never
#: approves it (`core.plugin_golden.BENCH_NEVER_APPROVES`), which is why the harness does
#: (task #161, `evals.creation_runner.install_and_enable` with `actor="eval"`).
HARNESS_CALLS: frozenset[str] = frozenset(CHECK_CALLS[name] for name in MOUNT_CHECKS)


def check_reachability() -> dict[str, tuple[str, str]]:
    """The derived table: check -> (generating call, privilege that call asks for).

    The privilege half is read from `core.tools.creator_guard.judge`, never restated here,
    so the table follows the gate instead of describing it a second time.
    """
    return {name: (call, _privilege_of(call)[0]) for name, call in CHECK_CALLS.items()}


def _privilege_of(call: str) -> tuple[str, str]:
    """The privilege a call asks for, and the gate ruling behind it, read from the gate."""
    from core.tools.creator_guard import judge

    return judge(call)


def _refusable() -> frozenset[str]:
    """Names a refusal can be attributed to, read from the layer that enforces them."""
    from core.plugin_manifest import KNOWN_TOOL_FAMILIES

    return frozenset(KNOWN_TOOL_FAMILIES)


def load_cases(path: Path | None = None) -> list[dict]:
    """Read the set fail-closed: the golden rules first, then the end-state rules.

    One broken line is an error, and a case whose criteria the harness cannot execute
    is a broken line — it would otherwise land in the receipt as a verdict it never
    measured.
    """
    source = path or CASES_PATH
    cases = load_golden(source, ID_PREFIX)
    for case in cases:
        _validate_end_state(case)
    return cases


def expected_bundles(case: dict) -> int:
    """How many bundles a case says its turn leaves, defaulted from its expected kind.

    A bundle turn means one and a refused turn means none. A line states the number in
    `expect.bundles`; one that omits it takes the default for its kind. This function is
    the only reader, and it is the loader's: the validator below calls it, so a number
    that contradicts the kind is refused before a receipt can describe an end state the
    instrument cannot attribute. The grader does not read it - `evals.creation_checks`
    counts the staged folders itself and accepts exactly one - so the field is a stated
    contract the set enforces at load time, not a second count the checks would honour.
    """
    expect = case.get("expect")
    if not isinstance(expect, dict):
        raise ValueError(f"{case.get('id')}: expect must be an object with a kind")
    fallback = REFUSED_BUNDLES if expect.get("kind") == "tool_refused" else DEFAULT_BUNDLES
    count = expect.get("bundles", fallback)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError(
            f"{case.get('id')}: expect.bundles must be a whole number of bundles, "
            f"got {count!r}"
        )
    return count


def name_counts() -> dict[str, int]:
    """The two served-name totals a receipt quotes, read from the layers that hold them.

    `default_reserved_names()` answers for the kernel dispatch map and the live MCP
    catalog, and `scan_tool_activations(None).owners` for the names the shipped
    bundles contribute. Nothing here restates either number: a checkout that adds a
    tool moves both the measurement and the receipt.
    """
    from core.plugin_registry import scan_tool_activations
    from core.tools.dynamic_registry import default_reserved_names

    return {
        "reserved": len(default_reserved_names()),
        "contributed": len(scan_tool_activations(None).owners),
    }


def _validate_end_state(case: dict) -> None:
    cid = case["id"]
    category = case.get("category")
    if category not in CATEGORIES:
        raise ValueError(f"{cid}: category {category!r} is not one of {', '.join(CATEGORIES)}")

    checks = case.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError(f"{cid}: checks must be a non-empty list of names from {', '.join(CHECKS)}")
    unknown = sorted({name for name in checks if name not in CHECKS})
    if unknown:
        raise ValueError(f"{cid}: checks the harness does not have: {', '.join(unknown)}")

    bundles = expected_bundles(case)
    _validate_capabilities(case)
    _validate_turn_shape(case, bundles)

    if case.get("mode") != "creator":
        raise ValueError(f"{cid}: a creation case runs with mode 'creator'")

    _validate_reachability(case)


def _validate_turn_shape(case: dict, bundles: int) -> None:
    """Keep the answer-grade, the bundle count, and the end-state grade on one turn.

    A refusal expects no bundle, so its checks are about the empty staging directory;
    a bundle expects the loader's answer and exactly one staged folder. A case whose
    only check is the undeclared-family refusal is a rejection probe: the bundle it
    reads has to fail the loader, so that check stands alone. A case that asks for two
    bundles, or for two verdicts, is two cases.
    """
    cid = case["id"]
    checks = case["checks"]
    refused = case["expect"]["kind"] == "tool_refused"
    if refused:
        if bundles != REFUSED_BUNDLES:
            raise ValueError(
                f"{cid}: a refused turn leaves no bundle, so expect.bundles is "
                f"{REFUSED_BUNDLES}, got {bundles}"
            )
        if checks != [DENIAL_CHECK]:
            raise ValueError(f"{cid}: a refused turn is graded on {DENIAL_CHECK} alone")
        return
    if bundles != DEFAULT_BUNDLES:
        raise ValueError(
            f"{cid}: a turn that leaves a bundle leaves exactly {DEFAULT_BUNDLES}, so "
            f"expect.bundles is {DEFAULT_BUNDLES}, got {bundles} - the staged end state "
            "reads one bundle and a second one cannot be attributed to the turn"
        )
    if DENIAL_CHECK in checks:
        raise ValueError(f"{cid}: {DENIAL_CHECK} belongs to a refused turn")
    if "capability_undeclared_refused" in checks:
        if checks != ["capability_undeclared_refused"]:
            raise ValueError(
                f"{cid}: capability_undeclared_refused is a rejection probe graded on that "
                "check alone - the bundle it reads has to fail the loader, so "
                f"{REQUIRED_CHECK} and surface_files cannot sit beside it"
            )
        return
    if REQUIRED_CHECK not in checks:
        raise ValueError(f"{cid}: every bundle case asks whether the loader reads it ({REQUIRED_CHECK})")


def _validate_capabilities(case: dict) -> None:
    """A grant has to be graded, and a graded refusal has to name a real vocabulary."""
    cid = case["id"]
    checks = case["checks"]
    caps = case.get("capabilities")
    declared: list[str] = []
    undeclared: list[str] = []
    if caps is not None:
        if not isinstance(caps, dict):
            raise ValueError(f"{cid}: capabilities must be an object with declared and undeclared")
        for key, into in (("declared", declared), ("undeclared", undeclared)):
            names = caps.get(key, [])
            if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
                raise ValueError(f"{cid}: capabilities.{key} must be a list of names")
            into.extend(names)
        unknown = sorted({name for name in declared + undeclared if name not in _refusable()})
        if unknown:
            raise ValueError(
                f"{cid}: capabilities no layer refuses by name: {', '.join(unknown)} - "
                f"refusable: {', '.join(sorted(_refusable()))}"
            )

    if "capability_declared" in checks and not declared:
        raise ValueError(f"{cid}: the capability_declared check needs a non-empty capabilities.declared")
    if "capability_undeclared_refused" in checks and not undeclared:
        raise ValueError(
            f"{cid}: the capability_undeclared_refused check needs a non-empty capabilities.undeclared"
        )
    if caps is not None and not (
        {"capability_declared", "capability_undeclared_refused"} & set(checks)
    ):
        raise ValueError(
            f"{cid}: capabilities {sorted(declared + undeclared)} name a grant no check grades - "
            "add capability_declared or drop them"
        )


def _validate_reachability(case: dict) -> None:
    """Refuse a case whose own grant cannot reach a check it asks for.

    A check's subject is produced by a call, and there are two makers of that call:

    * the turn's authoring calls are paid for by `privileges` - a case holding only
      `code` cannot stage a bundle, so a check that reads one would grade a folder that
      turn was never allowed to leave, and the case is refused here;
    * the install call behind the mount checks is made by the harness for every case
      (task #161), and no bench turn approves it at all
      (`core.plugin_golden.BENCH_NEVER_APPROVES`), so the case's grant - which is the
      turn's grant - neither covers it nor has to. That is why the 19 files-only cases
      that ask for a mount stay valid.

    A case that declares no `privileges` at all is the same fact one step earlier:
    `evals/creation_run.py` writes `case.get("privileges") or []` into the consent store,
    so a missing key is an empty grant. It is refused with its own message.
    The privilege itself is read from `core.tools.creator_guard.judge`, the same answer
    the tool loop refuses on, and the refusal names the check, the call, the privilege
    and that source.
    """
    if case["expect"]["kind"] == "tool_refused":
        # A refused turn is graded on the call it did not make; `staging_empty` names
        # that absence, so no privilege has to reach it.
        return
    cid = case["id"]
    granted = frozenset(case.get("privileges") or ())
    for name in case["checks"]:
        call = CHECK_CALLS[name]
        if call in HARNESS_CALLS:
            continue
        privilege, basis = _privilege_of(call)
        if basis == "unlisted":
            raise ValueError(
                f"{cid}: check {name!r} is produced by {call!r}, which "
                f"core.tools.creator_guard.judge cannot rule on, so the set cannot say "
                "which grant reaches it"
            )
        if not privilege or privilege in granted:
            continue
        if not granted:
            raise ValueError(
                f"{cid}: a creator case that asks for {name!r} declares no privileges, so "
                f"the turn holds no grant and cannot make {call!r} ({privilege!r} "
                f"privilege, source: core.tools.creator_guard, {basis} ruling) - declare "
                "the grant the check needs or drop the check"
            )
        raise ValueError(
            f"{cid}: check {name!r} cannot be reached by a turn holding "
            f"{sorted(granted) or 'no privileges'} - it is produced by {call!r}, which "
            f"asks for the {privilege!r} privilege (source: core.tools.creator_guard, "
            f"{basis} ruling); grant {privilege!r} or drop the check"
        )


def census(cases: list[dict]) -> dict[str, int]:
    """How many cases each category carries — the denominator of every rate printed."""
    counts = {category: 0 for category in CATEGORIES}
    for case in cases:
        counts[case["category"]] += 1
    return counts


def main(argv: list[str] | None = None) -> int:
    """The set's own doctor: what the asset claims and what the harness can grade."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cases", type=Path, default=CASES_PATH, help="the JSONL set to read")
    parser.add_argument("--json", action="store_true", help="print the census as JSON")
    args = parser.parse_args(argv)

    cases = load_cases(args.cases)
    counts = census(cases)
    names = name_counts()
    if args.json:
        print(json.dumps(
            {"cases": len(cases), "categories": counts, "names": names},
            ensure_ascii=False,
        ))
        return 0
    print(f"{len(cases)} creation cases in {args.cases.relative_to(ROOT)}")
    for category, seen in counts.items():
        floor = "ok" if seen >= MIN_PER_CATEGORY else f"below {MIN_PER_CATEGORY}"
        print(f"  {category:<12} {seen:>3}  {floor}")
    print(
        f"  names        {names['reserved']:>3} reserved, "
        f"{names['contributed']:>3} contributed"
    )
    if len(cases) < MIN_CASES:
        print(f"  the set is below its floor of {MIN_CASES} cases")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
