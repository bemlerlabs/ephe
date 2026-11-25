"""QG3 seed ↔ GET /api/context/budget contract.

The QG3 case in app/tests/playwright/q-quality.spec.ts intercepts the budget
route with a mirrored payload (QG3_BUDGET_JSON). A payload typed freely into the
spec would survive any rename of the field it pretends to carry and prove
nothing, so this check pins its shape against the real contract:

- the keys of the spec's seed must equal the keys the route returns, taken from
  a live call of context_budget() under the hermetic fixtures, and
- the breakdown category names must come from the route's fixed category
  vocabulary, and
- the seed's numbers must satisfy the route's own identity
  percent == round(estimated_tokens / window_tokens * 100, 2), recomputed here
  as an independent implementation.

Why this reads source files: the seed literal lives in a Playwright spec — a
browser-side file the product and pytest cannot import — and the category
vocabulary exists only in the for-loop tuple of _breakdown(). Both constraints
are cross-runtime contracts with no callable seam on this side, the same reason
tests/test_dev_handle_gate.py reads the shipped bundle. Renaming a field on
either side turns exactly these tests red (the mutation proof).
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "app" / "tests" / "playwright" / "q-quality.spec.ts"
ROUTE_PATH = REPO_ROOT / "server" / "routes" / "context.py"

SEED_START = "// QG3-BUDGET-SEED-START"
SEED_END = "// QG3-BUDGET-SEED-END"


def _seed_payload() -> dict:
    text = SPEC_PATH.read_text(encoding="utf-8")
    start = text.index(SEED_START)
    end = text.index(SEED_END)
    block = text[start:end]
    open_tick = block.index("`")
    close_tick = block.index("`", open_tick + 1)
    return json.loads(block[open_tick + 1 : close_tick])


def _route_category_names() -> list[str]:
    tree = ast.parse(ROUTE_PATH.read_text(encoding="utf-8"))
    fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_breakdown"
    )
    loop = next(node for node in ast.walk(fn) if isinstance(node, ast.For))
    # Reading this shape is the point of the case: a route that stops iterating a literal
    # tuple of pairs has changed the contract this file holds it to.
    assert isinstance(loop.iter, ast.Tuple), "the route no longer iterates a literal tuple of pairs"
    names: list[str] = []
    for element in loop.iter.elts:  # for name, chars in (("Messages", hist), ...)
        assert isinstance(element, ast.Tuple) and len(element.elts) == 2
        value = element.elts[0]
        assert isinstance(value, ast.Constant) and isinstance(value.value, str)
        names.append(value.value)
    return names


@pytest.fixture(scope="module")
def live_keys() -> set[str]:
    from server.routes.context import context_budget

    return set(context_budget().keys())


def test_given_spec_seed_when_checked_then_keys_equal_the_routes_response_keys(live_keys):
    seed = _seed_payload()
    assert set(seed.keys()) == live_keys, (
        "the QG3 seed and context_budget() drifted apart — move spec seed and route "
        "in the same patch (the route's dict is the contract)"
    )


def test_given_route_categories_when_seed_shares_them_then_names_are_from_the_vocabulary():
    names = _route_category_names()
    seed = _seed_payload()
    seeded = [row["name"] for row in seed["breakdown"]]
    assert seeded, "the seed lost its breakdown — QG3 asserts on these rows"
    unknown = [name for name in seeded if name not in names]
    assert not unknown, f"seeded categories outside the route vocabulary: {unknown}"


def test_given_seed_numbers_when_recomputed_then_they_obey_the_routes_identity():
    seed = _seed_payload()
    expected = round(seed["estimated_tokens"] / seed["window_tokens"] * 100, 2)
    assert seed["percent"] == expected, (
        "the route prints round(estimated/window*100, 2); a seed that violates the "
        "identity lets QG3 pass while asserting an impossible number"
    )
    total = sum(row["percent"] for row in seed["breakdown"])
    assert abs(total - 100.0) < 0.05, (
        f"breakdown shares sum to {total}; the seed must stay fully labelled "
        "(QG3's sum check reads these rows from the DOM)"
    )


def test_given_the_seed_block_when_scanned_then_it_stays_inside_its_markers():
    text = SPEC_PATH.read_text(encoding="utf-8")
    assert text.count(SEED_START) == 1 and text.count(SEED_END) == 1
    _seed_payload()  # raises ValueError on a malformed block
