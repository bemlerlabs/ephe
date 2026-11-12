"""EVAL-P1 — grader presets a plugin declares (`capabilities.evaluator`).

The seam this file pins: a version 2 manifest names up to eight checks, each one a preset
of a kernel grader primitive with the fragment list fixed in the manifest; a case in that
bundle's own suite names the preset in `expect.kind` and passes nothing else; the loader
resolves the preset from the manifest beside the suite and records the primitive on the
case, so a receipt names what the author wrote and what graded it.

What the kernel keeps, and this file therefore checks under a declared preset too: the five
primitives and their argument rules (`core/plugin_evaluator_contract.py`), the pass³
semantics, the case schema, the anti-slop gate and the receipt shape. A bundle cannot add a
primitive, take a kernel kind name, resolve another bundle's preset, or write the loader's
own `matcher` field.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import core.plugin_golden as plugin_golden


def _manifest(kinds: object = None, **evaluator: object) -> dict:
    """A version 2 manifest declaring grader presets; `evaluator` replaces the section."""
    section: dict = dict(evaluator)
    if kinds is not None:
        section["kinds"] = kinds
    return {
        "manifest_version": 2,
        "name": "acme-eval",
        "version": "1.0.0",
        "description": "Declares grader presets for its own golden suite.",
        "publisher": {"name": "Acme"},
        "license": "MIT",
        "engines": {"ephe": ">=0.6.0"},
        "permissions": {"tool_families": [], "data_roots": []},
        "capabilities": {"evaluator": section},
    }


def _kind(**overrides: object) -> dict:
    """One valid preset; `overrides` replaces a field, and None drops it."""
    kind: dict = {
        "id": "no-slop",
        "from": "not_contains",
        "any": ["as an AI", "lorem ipsum"],
        "description": "Placeholder text never reaches the answer.",
    }
    kind.update(overrides)
    return {key: value for key, value in kind.items() if value is not None}


def _write(root: Path, manifest: dict) -> Path:
    directory = root / str(manifest["name"])
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ephe-plugin.json").write_text(
        json.dumps({**manifest, "name": directory.name}), encoding="utf-8"
    )
    return directory


def _error(root: Path, manifest: dict) -> str | None:
    from core.plugin_manifest import load_manifest

    return load_manifest(_write(root, manifest))[1]


def _case(cid: str, kind: str, **arguments: object) -> dict:
    return {
        "id": cid,
        "input": "Do the thing this case asks for.",
        "expect": {"kind": kind, **arguments},
    }


def _plain_manifest() -> dict:
    """A version 2 manifest that declares no capability section at all."""
    manifest = _manifest()
    del manifest["capabilities"]
    return manifest


def _bundle(
    root: Path,
    name: str,
    cases: list[dict],
    *,
    kinds: list[dict] | None = None,
    manifest: dict | None = None,
) -> Path:
    """One bundle directory holding a suite and a manifest.

    `kinds` declares the presets, an explicit `manifest` replaces the whole document, and
    neither gives a valid bundle that declares no capability at all.
    """
    directory = root / name
    (directory / "prompts").mkdir(parents=True)
    if manifest is None:
        payload = _plain_manifest() if kinds is None else _manifest(kinds)
    else:
        payload = manifest
    (directory / "ephe-plugin.json").write_text(
        json.dumps({**payload, "name": name}), encoding="utf-8"
    )
    (directory / "prompts" / "golden.jsonl").write_text(
        "\n".join(json.dumps(case) for case in cases) + "\n", encoding="utf-8"
    )
    return directory


def _load(directory: Path) -> list[dict]:
    return plugin_golden.load_golden(directory / "prompts" / "golden.jsonl", directory.name)


@pytest.fixture()
def contract_root(tmp_path):
    """A folder per test for the manifests that have to be refused."""
    root = tmp_path / "contract"
    root.mkdir()
    return root


class TestContract:
    def test_a_valid_manifest_carries_the_presets_it_declares(self) -> None:
        from core.plugin_evaluator_contract import evaluator_kinds

        manifest = _manifest([_kind()])
        kinds = evaluator_kinds(manifest)
        assert set(kinds) == {"no-slop"}
        assert kinds["no-slop"].base == "not_contains"
        assert kinds["no-slop"].any == ("as an AI", "lorem ipsum")
        assert kinds["no-slop"].plugin_id == "acme-eval"

    def test_the_kernel_vocabulary_has_one_home(self) -> None:
        from core.plugin_evaluator_contract import KINDS

        assert plugin_golden.KINDS == KINDS
        assert KINDS == (
            "artifact",
            "tool_use",
            "contains",
            "not_contains",
            "tool_refused",
        )

    def test_a_version_1_manifest_cannot_declare_presets(self, contract_root) -> None:
        manifest = _manifest([_kind()])
        manifest["manifest_version"] = 1
        assert _error(contract_root, manifest) == "capabilities: manifest_version 2 required"

    def test_an_unknown_capability_section_is_still_refused(self, contract_root) -> None:
        """Widening the vocabulary for evaluator must not open the section list to typos."""
        manifest = _manifest([_kind()])
        manifest["capabilities"]["vector"] = {}
        assert _error(contract_root, manifest) == "capabilities: unknown section(s): vector"

    def test_the_evaluator_section_has_to_be_an_object(self, contract_root) -> None:
        manifest = _manifest([_kind()])
        manifest["capabilities"]["evaluator"] = []
        assert _error(contract_root, manifest) == "capabilities.evaluator: object expected"

    def test_an_unknown_evaluator_field_is_refused(self, contract_root) -> None:
        manifest = _manifest([_kind()], presets=[])
        assert (
            _error(contract_root, manifest)
            == "capabilities.evaluator: unknown field(s): presets"
        )

    def test_kinds_has_to_be_a_list(self, contract_root) -> None:
        assert (
            _error(contract_root, _manifest(kinds="no-slop"))
            == "capabilities.evaluator.kinds: list expected"
        )

    def test_an_empty_kind_list_is_refused(self, contract_root) -> None:
        assert (
            _error(contract_root, _manifest([]))
            == "capabilities.evaluator.kinds: at least one kind expected"
        )

    def test_the_kind_count_has_a_ceiling(self, contract_root) -> None:
        manifest = _manifest(
            [_kind(id=f"trap-{index}") for index in range(9)]
        )
        assert (
            _error(contract_root, manifest)
            == "capabilities.evaluator.kinds: at most 8 kinds expected"
        )

    def test_a_kind_has_to_be_an_object(self, contract_root) -> None:
        assert (
            _error(contract_root, _manifest(["no-slop"]))
            == "capabilities.evaluator.kinds[0]: object expected"
        )

    def test_an_unknown_kind_field_is_refused(self, contract_root) -> None:
        assert (
            _error(contract_root, _manifest([_kind(match="x")]))
            == "capabilities.evaluator.kinds[0]: unknown field(s): match"
        )

    def test_a_kind_id_is_a_slug(self, contract_root) -> None:
        assert (
            _error(contract_root, _manifest([_kind(id="No Slop")]))
            == "capabilities.evaluator.kinds[0].id: lowercase slug expected (a-z0-9-)"
        )

    def test_a_kind_id_has_a_length_ceiling(self, contract_root) -> None:
        assert (
            _error(contract_root, _manifest([_kind(id="p" * 41)]))
            == "capabilities.evaluator.kinds[0].id: at most 40 characters expected"
        )

    def test_a_kernel_kind_id_cannot_be_taken(self, contract_root) -> None:
        for kernel in ("contains", "not_contains", "artifact", "tool_use", "tool_refused"):
            manifest = _manifest([_kind(id=kernel)])
            assert (
                _error(contract_root, manifest)
                == f"capabilities.evaluator.kinds[0].id: {kernel!r} is a kernel kind id"
            )

    def test_a_duplicate_kind_id_is_refused(self, contract_root) -> None:
        manifest = _manifest([_kind(), _kind()])
        assert (
            _error(contract_root, manifest)
            == "capabilities.evaluator.kinds[1].id: duplicate id 'no-slop'"
        )

    def test_a_base_outside_the_kernel_primitives_is_refused(self, contract_root) -> None:
        manifest = _manifest([_kind(**{"from": "regex"})])
        assert (
            _error(contract_root, manifest)
            == "capabilities.evaluator.kinds[0].from: 'regex' is not a base this kernel "
            "grades (artifact, tool_use, contains, not_contains, tool_refused)"
        )

    def test_a_preset_without_its_arguments_is_refused(self, contract_root) -> None:
        manifest = _manifest([_kind(**{"from": "contains", "any": None})])
        assert (
            _error(contract_root, manifest)
            == "capabilities.evaluator.kinds[0]: contains needs any: [strings]"
        )

    def test_a_preset_fragment_list_holds_strings(self, contract_root) -> None:
        manifest = _manifest([_kind(any=["as an AI", 7])])
        assert (
            _error(contract_root, manifest)
            == "capabilities.evaluator.kinds[0]: not_contains needs any: [strings]"
        )

    def test_a_blank_preset_fragment_is_refused(self, contract_root) -> None:
        manifest = _manifest([_kind(any=["as an AI", "   "])])
        assert (
            _error(contract_root, manifest)
            == "capabilities.evaluator.kinds[0]: not_contains needs a non-empty "
            "fragment in any"
        )

    def test_a_preset_fragment_below_the_floor_is_refused(self, contract_root) -> None:
        """A preset is reused by every case that names it, so two letters are no check."""
        manifest = _manifest([_kind(any=["ai"])])
        assert (
            _error(contract_root, manifest)
            == "capabilities.evaluator.kinds[0]: not_contains fragment 'ai' is "
            "shorter than 3 characters"
        )

    def test_a_preset_may_not_carry_an_argument_its_base_does_not_read(self, contract_root) -> None:
        manifest = _manifest([_kind(suffix=".pdf")])
        assert (
            _error(contract_root, manifest)
            == "capabilities.evaluator.kinds[0]: not_contains does not read suffix; "
            "its arguments are any"
        )

    def test_a_missing_description_is_refused(self, contract_root) -> None:
        manifest = _manifest([_kind(description=None)])
        assert (
            _error(contract_root, manifest)
            == "capabilities.evaluator.kinds[0].description: non-empty string expected"
        )

    def test_a_blank_description_is_refused(self, contract_root) -> None:
        manifest = _manifest([_kind(description="  ")])
        assert (
            _error(contract_root, manifest)
            == "capabilities.evaluator.kinds[0].description: non-empty string expected"
        )

    def test_an_absent_evaluator_section_is_fine(self, contract_root) -> None:
        manifest = _manifest([_kind()])
        del manifest["capabilities"]
        assert _error(contract_root, manifest) is None

    def test_a_bundle_declaring_eight_kinds_is_accepted(self, contract_root) -> None:
        manifest = _manifest([_kind(id=f"trap-{index}") for index in range(8)])
        assert _error(contract_root, manifest) is None

    def test_the_bundles_manifest_resolves_its_presets(self, tmp_path) -> None:
        from core.plugin_evaluator_contract import evaluator_kinds

        directory = _bundle(tmp_path, "acme-eval", [_case("acme-eval-1", "no-slop")], kinds=[_kind()])
        from core.plugin_manifest import load_manifest

        manifest, error = load_manifest(directory)
        assert error is None
        assert evaluator_kinds(manifest)["no-slop"].kind_id == "no-slop"


class TestGradePath:
    def _suite(self, tmp_path, cases, kinds=None):
        directory = _bundle(
            tmp_path,
            "acme-eval",
            cases,
            kinds=[_kind()] if kinds is None else kinds,
        )
        return _load(directory)

    def test_a_declared_not_contains_preset_grades_like_the_primitive(self, tmp_path) -> None:
        case = self._suite(tmp_path, [_case("acme-eval-1", "no-slop")])[0]
        assert case["matcher"] == {"kind": "not_contains", "any": ["as an AI", "lorem ipsum"]}
        assert case["kind_source"] == "no-slop"
        assert plugin_golden.grade(case, "The report is two pages long.")
        assert not plugin_golden.grade(case, "As an AI, I cannot read that file.")

    def test_a_declared_contains_preset_grades_like_the_primitive(self, tmp_path) -> None:
        kinds = [_kind(id="names-the-file", **{"from": "contains"}, any=["report.pdf"])]
        case = self._suite(
            tmp_path, [_case("acme-eval-1", "names-the-file")], kinds=kinds
        )[0]
        assert case["matcher"] == {"kind": "contains", "any": ["report.pdf"]}
        assert plugin_golden.grade(case, "Wrote report.pdf next to the source.")
        assert not plugin_golden.grade(case, "Wrote the file next to the source.")

    def test_the_declared_name_stays_in_what_the_author_wrote(self, tmp_path) -> None:
        case = self._suite(tmp_path, [_case("acme-eval-1", "no-slop")])[0]
        assert case["expect"] == {"kind": "no-slop"}
        assert case["matcher"]["kind"] == "not_contains"

    def test_a_kernel_case_records_the_kernel_as_its_source(self, tmp_path) -> None:
        case = self._suite(
            tmp_path, [_case("acme-eval-1", "contains", any=["report"])]
        )[0]
        assert case["kind_source"] == "kernel"
        assert case["matcher"] == {"kind": "contains", "any": ["report"]}

    def test_the_matrix_row_names_the_preset_and_the_primitive(self, tmp_path) -> None:
        directory = _bundle(
            tmp_path, "acme-eval", [_case("acme-eval-1", "no-slop")], kinds=[_kind()]
        )
        matrix = plugin_golden.measure_matrix(
            directory, runs=1, runner=lambda case, **_: ("done", {}), system_prompt="", allowed_tools=[]
        )
        row = matrix["cases"][0]
        assert row["expect"] == {"kind": "no-slop"}
        assert row["kind_source"] == "no-slop"
        assert row["matcher"]["kind"] == "not_contains"

    def test_the_pass3_row_names_the_preset_and_the_primitive(self, tmp_path, monkeypatch) -> None:
        directory = _bundle(
            tmp_path, "acme-eval", [_case("acme-eval-1", "no-slop")], kinds=[_kind()]
        )
        monkeypatch.setattr(plugin_golden, "run_once", lambda case, engine=None, **_: "done")
        rows = plugin_golden.pass3_matrix(directory, runs=["a", "b", "c"])
        assert rows[0]["kind_source"] == "no-slop"
        assert rows[0]["matcher"] == {"kind": "not_contains", "any": ["as an AI", "lorem ipsum"]}

    def test_a_declared_not_contains_preset_satisfies_the_anti_slop_gate(self, tmp_path) -> None:
        cases = [_case(f"acme-eval-{index}", "contains", any=["ok"]) for index in range(1, 6)]
        cases.append(_case("acme-eval-6", "no-slop"))
        directory = _bundle(tmp_path, "acme-eval", cases, kinds=[_kind()])
        (directory / "prompts" / "rubric.md").write_text(
            "# Rubric\n\nThe answer is short, names the file it wrote and carries no "
            "placeholder text. Each case is graded mechanically, so this rubric records "
            "the quality bar a reader applies to the report rather than a second check "
            "the grader runs. Six cases, one of them a declared anti-slop preset.\n",
            encoding="utf-8",
        )
        report = plugin_golden.verify_all(tmp_path)
        assert report == [{"plugin": "acme-eval", "cases": 6, "issues": []}]

    def test_a_declared_contains_preset_does_not_satisfy_the_anti_slop_gate(self, tmp_path) -> None:
        cases = [_case(f"acme-eval-{index}", "contains", any=["ok"]) for index in range(1, 7)]
        contains = _kind(id="names-the-file", **{"from": "contains"}, any=["report.pdf"])
        cases[0] = _case("acme-eval-1", "names-the-file")
        directory = _bundle(
            tmp_path, "acme-eval", cases, kinds=[contains]
        )
        (directory / "prompts" / "rubric.md").write_text(
            "# Rubric\n\nThe answer names the file it wrote. Six cases, none of them an "
            "anti-slop trap, which is the finding this case measures rather than a "
            "quality bar a reader applies to the report.\n",
            encoding="utf-8",
        )
        report = plugin_golden.verify_all(tmp_path)
        assert "no anti-slop trap (not_contains)" in report[0]["issues"]


class TestFailClosed:
    """Every hole the old validator left open, as a refusal at load time."""

    def test_a_case_naming_an_undeclared_kind_is_refused(self, tmp_path) -> None:
        directory = _bundle(tmp_path, "acme-eval", [_case("acme-eval-1", "no-slop")])
        with pytest.raises(ValueError, match="unknown expect.kind 'no-slop'"):
            _load(directory)

    def test_a_case_naming_a_kind_with_no_manifest_is_refused(self, tmp_path) -> None:
        directory = tmp_path / "acme-eval"
        (directory / "prompts").mkdir(parents=True)
        (directory / "prompts" / "golden.jsonl").write_text(
            json.dumps(_case("acme-eval-1", "no-slop")) + "\n", encoding="utf-8"
        )
        with pytest.raises(ValueError, match="unknown expect.kind 'no-slop'"):
            _load(directory)

    def test_a_preset_does_not_resolve_into_another_bundle(self, tmp_path) -> None:
        _bundle(tmp_path, "alpha-eval", [_case("alpha-eval-1", "no-slop")], kinds=[_kind()])
        beta = _bundle(tmp_path, "beta-eval", [_case("beta-eval-1", "no-slop")])
        with pytest.raises(ValueError, match="unknown expect.kind 'no-slop'"):
            _load(beta)

    def test_a_case_may_not_restate_a_presets_arguments(self, tmp_path) -> None:
        case = _case("acme-eval-1", "no-slop", any=["something else"])
        directory = _bundle(tmp_path, "acme-eval", [case], kinds=[_kind()])
        with pytest.raises(ValueError, match="takes no arguments beside kind"):
            _load(directory)

    def test_a_case_may_not_write_the_loader_matcher(self, tmp_path) -> None:
        case = {**_case("acme-eval-1", "no-slop"), "matcher": {"kind": "contains", "any": ["x"]}}
        directory = _bundle(tmp_path, "acme-eval", [case], kinds=[_kind()])
        with pytest.raises(ValueError, match="may not carry matcher"):
            _load(directory)

    def test_a_case_may_not_write_the_loader_source(self, tmp_path) -> None:
        case = {**_case("acme-eval-1", "contains", any=["ok"]), "kind_source": "no-slop"}
        directory = _bundle(tmp_path, "acme-eval", [case], kinds=[_kind()])
        with pytest.raises(ValueError, match="may not carry kind_source"):
            _load(directory)

    def test_an_empty_fragment_is_refused_for_every_string_kind(self, tmp_path) -> None:
        for kind in ("contains", "not_contains", "tool_use"):
            case = _case("acme-eval-1", kind, any=[""])
            directory = _bundle(tmp_path / kind, "acme-eval", [case])
            with pytest.raises(ValueError, match="needs a non-empty fragment"):
                _load(directory)

    def test_a_blank_fragment_does_not_hide_behind_a_valid_one(self, tmp_path) -> None:
        case = _case("acme-eval-1", "contains", any=["report.pdf", " "])
        directory = _bundle(tmp_path, "acme-eval", [case])
        with pytest.raises(ValueError, match="needs a non-empty fragment"):
            _load(directory)

    def test_a_case_may_not_carry_an_argument_its_kind_does_not_read(self, tmp_path) -> None:
        case = _case("acme-eval-1", "contains", any=["report.pdf"], reason="denied")
        directory = _bundle(tmp_path, "acme-eval", [case])
        with pytest.raises(ValueError, match="contains does not read reason"):
            _load(directory)

    def test_an_empty_reason_is_refused(self, tmp_path) -> None:
        case = _case("acme-eval-1", "tool_refused", any=["write_file"], reason="   ")
        directory = _bundle(tmp_path, "acme-eval", [case])
        with pytest.raises(ValueError, match="reason must be a phrase to find"):
            _load(directory)

    def test_an_empty_suffix_is_refused(self, tmp_path) -> None:
        case = _case("acme-eval-1", "artifact", suffix="")
        directory = _bundle(tmp_path, "acme-eval", [case])
        with pytest.raises(ValueError, match="artifact needs a suffix"):
            _load(directory)

    def test_an_invalid_manifest_makes_the_suite_unreadable(self, tmp_path) -> None:
        manifest = _manifest([_kind(match="x")])
        directory = _bundle(
            tmp_path, "acme-eval", [_case("acme-eval-1", "contains", any=["ok"])], manifest=manifest
        )
        with pytest.raises(ValueError, match="unknown field"):
            _load(directory)

    def test_a_manifest_refused_elsewhere_still_declares_its_presets(self, tmp_path) -> None:
        """The suite asks one question of the manifest: does its evaluator section load.

        A bundle the rest of the contract refuses is the scanner's finding; letting the
        loader refuse it too would report one manifest violation as a golden finding.
        """
        manifest = _manifest([_kind()])
        del manifest["description"]
        directory = _bundle(
            tmp_path,
            "acme-eval",
            [_case("acme-eval-1", "no-slop")],
            manifest=manifest,
        )
        assert _load(directory)[0]["matcher"]["kind"] == "not_contains"

    def test_a_raw_declared_name_case_grades_false(self) -> None:
        """A case that never passed the loader has no matcher, so it grades nothing."""
        assert not plugin_golden.grade(
            {"expect": {"kind": "no-slop"}}, "The report is two pages long."
        )

    def test_a_kernel_case_still_needs_a_readable_expect(self, tmp_path) -> None:
        directory = _bundle(
            tmp_path,
            "acme-eval",
            [{"id": "acme-eval-1", "input": "Ask it about the file.", "expect": []}],
        )
        with pytest.raises(ValueError, match="expect must be an object"):
            _load(directory)
