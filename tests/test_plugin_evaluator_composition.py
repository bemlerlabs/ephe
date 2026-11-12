"""EVAL-P2 — composed grader presets: the remaining bases and `all_of` / `none_of`.

The second cut of `capabilities.evaluator`. The first cut
(`tests/test_plugin_evaluator_kinds.py`) let a manifest name presets of `contains` and
`not_contains`. This cut adds the three remaining kernel primitives — `artifact`,
`tool_use` and `tool_refused` — as declarable bases with their own arguments, and lets a
case combine the presets its own bundle declares with `all_of` or `none_of` in
`expect.kind`.

What stays the kernel's, and what this file therefore checks: the five primitives and
their argument rules, the case schema, the receipt shape and the anti-slop gate. A
composition names declared presets only, so the manifest stays the one place a fragment
list is written; the gate still asks for the kernel's `not_contains` primitive somewhere
in whatever a case resolves to. Most cases here are failure modes: a composition that
passes one member and fails another is not a pass, and a `none_of` whose member passes is
not a pass either.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import core.plugin_golden as plugin_golden

#: The marker the harness separates the answer from the tool events with.
EVENTS = "\n[EPHE-TOOL-EVENTS]\n"


def _manifest(kinds: object = None, **evaluator: object) -> dict:
    """A version 2 manifest declaring grader presets; `evaluator` replaces the section."""
    section: dict = dict(evaluator)
    if kinds is not None:
        section["kinds"] = kinds
    return {
        "manifest_version": 2,
        "name": "acme-eval",
        "version": "1.0.0",
        "description": "Declares composed grader presets for its own golden suite.",
        "publisher": {"name": "Acme"},
        "license": "MIT",
        "engines": {"ephe": ">=0.6.0"},
        "permissions": {"tool_families": [], "data_roots": []},
        "capabilities": {"evaluator": section},
    }


def _plain_manifest() -> dict:
    """A version 2 manifest that declares no capability section at all."""
    manifest = _manifest()
    del manifest["capabilities"]
    return manifest


def _preset(**overrides: object) -> dict:
    """One `not_contains` preset; `overrides` replaces a field, and None drops it."""
    preset: dict = {
        "id": "no-slop",
        "from": "not_contains",
        "any": ["as an AI", "lorem ipsum"],
        "description": "Placeholder text never reaches the answer.",
    }
    preset.update(overrides)
    return {key: value for key, value in preset.items() if value is not None}


def _wrote_pdf() -> dict:
    return _preset(
        id="wrote-pdf",
        **{"from": "artifact"},
        any=None,
        suffix=".pdf",
        description="A PDF path is in the transcript.",
    )


def _used_writer() -> dict:
    return _preset(
        id="used-writer",
        **{"from": "tool_use"},
        any=["write_file"],
        description="The turn wrote the file it was asked for.",
    )


def _refused_install() -> dict:
    return _preset(
        id="refused-install",
        **{"from": "tool_refused"},
        any=["install_plugin_bundle"],
        reason="consent",
        description="Installing a bundle is refused by the consent gate.",
    )


def _names_file() -> dict:
    return _preset(
        id="names-file",
        **{"from": "contains"},
        any=["report.pdf"],
        description="The answer names the file it wrote.",
    )


def _no_todo() -> dict:
    return _preset(
        id="no-todo",
        any=["TODO:", "fixme"],
        description="No work marker reaches the answer.",
    )


def _says_as_ai() -> dict:
    return _preset(
        id="says-as-ai",
        **{"from": "contains"},
        any=["as an ai"],
        description="The answer claims to be an AI.",
    )


def _says_todo() -> dict:
    return _preset(
        id="says-todo",
        **{"from": "contains"},
        any=["todo:"],
        description="The answer carries a work marker.",
    )


def _case(cid: str, kind: str, **arguments: object) -> dict:
    return {
        "id": cid,
        "input": "Do the thing this case asks for.",
        "expect": {"kind": kind, **arguments},
    }


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


def _bundle(
    root: Path,
    name: str,
    cases: list[dict],
    *,
    kinds: list[dict] | None = None,
    manifest: dict | None = None,
) -> Path:
    """One bundle directory holding a suite and a manifest."""
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


def _loaded(
    tmp_path: Path, cases: list[dict], kinds: list[dict] | None = None
) -> list[dict]:
    """Load one suite of the same bundle; every case names a preset it declares."""
    return _load(_bundle(tmp_path, "acme-eval", cases, kinds=kinds))


def _transcript(answer: str, *events: str) -> str:
    return answer + EVENTS + "\n".join(events)


@pytest.fixture()
def contract_root(tmp_path):
    """A folder per test for the manifests that have to be refused."""
    root = tmp_path / "contract"
    root.mkdir()
    return root


class TestContract:
    def test_the_three_remaining_primitives_are_declarable_bases(self) -> None:
        from core.plugin_evaluator_contract import KINDS, PRESET_BASES

        assert PRESET_BASES == KINDS
        assert PRESET_BASES == (
            "artifact",
            "tool_use",
            "contains",
            "not_contains",
            "tool_refused",
        )

    def test_the_composition_grammar_is_named_once(self) -> None:
        from core.plugin_evaluator_contract import COMPOSITIONS, KINDS

        assert COMPOSITIONS == ("all_of", "none_of")
        assert not set(COMPOSITIONS) & set(KINDS)

    def test_each_new_base_resolves_its_own_arguments(self) -> None:
        from core.plugin_evaluator_contract import evaluator_kinds

        kinds = evaluator_kinds(_manifest([_wrote_pdf(), _used_writer(), _refused_install()]))
        assert kinds["wrote-pdf"].base == "artifact"
        assert kinds["wrote-pdf"].suffix == ".pdf"
        assert kinds["used-writer"].any == ("write_file",)
        assert kinds["refused-install"].reason == "consent"

    def test_a_preset_matcher_carries_the_arguments_its_base_reads(self) -> None:
        from core.plugin_evaluator_contract import evaluator_kinds, preset_matcher

        kinds = evaluator_kinds(_manifest([_wrote_pdf(), _used_writer(), _refused_install()]))
        assert preset_matcher(kinds["wrote-pdf"]) == {"kind": "artifact", "suffix": ".pdf"}
        assert preset_matcher(kinds["used-writer"]) == {
            "kind": "tool_use",
            "any": ["write_file"],
        }
        assert preset_matcher(kinds["refused-install"]) == {
            "kind": "tool_refused",
            "any": ["install_plugin_bundle"],
            "reason": "consent",
        }

    def test_a_tool_refused_preset_without_a_reason_is_accepted(self) -> None:
        from core.plugin_evaluator_contract import evaluator_kinds

        preset = _preset(id="refused-tool", **{"from": "tool_refused"})
        preset["any"] = ["install_plugin_bundle"]
        kinds = evaluator_kinds(_manifest([preset]))
        assert kinds["refused-tool"].reason == ""

    def test_a_composition_id_cannot_be_taken_as_a_preset_id(self, contract_root) -> None:
        for name in ("all_of", "none_of"):
            assert (
                _error(contract_root, _manifest([_preset(id=name)]))
                == f"capabilities.evaluator.kinds[0].id: {name!r} is a composition id"
            )

    def test_a_base_outside_the_kernel_primitives_is_refused(self, contract_root) -> None:
        manifest = _manifest([_preset(**{"from": "regex"})])
        assert (
            _error(contract_root, manifest)
            == "capabilities.evaluator.kinds[0].from: 'regex' is not a base this kernel "
            "grades (artifact, tool_use, contains, not_contains, tool_refused)"
        )

    def test_an_artifact_preset_needs_a_dotted_suffix(self, contract_root) -> None:
        for suffix in (None, "pdf", ""):
            preset = _wrote_pdf()
            preset.pop("suffix", None)
            if suffix is not None:
                preset["suffix"] = suffix
            assert (
                _error(contract_root, _manifest([preset]))
                == "capabilities.evaluator.kinds[0]: artifact needs a suffix like '.pdf'"
            )

    def test_a_tool_use_preset_needs_fragments(self, contract_root) -> None:
        preset = _used_writer()
        preset.pop("any")
        assert (
            _error(contract_root, _manifest([preset]))
            == "capabilities.evaluator.kinds[0]: tool_use needs any: [strings]"
        )

    def test_a_tool_refused_preset_needs_fragments(self, contract_root) -> None:
        preset = _refused_install()
        preset.pop("any")
        assert (
            _error(contract_root, _manifest([preset]))
            == "capabilities.evaluator.kinds[0]: tool_refused needs any: [strings]"
        )

    def test_a_blank_tool_refused_reason_is_refused(self, contract_root) -> None:
        assert (
            _error(contract_root, _manifest([_refused_install() | {"reason": "  "}]))
            == "capabilities.evaluator.kinds[0]: tool_refused reason must be a phrase to "
            "find"
        )

    def test_a_new_base_does_not_read_another_bases_arguments(self, contract_root) -> None:
        with_any = _wrote_pdf() | {"any": ["report.pdf"]}
        assert (
            _error(contract_root, _manifest([with_any]))
            == "capabilities.evaluator.kinds[0]: artifact does not read any; its "
            "arguments are suffix"
        )
        with_suffix = _used_writer() | {"suffix": ".pdf"}
        assert (
            _error(contract_root, _manifest([with_suffix]))
            == "capabilities.evaluator.kinds[0]: tool_use does not read suffix; its "
            "arguments are any"
        )

    def test_the_fragment_floor_holds_for_the_new_bases(self, contract_root) -> None:
        short_use = _used_writer() | {"any": ["ok"]}
        assert (
            _error(contract_root, _manifest([short_use]))
            == "capabilities.evaluator.kinds[0]: tool_use fragment 'ok' is shorter than "
            "3 characters"
        )
        short_refused = _refused_install() | {"any": ["ok"]}
        assert (
            _error(contract_root, _manifest([short_refused]))
            == "capabilities.evaluator.kinds[0]: tool_refused fragment 'ok' is shorter "
            "than 3 characters"
        )

    def test_the_kind_ceiling_holds_for_the_new_bases(self, contract_root) -> None:
        kinds = [_preset(id=f"trap-{index}") for index in range(8)]
        kinds.append(_wrote_pdf())
        assert (
            _error(contract_root, _manifest(kinds))
            == "capabilities.evaluator.kinds: at most 8 kinds expected"
        )


class TestGradePath:
    def test_an_artifact_preset_grades_like_the_primitive(self, tmp_path) -> None:
        cases = _loaded(
            tmp_path, [_case("acme-eval-1", "wrote-pdf")], kinds=[_wrote_pdf()]
        )
        case = cases[0]
        assert case["matcher"] == {"kind": "artifact", "suffix": ".pdf"}
        assert case["kind_source"] == "wrote-pdf"
        assert plugin_golden.grade(case, "Saved the report to out/report.pdf.")
        assert not plugin_golden.grade(case, "Saved the report to out/report.txt.")

    def test_a_tool_use_preset_grades_on_the_events_not_the_answer(self, tmp_path) -> None:
        cases = _loaded(
            tmp_path, [_case("acme-eval-1", "used-writer")], kinds=[_used_writer()]
        )
        case = cases[0]
        assert plugin_golden.grade(
            case, _transcript("Done.", "[tool write_file] wrote the file")
        )
        assert not plugin_golden.grade(
            case, _transcript("I called write_file.", "[tool read_file] opened it")
        )
        assert not plugin_golden.grade(
            case, _transcript("Done.", "[tool write_file] [tool-error] denied")
        )

    def test_a_tool_refused_preset_with_a_reason_needs_the_refusals_words(self, tmp_path) -> None:
        cases = _loaded(
            tmp_path,
            [_case("acme-eval-1", "refused-install")],
            kinds=[_refused_install()],
        )
        case = cases[0]
        assert case["matcher"]["reason"] == "consent"
        assert plugin_golden.grade(
            case,
            _transcript(
                "I cannot install that.",
                "[tool install_plugin_bundle] refused: consent required",
            ),
        )
        assert not plugin_golden.grade(
            case,
            _transcript(
                "Installed.",
                "[tool install_plugin_bundle] installed the bundle",
            ),
        )

    def test_a_tool_refused_preset_without_a_reason_only_needs_the_absence(
        self, tmp_path
    ) -> None:
        preset = _preset(id="refused-tool", **{"from": "tool_refused"})
        preset["any"] = ["install_plugin_bundle"]
        cases = _loaded(
            tmp_path, [_case("acme-eval-1", "refused-tool")], kinds=[preset]
        )
        case = cases[0]
        assert "reason" not in case["matcher"]
        assert plugin_golden.grade(case, _transcript("The offer withheld it."))
        assert not plugin_golden.grade(
            case, _transcript("Installed.", "[tool install_plugin_bundle] ok")
        )

    def test_the_matrix_row_names_the_base_preset_and_primitive(self, tmp_path) -> None:
        directory = _bundle(
            tmp_path, "acme-eval", [_case("acme-eval-1", "wrote-pdf")], kinds=[_wrote_pdf()]
        )
        matrix = plugin_golden.measure_matrix(
            directory,
            runs=1,
            runner=lambda case, **_: "Saved out/report.pdf.",
            system_prompt="",
            allowed_tools=[],
        )
        row = matrix["cases"][0]
        assert row["expect"] == {"kind": "wrote-pdf"}
        assert row["matcher"] == {"kind": "artifact", "suffix": ".pdf"}
        assert row["kind_source"] == "wrote-pdf"


class TestComposition:
    def test_all_of_resolves_every_member_to_its_primitive(self, tmp_path) -> None:
        cases = _loaded(
            tmp_path,
            [_case("acme-eval-1", "all_of", of=["no-slop", "wrote-pdf"])],
            kinds=[_preset(), _wrote_pdf()],
        )
        case = cases[0]
        assert case["expect"] == {"kind": "all_of", "of": ["no-slop", "wrote-pdf"]}
        assert case["matcher"] == {
            "kind": "all_of",
            "of": [
                {"kind": "not_contains", "any": ["as an AI", "lorem ipsum"]},
                {"kind": "artifact", "suffix": ".pdf"},
            ],
        }
        assert case["kind_source"] == "all_of(no-slop, wrote-pdf)"

    def test_none_of_resolves_every_member_to_its_primitive(self, tmp_path) -> None:
        cases = _loaded(
            tmp_path,
            [_case("acme-eval-1", "none_of", of=["no-slop", "wrote-pdf"])],
            kinds=[_preset(), _wrote_pdf()],
        )
        case = cases[0]
        assert case["matcher"]["kind"] == "none_of"
        assert [member["kind"] for member in case["matcher"]["of"]] == [
            "not_contains",
            "artifact",
        ]
        assert case["kind_source"] == "none_of(no-slop, wrote-pdf)"

    def test_all_of_passes_only_when_every_member_passes(self, tmp_path) -> None:
        case = _loaded(
            tmp_path,
            [_case("acme-eval-1", "all_of", of=["no-slop", "wrote-pdf"])],
            kinds=[_preset(), _wrote_pdf()],
        )[0]
        assert plugin_golden.grade(case, "Saved the report to out/report.pdf.")
        assert not plugin_golden.grade(
            case, "As an AI, I saved the report to out/report.pdf."
        )
        assert not plugin_golden.grade(case, "Saved the report to out/report.txt.")

    def test_none_of_passes_only_when_no_member_passes(self, tmp_path) -> None:
        case = _loaded(
            tmp_path,
            [_case("acme-eval-1", "none_of", of=["wrote-pdf", "names-file"])],
            kinds=[_wrote_pdf(), _names_file()],
        )[0]
        assert plugin_golden.grade(case, "I only described the plan.")
        assert not plugin_golden.grade(case, "Saved the report to out/report.pdf.")
        assert not plugin_golden.grade(case, "The answer names report.pdf.")

    def test_none_of_over_two_contains_presets_forbids_both_fragments(self, tmp_path) -> None:
        case = _loaded(
            tmp_path,
            [_case("acme-eval-1", "none_of", of=["says-as-ai", "says-todo"])],
            kinds=[_says_as_ai(), _says_todo()],
        )[0]
        assert plugin_golden.grade(case, "The report is two pages long.")
        assert not plugin_golden.grade(case, "As an AI, I cannot read that file.")
        assert not plugin_golden.grade(case, "TODO: write the report.")

    def test_the_matrix_row_carries_the_composition_and_its_members(self, tmp_path) -> None:
        directory = _bundle(
            tmp_path,
            "acme-eval",
            [_case("acme-eval-1", "all_of", of=["no-slop", "wrote-pdf"])],
            kinds=[_preset(), _wrote_pdf()],
        )
        matrix = plugin_golden.measure_matrix(
            directory,
            runs=1,
            runner=lambda case, **_: "Saved out/report.pdf.",
            system_prompt="",
            allowed_tools=[],
        )
        row = matrix["cases"][0]
        assert row["expect"] == {"kind": "all_of", "of": ["no-slop", "wrote-pdf"]}
        assert row["matcher"]["kind"] == "all_of"
        assert row["kind_source"] == "all_of(no-slop, wrote-pdf)"

    def test_the_pass3_row_carries_the_composition_and_its_members(
        self, tmp_path, monkeypatch
    ) -> None:
        directory = _bundle(
            tmp_path,
            "acme-eval",
            [_case("acme-eval-1", "all_of", of=["no-slop", "wrote-pdf"])],
            kinds=[_preset(), _wrote_pdf()],
        )
        monkeypatch.setattr(
            plugin_golden,
            "run_once",
            lambda case, engine=None, **_: "Saved out/report.pdf.",
        )
        rows = plugin_golden.pass3_matrix(directory, runs=["a", "b", "c"])
        assert rows[0]["kind_source"] == "all_of(no-slop, wrote-pdf)"
        assert rows[0]["pass3"] is True
        assert [member["kind"] for member in rows[0]["matcher"]["of"]] == [
            "not_contains",
            "artifact",
        ]

    def test_a_composition_member_has_to_be_a_declared_preset(self, tmp_path) -> None:
        directory = _bundle(
            tmp_path,
            "acme-eval",
            [_case("acme-eval-1", "all_of", of=["no-slop", "contains"])],
            kinds=[_preset()],
        )
        with pytest.raises(ValueError, match="member 'contains' is a kernel kind"):
            _load(directory)

    def test_a_composition_member_may_not_be_another_composition(self, tmp_path) -> None:
        directory = _bundle(
            tmp_path,
            "acme-eval",
            [_case("acme-eval-1", "all_of", of=["no-slop", "none_of"])],
            kinds=[_preset()],
        )
        with pytest.raises(ValueError, match="member 'none_of' is a composition id"):
            _load(directory)

    def test_a_composition_naming_an_undeclared_preset_is_refused(self, tmp_path) -> None:
        directory = _bundle(
            tmp_path,
            "acme-eval",
            [_case("acme-eval-1", "all_of", of=["no-slop", "ghost"])],
            kinds=[_preset()],
        )
        with pytest.raises(
            ValueError,
            match="member 'ghost' is not a declared preset - declared here: no-slop",
        ):
            _load(directory)

    def test_a_composition_does_not_resolve_into_another_bundle(self, tmp_path) -> None:
        _bundle(
            tmp_path, "alpha-eval", [_case("alpha-eval-1", "no-slop")], kinds=[_preset()]
        )
        beta = _bundle(
            tmp_path,
            "beta-eval",
            [_case("beta-eval-1", "all_of", of=["no-slop", "beta-trap"])],
            kinds=[_preset(id="beta-trap")],
        )
        with pytest.raises(ValueError, match="member 'no-slop' is not a declared preset"):
            _load(beta)

    def test_a_composition_needs_a_list_of_preset_ids(self, tmp_path) -> None:
        for members in ("no-slop", [1, 2]):
            directory = _bundle(
                tmp_path / str(members),
                "acme-eval",
                [_case("acme-eval-1", "all_of", of=members)],
                kinds=[_preset()],
            )
            with pytest.raises(ValueError, match="all_of needs of: \\[preset ids\\]"):
                _load(directory)

    def test_a_composition_needs_at_least_two_members(self, tmp_path) -> None:
        directory = _bundle(
            tmp_path,
            "acme-eval",
            [_case("acme-eval-1", "all_of", of=["no-slop"])],
            kinds=[_preset()],
        )
        with pytest.raises(ValueError, match="all_of needs at least 2 presets in of"):
            _load(directory)

    def test_a_duplicate_member_is_refused(self, tmp_path) -> None:
        directory = _bundle(
            tmp_path,
            "acme-eval",
            [_case("acme-eval-1", "all_of", of=["no-slop", "no-slop"])],
            kinds=[_preset()],
        )
        with pytest.raises(ValueError, match="all_of names 'no-slop' twice"):
            _load(directory)

    def test_a_composition_takes_no_arguments_beside_of(self, tmp_path) -> None:
        directory = _bundle(
            tmp_path,
            "acme-eval",
            [_case("acme-eval-1", "all_of", of=["no-slop", "wrote-pdf"], any=["x"])],
            kinds=[_preset(), _wrote_pdf()],
        )
        with pytest.raises(ValueError, match=r"all_of takes only of beside kind \(any\)"):
            _load(directory)

    def test_a_kernel_case_may_not_compose(self, tmp_path) -> None:
        directory = _bundle(
            tmp_path,
            "acme-eval",
            [_case("acme-eval-1", "contains", any=["report.pdf"], of=["no-slop"])],
        )
        with pytest.raises(
            ValueError, match="contains does not compose - of belongs to all_of and none_of"
        ):
            _load(directory)

    def test_a_declared_preset_case_may_not_compose(self, tmp_path) -> None:
        directory = _bundle(
            tmp_path,
            "acme-eval",
            [_case("acme-eval-1", "no-slop", of=["no-slop"])],
            kinds=[_preset()],
        )
        with pytest.raises(ValueError, match="takes no arguments beside kind"):
            _load(directory)


class TestAntiSlopGate:
    def _rubric(self, directory: Path) -> None:
        (directory / "prompts" / "rubric.md").write_text(
            "# Rubric\n\nThe answer is short, names the file it wrote and carries no "
            "placeholder text. Each case is graded mechanically, so this rubric records "
            "the quality bar a reader applies to the report rather than a second check "
            "the grader runs. Six cases, one of them a composed trap.\n",
            encoding="utf-8",
        )

    def _six(self, composed: dict) -> list[dict]:
        cases = [
            _case(f"acme-eval-{index}", "contains", any=["ok"]) for index in range(1, 6)
        ]
        return cases + [composed]

    def test_a_declared_none_of_over_contains_presets_satisfies_the_gate(
        self, tmp_path
    ) -> None:
        cases = self._six(
            _case("acme-eval-6", "none_of", of=["says-as-ai", "says-todo"])
        )
        directory = _bundle(
            tmp_path, "acme-eval", cases, kinds=[_says_as_ai(), _says_todo()]
        )
        self._rubric(directory)
        assert plugin_golden.verify_all(tmp_path) == [
            {"plugin": "acme-eval", "cases": 6, "issues": []}
        ]

    def test_an_all_of_carrying_the_trap_satisfies_the_gate(self, tmp_path) -> None:
        cases = self._six(
            _case("acme-eval-6", "all_of", of=["no-slop", "wrote-pdf"])
        )
        directory = _bundle(
            tmp_path, "acme-eval", cases, kinds=[_preset(), _wrote_pdf()]
        )
        self._rubric(directory)
        assert plugin_golden.verify_all(tmp_path) == [
            {"plugin": "acme-eval", "cases": 6, "issues": []}
        ]

    def test_a_none_of_over_the_trap_is_not_a_trap(self, tmp_path) -> None:
        """`none_of` over `not_contains` presets passes only when the trap fails."""
        cases = self._six(
            _case("acme-eval-6", "none_of", of=["no-slop", "no-todo"])
        )
        directory = _bundle(
            tmp_path, "acme-eval", cases, kinds=[_preset(), _no_todo()]
        )
        self._rubric(directory)
        report = plugin_golden.verify_all(tmp_path)
        assert "no anti-slop trap (not_contains)" in report[0]["issues"]

    def test_a_composition_without_the_trap_does_not_satisfy_the_gate(self, tmp_path) -> None:
        """A `none_of` that names another kind is not a text trap either."""
        cases = self._six(
            _case("acme-eval-6", "none_of", of=["names-file", "wrote-pdf"])
        )
        directory = _bundle(
            tmp_path, "acme-eval", cases, kinds=[_names_file(), _wrote_pdf()]
        )
        self._rubric(directory)
        report = plugin_golden.verify_all(tmp_path)
        assert "no anti-slop trap (not_contains)" in report[0]["issues"]


class TestFailOpen:
    """A composition that never loaded, or never resolved, is a failed verdict."""

    def test_a_hand_built_composition_with_no_members_grades_false(self) -> None:
        for kind in ("all_of", "none_of"):
            assert not plugin_golden.grade(
                {"expect": {"kind": kind, "of": []}}, "The report is two pages long."
            )

    def test_a_raw_composition_case_grades_false(self) -> None:
        assert not plugin_golden.grade(
            {"expect": {"kind": "all_of", "of": ["no-slop"]}},
            "The report is two pages long.",
        )

    def test_a_composition_with_an_unresolved_member_kind_grades_false(self) -> None:
        matcher = {
            "kind": "all_of",
            "of": [{"kind": "not_contains", "any": ["as an AI"]}, {"kind": "no-slop"}],
        }
        assert not plugin_golden.grade(
            {"expect": {"kind": "all_of"}, "matcher": matcher},
            "The report is two pages long.",
        )

    def test_a_hand_built_primitive_with_no_arguments_grades_false(self) -> None:
        for matcher in (
            {"kind": "contains"},
            {"kind": "not_contains", "any": []},
            {"kind": "artifact"},
            {"kind": "tool_use", "any": []},
        ):
            case = {"expect": {"kind": matcher["kind"]}, "matcher": matcher}
            assert not plugin_golden.grade(case, "The report is two pages long.")

    def test_an_unloaded_case_that_never_passed_the_loader_grades_false(self) -> None:
        assert not plugin_golden.grade(
            {"expect": {"kind": "none_of", "of": ["no-slop"]}}, "Clean answer."
        )


class TestCreationRegression:
    def test_the_creation_set_still_loads_through_the_golden_loader(self) -> None:
        from evals.creation_eval import load_cases

        cases = load_cases()
        assert len(cases) >= 20
        assert {case["kind_source"] for case in cases} == {"kernel"}
        assert all(isinstance(case.get("matcher"), dict) for case in cases)
