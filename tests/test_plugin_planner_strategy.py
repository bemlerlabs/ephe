"""PLAN-P1 — a plan strategy a plugin declares (`capabilities.planner`).

The seam this file pins: a version 2 manifest names one plan strategy with a step budget
and a step schema; the plugin runtime registers it from the same scan the tool gate reads;
`core/ephe_plan.py` resolves it where the plan core used to fix its strategy in a module
constant; and the kernel is the fallback whenever nothing is declared, the declaring
bundle is switched off, or two bundles contradict each other.

What the kernel keeps, and this file therefore checks under a declared strategy too: the
loop, the repair budget (`MAX_REPAIRS_PER_STEP`), the abort, the rendered block and the
stream payload. `tests/fixtures/plugins/domain-plan/` is the declaring bundle used
throughout; each test copies it into a plugin root it owns.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "plugins"


def _valid(**planner: object) -> dict:
    """A v2 manifest that declares the fixture's strategy; `planner` replaces the section."""
    descriptor: dict = {
        "strategy": "domain-plan",
        "step_budget": 6,
        "step_schema": ["title", "evidence"],
        "description": "A plan dialect for one domain.",
    }
    descriptor.update(planner)
    descriptor = {key: value for key, value in descriptor.items() if value is not None}
    manifest = {
        "manifest_version": 2,
        "name": "acme-plan",
        "version": "1.0.0",
        "description": "A declared plan strategy.",
        "publisher": {"name": "Acme"},
        "license": "MIT",
        "engines": {"ephe": ">=0.6.0"},
        "permissions": {"tool_families": [], "data_roots": []},
    }
    manifest["capabilities"] = {"planner": descriptor}
    return manifest


def _resolved():
    from core.ephe_plan import plan_strategy

    return plan_strategy()


def _write(root: Path, manifest: dict) -> Path:
    directory = root / str(manifest["name"])
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ephe-plugin.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    return directory


@pytest.fixture(autouse=True)
def _no_strategy_pin(monkeypatch):
    from core.ephe_plan import ENV_PLAN_STRATEGY

    monkeypatch.delenv(ENV_PLAN_STRATEGY, raising=False)


@pytest.fixture()
def contract_root(tmp_path):
    """A folder per test for the manifests that have to be refused."""
    root = tmp_path / "contract"
    root.mkdir()
    return root


def _error(root: Path, manifest: dict) -> str | None:
    from core.plugin_manifest import load_manifest

    return load_manifest(_write(root, manifest))[1]


@pytest.fixture()
def roots(tmp_path, monkeypatch):
    """A plugin root the test owns, holding the fixture strategy."""
    from core import plugin_manifest, plugin_runtime

    plugins = tmp_path / "plugins"
    plugins.mkdir()
    shutil.copytree(FIXTURES / "domain-plan", plugins / "domain-plan")
    monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", plugins)
    plugin_runtime.invalidate_ownership_cache()
    yield plugins
    plugin_runtime.invalidate_ownership_cache()


def _disable(plugin_id: str) -> None:
    from core import plugin_runtime

    plugin_runtime.invalidate_ownership_cache()
    plugin_runtime.lifecycle().set_enabled(plugin_id, False)


class TestContract:
    def test_the_fixture_manifest_validates_and_carries_the_strategy(self) -> None:
        from core.plugin_manifest import load_manifest
        from core.plugin_planner_contract import planner_claim

        manifest, error = load_manifest(FIXTURES / "domain-plan")
        assert error is None
        strategy = planner_claim(manifest)
        assert strategy is not None
        assert strategy.plugin_id == "domain-plan"
        assert strategy.strategy_id == "domain-plan"
        assert strategy.step_budget == 5
        assert strategy.step_schema == ("title", "evidence")

    def test_a_version_1_manifest_cannot_declare_a_strategy(self, contract_root) -> None:
        manifest = _valid()
        manifest["manifest_version"] = 1
        assert _error(contract_root, manifest) == "capabilities: manifest_version 2 required"

    def test_the_planner_section_has_to_be_an_object(self, contract_root) -> None:
        manifest = _valid()
        manifest["capabilities"]["planner"] = []
        assert _error(contract_root, manifest) == "capabilities.planner: object expected"

    def test_an_unknown_planner_field_is_refused(self, contract_root) -> None:
        manifest = _valid(step_limit=3)
        assert (
            _error(contract_root, manifest)
            == "capabilities.planner: unknown field(s): step_limit"
        )

    def test_a_missing_strategy_id_is_refused(self, contract_root) -> None:
        manifest = _valid(strategy=None)
        assert (
            _error(contract_root, manifest)
            == "capabilities.planner.strategy: lowercase slug expected (a-z0-9-)"
        )

    def test_a_strategy_id_is_a_slug(self, contract_root) -> None:
        manifest = _valid(strategy="Domain Plan")
        assert (
            _error(contract_root, manifest)
            == "capabilities.planner.strategy: lowercase slug expected (a-z0-9-)"
        )

    def test_a_kernel_strategy_id_cannot_be_taken(self, contract_root) -> None:
        manifest = _valid(strategy="checklist")
        assert (
            _error(contract_root, manifest)
            == "capabilities.planner.strategy: 'checklist' is a kernel strategy id"
        )

    def test_a_strategy_id_has_a_length_ceiling(self, contract_root) -> None:
        manifest = _valid(strategy="p" * 41)
        assert (
            _error(contract_root, manifest)
            == "capabilities.planner.strategy: at most 40 characters expected"
        )

    def test_a_boolean_step_budget_is_not_a_number(self, contract_root) -> None:
        manifest = _valid(step_budget=True)
        assert (
            _error(contract_root, manifest)
            == "capabilities.planner.step_budget: a whole number of steps expected"
        )

    def test_a_step_budget_above_the_kernel_ceiling_is_refused(self, contract_root) -> None:
        manifest = _valid(step_budget=9)
        assert (
            _error(contract_root, manifest)
            == "capabilities.planner.step_budget: 9 is outside 4..8 steps"
        )

    def test_a_step_budget_below_the_guard_floor_is_refused(self, contract_root) -> None:
        manifest = _valid(step_budget=3)
        assert (
            _error(contract_root, manifest)
            == "capabilities.planner.step_budget: 3 is outside 4..8 steps"
        )

    def test_a_step_budget_at_the_floor_is_accepted(self, contract_root) -> None:
        manifest = _valid(step_budget=4)
        assert _error(contract_root, manifest) is None

    def test_the_step_schema_has_to_be_a_list(self, contract_root) -> None:
        manifest = _valid(step_schema="title")
        assert (
            _error(contract_root, manifest)
            == "capabilities.planner.step_schema: list of step field names expected"
        )

    def test_an_unknown_step_field_is_refused(self, contract_root) -> None:
        manifest = _valid(step_schema=["title", "owner"])
        assert (
            _error(contract_root, manifest)
            == "capabilities.planner.step_schema: unknown step field(s): owner "
            "(title, evidence, mutating)"
        )

    def test_a_repeated_step_field_is_refused(self, contract_root) -> None:
        manifest = _valid(step_schema=["title", "title"])
        assert (
            _error(contract_root, manifest)
            == "capabilities.planner.step_schema: duplicate step field(s): title"
        )

    def test_a_step_schema_without_a_title_is_refused(self, contract_root) -> None:
        manifest = _valid(step_schema=["evidence"])
        assert (
            _error(contract_root, manifest)
            == "capabilities.planner.step_schema: must name 'title' — "
            "a step without a title is not a step"
        )

    def test_a_blank_description_is_refused(self, contract_root) -> None:
        manifest = _valid(description="  ")
        assert (
            _error(contract_root, manifest)
            == "capabilities.planner.description: non-empty string expected"
        )

    def test_the_defaults_are_the_kernel_numbers(self, contract_root) -> None:
        from core.ephe_plan import MAX_PLAN_STEPS
        from core.plugin_planner_contract import planner_claim
        from core.plugin_manifest import load_manifest

        manifest = _valid(step_budget=None, step_schema=None)
        assert _error(contract_root, manifest) is None
        loaded, _ = load_manifest(contract_root / "acme-plan")
        strategy = planner_claim(loaded)
        assert strategy is not None
        assert strategy.step_budget == MAX_PLAN_STEPS
        assert strategy.step_schema == ("title",)

    def test_an_absent_planner_section_is_fine(self, contract_root) -> None:
        manifest = _valid()
        del manifest["capabilities"]
        assert _error(contract_root, manifest) is None

    def test_an_unknown_capability_section_is_still_refused(self, contract_root) -> None:
        """Widening the vocabulary for planner must not open the section list to typos."""
        manifest = _valid()
        manifest["capabilities"]["vector"] = {}
        assert _error(contract_root, manifest) == "capabilities: unknown section(s): vector"

    def test_the_reserved_ids_agree_with_the_plan_core(self) -> None:
        from core.ephe_plan import KERNEL_STRATEGY_IDS
        from core.plugin_planner_contract import BUILTIN_STRATEGY_IDS

        assert BUILTIN_STRATEGY_IDS == frozenset(KERNEL_STRATEGY_IDS)

    def test_the_step_vocabulary_is_the_plan_cores_own_fields(self) -> None:
        from core.ephe_plan import EpheStep
        from core.plugin_planner_contract import PLAN_STEP_FIELDS

        carrier = set(EpheStep.__dataclass_fields__)
        assert set(PLAN_STEP_FIELDS) <= carrier
        assert "title" in PLAN_STEP_FIELDS


class TestRegistration:
    def test_the_runtime_registers_the_declared_strategy(self, roots) -> None:
        from core import plugin_runtime

        claim = plugin_runtime.plan_strategies().get("domain-plan")
        assert claim is not None
        assert claim.plugin_id == "domain-plan"
        assert claim.step_budget == 5
        assert claim.step_schema == ("title", "evidence")

    def test_an_unknown_strategy_id_is_not_registered(self, roots) -> None:
        from core import plugin_runtime

        assert plugin_runtime.plan_strategies().get("nobody") is None

    def test_two_plugins_claiming_one_id_make_it_contested(self, roots) -> None:
        from core import plugin_manifest, plugin_runtime

        twin = _valid()
        twin["name"] = "twin-plan"
        _write(plugin_manifest.PLUGINS_ROOT_OVERRIDE, twin)
        plugin_runtime.invalidate_ownership_cache()

        table = plugin_runtime.plan_strategies()
        assert table.get("domain-plan") is None
        assert table.contested == ("domain-plan",)
        assert "'twin-plan'" in table.conflict_reason("domain-plan")

    def test_the_conflict_reaches_the_store_view(self, roots) -> None:
        from core import plugin_manifest, plugin_runtime

        twin = _valid()
        twin["name"] = "twin-plan"
        _write(plugin_manifest.PLUGINS_ROOT_OVERRIDE, twin)
        plugin_runtime.invalidate_ownership_cache()

        contested = plugin_runtime.contested_names()["plan_strategies"]
        entry = next(row for row in contested if row["name"] == "domain-plan")
        assert {"domain-plan", "twin-plan"} == {claim["plugin"] for claim in entry["claims"]}

    def test_the_cache_drops_after_a_rescan(self, roots) -> None:
        from core import plugin_manifest, plugin_runtime

        assert plugin_runtime.plan_strategies().get("domain-plan") is not None
        shutil.rmtree(plugin_manifest.PLUGINS_ROOT_OVERRIDE / "domain-plan")
        plugin_runtime.invalidate_ownership_cache()
        assert plugin_runtime.plan_strategies().get("domain-plan") is None


class TestResolutionActive:
    def test_an_active_declaration_resolves(self, roots) -> None:
        from core.ephe_plan import plan_strategy

        strategy = plan_strategy()
        assert strategy.strategy_id == "domain-plan"
        assert strategy.step_budget == 5
        assert strategy.plugin_id == "domain-plan"

    def test_the_step_budget_bounds_a_plan_built_from_titles(self, roots) -> None:
        from core.ephe_plan import EphePlan

        plan = EphePlan.from_titles([f"Step {i} names a file" for i in range(12)])
        assert len(plan.steps) == 5
        assert plan.strategy.strategy_id == "domain-plan"

    def test_the_step_budget_bounds_a_plan_parsed_from_markdown(self, roots) -> None:
        from core.ephe_plan import PLAN_HEADING, EphePlan

        block = PLAN_HEADING + "\n" + "\n".join(f"- [ ] Step {i} reads a file" for i in range(9))
        assert len(EphePlan.from_markdown(block).steps) == 5

    def test_the_step_budget_bounds_the_ledger_mirror(self, roots) -> None:
        from core.ephe_plan import EphePlan

        rows = [{"id": i, "title": f"Row {i}", "status": "pending"} for i in range(9)]
        plan = EphePlan.from_ledger(rows)
        assert plan is not None
        assert len(plan.steps) == 5

    def test_the_plan_records_the_strategy_it_was_built_under(self, roots) -> None:
        from core.ephe_plan import EphePlan

        plan = EphePlan.from_titles(["Read", "Write"])
        assert plan.strategy == _resolved()

    def test_the_rendered_block_keeps_the_one_shape(self, roots) -> None:
        from core.ephe_plan import PLAN_HEADING, EphePlan

        plan = EphePlan.from_titles(["Read the router", "Add the case"])
        assert plan.render().split("\n")[0].startswith(PLAN_HEADING)
        assert all(line.startswith("- [") for line in plan.render().split("\n")[1:])

    def test_the_stream_payload_keeps_its_keys(self, roots) -> None:
        from core.ephe_plan import EphePlan

        payload = EphePlan.from_titles(["Read", "Write"]).as_dict()
        assert set(payload) == {"state", "done", "total", "steps"}

    def test_the_repair_budget_stays_the_kernels(self, roots) -> None:
        from core.ephe_plan import MAX_REPAIRS_PER_STEP, EphePlan

        plan = EphePlan.from_titles(["Read", "Write"])
        plan.start_current()
        for _ in range(MAX_REPAIRS_PER_STEP):
            plan.complete_current(ok=False)
        assert plan.status == "running"
        plan.complete_current(ok=False)
        assert plan.status == "failed"

    def test_the_pin_can_name_the_declared_strategy(self, roots, monkeypatch) -> None:
        from core.ephe_plan import ENV_PLAN_STRATEGY, plan_strategy

        monkeypatch.setenv(ENV_PLAN_STRATEGY, "domain-plan")
        assert plan_strategy().strategy_id == "domain-plan"

    def test_the_pin_can_keep_the_kernel_strategy(self, roots, monkeypatch) -> None:
        from core.ephe_plan import ENV_PLAN_STRATEGY, plan_strategy

        monkeypatch.setenv(ENV_PLAN_STRATEGY, "checklist")
        strategy = plan_strategy()
        assert strategy.strategy_id == "checklist"
        assert strategy.step_budget == 8


class TestResolutionInactive:
    def test_a_switched_off_bundle_takes_its_strategy_with_it(self, roots) -> None:
        from core.ephe_plan import EphePlan, plan_strategy

        _disable("domain-plan")
        assert plan_strategy().strategy_id == "checklist"
        assert len(EphePlan.from_titles([f"Step {i} names a file" for i in range(12)]).steps) == 8

    def test_the_pin_ignores_a_switched_off_bundle(self, roots, monkeypatch, caplog) -> None:
        from core.ephe_plan import ENV_PLAN_STRATEGY, plan_strategy

        _disable("domain-plan")
        monkeypatch.setenv(ENV_PLAN_STRATEGY, "domain-plan")
        assert plan_strategy().strategy_id == "checklist"
        assert any("domain-plan" in record.message for record in caplog.records)


class TestResolutionContradictory:
    def test_two_plugins_on_one_id_leave_the_kernel_strategy(self, roots) -> None:
        from core import plugin_manifest, plugin_runtime
        from core.ephe_plan import plan_strategy

        twin = _valid()
        twin["name"] = "twin-plan"
        _write(plugin_manifest.PLUGINS_ROOT_OVERRIDE, twin)
        plugin_runtime.invalidate_ownership_cache()
        assert plan_strategy().strategy_id == "checklist"

    def test_two_different_dialects_leave_the_kernel_strategy(self, roots) -> None:
        from core import plugin_manifest, plugin_runtime
        from core.ephe_plan import plan_strategy

        other = _valid(strategy="other-plan", step_budget=4)
        other["name"] = "other-plan"
        _write(plugin_manifest.PLUGINS_ROOT_OVERRIDE, other)
        plugin_runtime.invalidate_ownership_cache()
        assert plan_strategy().strategy_id == "checklist"

    def test_the_pin_settles_two_dialects(self, roots, monkeypatch) -> None:
        from core import plugin_manifest, plugin_runtime
        from core.ephe_plan import ENV_PLAN_STRATEGY, plan_strategy

        other = _valid(strategy="other-plan", step_budget=4)
        other["name"] = "other-plan"
        _write(plugin_manifest.PLUGINS_ROOT_OVERRIDE, other)
        plugin_runtime.invalidate_ownership_cache()
        monkeypatch.setenv(ENV_PLAN_STRATEGY, "other-plan")
        strategy = plan_strategy()
        assert (strategy.strategy_id, strategy.step_budget) == ("other-plan", 4)

    def test_the_pin_cannot_pick_a_contested_id(self, roots, monkeypatch, caplog) -> None:
        from core import plugin_manifest, plugin_runtime
        from core.ephe_plan import ENV_PLAN_STRATEGY, plan_strategy

        twin = _valid()
        twin["name"] = "twin-plan"
        _write(plugin_manifest.PLUGINS_ROOT_OVERRIDE, twin)
        plugin_runtime.invalidate_ownership_cache()
        monkeypatch.setenv(ENV_PLAN_STRATEGY, "domain-plan")
        assert plan_strategy().strategy_id == "checklist"
        assert any("claimed by" in record.message for record in caplog.records)

    def test_an_unknown_pin_falls_back_to_the_kernel(self, roots, monkeypatch, caplog) -> None:
        from core.ephe_plan import ENV_PLAN_STRATEGY, plan_strategy

        monkeypatch.setenv(ENV_PLAN_STRATEGY, "nobody")
        assert plan_strategy().strategy_id == "checklist"
        assert any("nobody" in record.message for record in caplog.records)


class TestKernelFallback:
    def test_no_plugin_at_all_keeps_the_kernel_strategy(self, tmp_path, monkeypatch) -> None:
        from core import plugin_manifest, plugin_runtime
        from core.ephe_plan import MAX_PLAN_STEPS, EphePlan, plan_strategy

        empty = tmp_path / "plugins"
        empty.mkdir()
        monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", empty)
        plugin_runtime.invalidate_ownership_cache()
        try:
            strategy = plan_strategy()
            assert strategy.strategy_id == "checklist"
            assert strategy.plugin_id == ""
            assert len(EphePlan.from_titles([f"Step {i} names a file" for i in range(12)]).steps) == MAX_PLAN_STEPS
        finally:
            plugin_runtime.invalidate_ownership_cache()

    def test_a_handed_in_strategy_cannot_raise_the_ceiling(self) -> None:
        """The kernel's ceiling holds even for a strategy no manifest validation saw."""
        from core.ephe_plan import MAX_PLAN_STEPS, EphePlan
        from core.plugin_planner_contract import PlanStrategy

        greedy = PlanStrategy(strategy_id="greedy", step_budget=99, plugin_id="acme")
        plan = EphePlan.from_titles([f"Step {i} names a file" for i in range(20)], greedy)
        assert len(plan.steps) == MAX_PLAN_STEPS

    def test_a_broken_manifest_does_not_break_the_plan(self, tmp_path, monkeypatch) -> None:
        from core import plugin_manifest, plugin_runtime
        from core.ephe_plan import EphePlan

        plugins = tmp_path / "plugins"
        broken = plugins / "broken-plan"
        broken.mkdir(parents=True)
        (broken / "ephe-plugin.json").write_text("{ not json", encoding="utf-8")
        monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", plugins)
        plugin_runtime.invalidate_ownership_cache()
        try:
            assert len(EphePlan.from_titles(["Read", "Write"]).steps) == 2
        finally:
            plugin_runtime.invalidate_ownership_cache()
