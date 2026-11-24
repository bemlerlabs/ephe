"""The env/lock agreement instrument is only trusted if a planted deviation is caught.

Every case here feeds the instrument a lock body and a set of installed distributions it is
handed — no fixture file, no read of the real environment, no installer. A checker whose clean
case is "nothing printed" proves nothing; these tests assert the refusal and the exit code, so a
detector that stopped seeing drift would fail here rather than in CI.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
INSTRUMENT_PATH = SCRIPTS / "env_lock_agreement.py"


def _load_instrument():
    if str(SCRIPTS) not in sys.path:  # the module reads its lock relative to its own directory
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("env_lock_agreement_under_test", INSTRUMENT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Registered before execution: the module's dataclasses resolve their string annotations
    # through `sys.modules[cls.__module__]`, which is empty until the module is in there.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


instrument = _load_instrument()

ROOT = "ephe"


def lock_text(
    *,
    always_on: dict[str, str],
    extras: dict[str, dict[str, str]] | None = None,
    edges: dict[str, dict[str, str | tuple]] | None = None,
    markers: dict[str, str] | None = None,
) -> str:
    """A `uv.lock` body with one editable root, its dependencies and any extra's own graph.

    `edges` maps a package to the packages it requires; `markers` maps a package name to the
    marker written on the edge that leads to it.
    """
    markers = markers or {}
    extras = extras or {}
    edges = edges or {}

    def rows(mapping: dict[str, str | tuple]) -> str:
        parts = []
        for name, value in mapping.items():
            marker = markers.get(name)
            if isinstance(value, tuple):  # (version, extra-requested)
                parts.append(f'{{ name = "{name}", extra = "{value[1]}" }}')
            elif marker:
                parts.append(f'{{ name = "{name}", marker = "{marker}" }}')
            else:
                parts.append(f'{{ name = "{name}" }}')
        return "[" + ", ".join(parts) + "]"

    chunks = [
        '[[package]]\nname = "ephe"\nversion = "0.1.0"\nsource = { editable = "." }',
        f"dependencies = {rows(dict(always_on))}",
    ]
    for extra, mapping in extras.items():
        chunks.append(f"[package.optional-dependencies]\n{extra} = {rows(dict(mapping))}")
    for name, version in list(always_on.items()) + [
        (name, value) for mapping in extras.values() for name, value in mapping.items()
    ]:
        if isinstance(version, tuple):
            continue
        chunks.append(
            f'[[package]]\nname = "{name}"\nversion = "{version}"\nsource = {{ registry = "https://pypi.org/simple" }}'
        )
        if name in edges:
            chunks.append(f"dependencies = {rows(dict(edges[name]))}")
    return "\n\n".join(chunks) + "\n"


def lock_from(*, always_on: dict[str, str], **kwargs) -> instrument.Lock:
    return instrument.read_lock_text(lock_text(always_on=always_on, **kwargs), "<test lock>")


def kinds(findings: list[instrument.Finding]) -> dict[str, str]:
    return {finding.name: finding.kind for finding in findings}


class TestRefusal:
    def test_given_a_planted_version_then_the_drift_is_named_and_the_run_refuses(self):
        # GIVEN a lock pinning the product's one dependency at 1.0.0, and an environment at 0.9.0
        lock = lock_from(always_on={"fastapi": "1.0.0"})
        # WHEN the environment is compared
        findings = instrument.compare(lock, {"fastapi": "0.9.0"})
        # THEN the drift is named with both numbers and the verdict refuses
        assert kinds(findings) == {"fastapi": "drift"}
        assert findings[0].installed == "0.9.0"
        assert findings[0].pinned == "1.0.0"
        code, lines = instrument.report(lock, findings, python="py", installed_count=1)
        assert code == instrument.EXIT_DIFFERS
        assert "FAIL" in lines[0]

    def test_given_the_pinned_versions_then_the_run_passes(self):
        # GIVEN the same lock and an environment that matches it exactly
        lock = lock_from(always_on={"fastapi": "1.0.0", "pillow": "2.3.4"})
        # WHEN compared
        findings = instrument.compare(lock, {"fastapi": "1.0.0", "pillow": "2.3.4"})
        # THEN nothing is reported and the exit is clean
        assert findings == []
        code, lines = instrument.report(lock, findings, python="py", installed_count=2)
        assert code == instrument.EXIT_OK
        assert "PASS" in lines[0]

    def test_given_a_missing_always_on_dependency_then_the_run_refuses(self):
        # GIVEN a dependency the product imports unconditionally
        lock = lock_from(always_on={"fastapi": "1.0.0"})
        # WHEN it is not installed at all
        findings = instrument.compare(lock, {})
        # THEN it is a missing product dependency, not a silent pass
        assert kinds(findings) == {"fastapi": "missing"}
        assert instrument.report(lock, findings, python="py", installed_count=0)[0] == instrument.EXIT_DIFFERS


class TestColumns:
    def test_given_an_opt_in_feature_not_installed_then_it_is_printed_and_does_not_refuse(self):
        # GIVEN a `voice` extra the user never installed and a product dependency that matches
        lock = lock_from(always_on={"fastapi": "1.0.0"}, extras={"voice": {"faster-whisper": "1.2.1"}})
        # WHEN only the always-on half is installed
        findings = instrument.compare(lock, {"fastapi": "1.0.0"})
        # THEN the feature reads as absent and the exit stays clean
        assert kinds(findings) == {"faster-whisper": "absent"}
        assert instrument.report(lock, findings, python="py", installed_count=1)[0] == instrument.EXIT_OK

    def test_given_an_opt_in_feature_at_the_wrong_version_then_it_refuses(self):
        # GIVEN the same extra, installed but not at the pinned version
        lock = lock_from(always_on={"fastapi": "1.0.0"}, extras={"voice": {"faster-whisper": "1.2.1"}})
        # WHEN it is present at another version — the wasmtime case: a runtime nobody re-read
        findings = instrument.compare(lock, {"fastapi": "1.0.0", "faster-whisper": "0.9.0"})
        # THEN a running copy at the wrong version is a product deviation
        assert kinds(findings) == {"faster-whisper": "drift"}
        assert instrument.report(lock, findings, python="py", installed_count=2)[0] == instrument.EXIT_DIFFERS

    def test_given_a_suite_tool_at_the_wrong_version_then_it_is_printed_and_does_not_refuse(self):
        # GIVEN `dev` carries the suite's own tools and one of them drifted
        lock = lock_from(always_on={"fastapi": "1.0.0"}, extras={"dev": {"pytest": "9.1.1"}})
        # WHEN the environment runs a different pytest
        findings = instrument.compare(lock, {"fastapi": "1.0.0", "pytest": "9.2.0"})
        # THEN the fact is named in the dev column and ships nothing broken
        assert kinds(findings) == {"pytest": "dev-drift"}
        assert instrument.report(lock, findings, python="py", installed_count=2)[0] == instrument.EXIT_OK

    def test_given_an_extra_nobody_classified_then_it_is_held_to_the_lock(self):
        lock = lock_from(always_on={"fastapi": "1.0.0"}, extras={"telemetry": {"opentelemetry": "1.0.0"}})
        findings = instrument.compare(lock, {"fastapi": "1.0.0", "opentelemetry": "0.5.0"})
        # An extra absent from DEV_EXTRAS is product: a missing classification cannot excuse it.
        assert kinds(findings) == {"opentelemetry": "drift"}

    def test_given_a_package_no_closure_contains_then_it_is_undeclared_and_printed(self):
        # GIVEN a distribution the lock never mentions — the `pip` in a venv nobody declared
        lock = lock_from(always_on={"fastapi": "1.0.0"})
        # WHEN it is installed anyway
        findings = instrument.compare(lock, {"fastapi": "1.0.0", "pip": "26.3"})
        # THEN it is named, and a lock cannot demand an absence so the run still passes
        assert kinds(findings) == {"pip": "undeclared"}
        assert instrument.report(lock, findings, python="py", installed_count=2)[0] == instrument.EXIT_OK

    def test_given_the_root_package_installed_editable_then_it_is_not_undeclared(self):
        lock = lock_from(always_on={"fastapi": "1.0.0"})
        findings = instrument.compare(lock, {"fastapi": "1.0.0", ROOT: "0.1.0"})
        assert kinds(findings) == {}


class TestTransitiveAndMarkers:
    def test_given_a_dependency_of_a_dependency_then_the_drift_is_found_through_the_graph(self):
        lock = lock_from(always_on={"fastapi": "1.0.0"}, edges={"fastapi": {"starlette": "0.40.0"}})
        findings = instrument.compare(lock, {"fastapi": "1.0.0", "starlette": "0.39.0"})
        assert kinds(findings) == {"starlette": "drift"}

    def test_given_an_extra_requested_by_a_dependency_then_its_packages_are_required(self):
        # GIVEN `uvicorn[standard]`, whose extra carries httptools — the shape a bare
        # `dependencies`-only walk would miss, because those packages sit under the
        # dependency's own `optional-dependencies` table
        body = (
            '[[package]]\nname = "ephe"\nversion = "0.1.0"\nsource = { editable = "." }\n'
            'dependencies = [ { name = "uvicorn", extra = "standard" } ]\n\n'
            '[[package]]\nname = "uvicorn"\nversion = "1.0.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n'
            'optional-dependencies = { standard = [ { name = "httptools" } ] }\n\n'
            '[[package]]\nname = "httptools"\nversion = "0.6.0"\n'
            'source = { registry = "https://pypi.org/simple" }\n'
        )
        lock = instrument.read_lock_text(body, "<test lock>")
        # WHEN nothing is installed
        findings = instrument.compare(lock, {})
        # THEN the extra's own dependency is a required product package
        assert kinds(findings) == {"httptools": "missing", "uvicorn": "missing"}
        # WHEN both are installed and only the deeper one drifted
        findings = instrument.compare(lock, {"uvicorn": "1.0.0", "httptools": "0.5.0"})
        # THEN the drift under the extra still refuses
        assert kinds(findings) == {"httptools": "drift"}

    def test_given_a_marker_that_holds_here_then_the_package_is_required(self):
        lock = lock_from(always_on={"anyio": "4.0.0"}, markers={"anyio": "python_version >= '3.0'"})
        findings = instrument.compare(lock, {}, admits=instrument.marker_admits()[0])
        assert kinds(findings) == {"anyio": "missing"}

    def test_given_a_marker_that_excludes_this_interpreter_then_its_absence_is_gated(self):
        # GIVEN an edge no interpreter here can satisfy
        lock = lock_from(always_on={"colorama": "0.4.6"}, markers={"colorama": "python_version < '3.0'"})
        # WHEN it is not installed
        findings = instrument.compare(lock, {}, admits=instrument.marker_admits()[0])
        # THEN the run says gated and passes
        assert kinds(findings) == {"colorama": "gated"}
        assert instrument.report(lock, findings, python="py", installed_count=0)[0] == instrument.EXIT_OK

    def test_given_a_conditioned_package_installed_at_the_wrong_version_then_it_is_named_not_refused(self):
        # GIVEN the same excluded edge, but a copy is installed anyway
        lock = lock_from(always_on={"colorama": "0.4.6"}, markers={"colorama": "python_version < '3.0'"})
        # WHEN it drifted
        findings = instrument.compare(lock, {"colorama": "0.1.0"}, admits=instrument.marker_admits()[0])
        # THEN the fact is printed — the product cannot reach it here, so it does not refuse
        assert kinds(findings) == {"colorama": "gated-drift"}
        assert instrument.report(lock, findings, python="py", installed_count=1)[0] == instrument.EXIT_OK

    def test_given_a_requirement_written_once_per_resolution_environment_then_it_stays_required(self):
        # GIVEN uv's way of writing one requirement twice, once per resolution marker, which is
        # what made a first version of this instrument call `numpy` conditional
        def root(first: str, second: str) -> str:
            return (
                lock_text(always_on={})
                + '\n\n[[package]]\nname = "ephe"\nversion = "0.1.0"\nsource = { editable = "." }\n'
                f'dependencies = [ {{ name = "numpy", marker = "{first}" }},'
                f' {{ name = "numpy", marker = "{second}" }} ]\n\n'
                '[[package]]\nname = "numpy"\nversion = "2.5.2"\n'
                'source = { registry = "https://pypi.org/simple" }\n'
            )

        low = "python_full_version < '3.12'"
        high = "python_full_version >= '3.12'"
        # ASSERTED FOR TWO RESOLUTION ENVIRONMENTS. The pair is one requirement, so no interpreter
        # may turn it into a conditional edge: the instrument used to pop one of the two edges and
        # dismiss the other as already asked, which left the first edge popped deciding the class.
        # Both spellings are run below, and the environment is named rather than inherited, so this
        # case says the same thing on the interpreter that runs it.
        for version in ("3.11.9", "3.13.1"):
            admits, _ = instrument.marker_admits(instrument.resolution_environment(version))
            for first, second in ((low, high), (high, low)):
                lock = instrument.read_lock_text(root(first, second), "<test lock>")
                findings = instrument.compare(lock, {"numpy": "2.0.0"}, admits=admits)
                assert kinds(findings) == {"numpy": "drift"}, (version, first, second)

    def test_given_an_edge_no_environment_in_the_lock_satisfies_then_it_stays_excused(self):
        # GIVEN a requirement whose every spelling is unsatisfiable, so it is genuinely conditional
        lock = instrument.read_lock_text(
            lock_text(always_on={})
            + '\n\n[[package]]\nname = "ephe"\nversion = "0.1.0"\nsource = { editable = "." }\n'
              "dependencies = [ { name = \"numpy\", marker = \"python_version < '3.0'\" },"
              ' { name = "numpy", marker = "python_version < \'3.0\'" } ]\n\n'
              '[[package]]\nname = "numpy"\nversion = "2.5.2"\n'
              'source = { registry = "https://pypi.org/simple" }\n',
            "<test lock>",
        )
        admits, _ = instrument.marker_admits(instrument.resolution_environment("3.11.9"))
        findings = instrument.compare(lock, {"numpy": "2.0.0"}, admits=admits)
        # THEN the pair prints as a drifted conditional and does not refuse the run
        assert kinds(findings) == {"numpy": "gated-drift"}

    def test_given_no_injected_environment_then_markers_answer_for_this_interpreter(self):
        # The shipped gate judges one environment: the interpreter whose distributions it compared.
        admits, markers = instrument.marker_admits()
        assert admits("python_version >= '3.0'") is True
        assert admits("python_version < '3.0'") is False
        # The account is read after the asking, which is the only order that can state a fact.
        assert markers.evaluated is True
        assert (markers.asked, markers.decided, markers.errored) == (2, 2, 0)


class TestTheMarkerAccountTellsTheTruth:
    """`evaluated` was a constant until 2026-11-24; these cases make the lie unproducible.

    The account is the one place where this instrument claims it decided something about a
    conditional edge, so a run in which every marker raised may not print that markers were
    evaluated. Each case plants the marker text itself — an unreadable marker is what a lock
    written by another `uv` delivers — and reads the account after the comparison, the order the
    command uses.
    """

    #: Two texts `packaging.markers.Marker` refuses to parse, distinct so both are asked.
    UNREADABLE = ("this is not a marker", "python_version ===")

    @staticmethod
    def _root_with(marker_texts: tuple[str, ...]) -> str:
        edges = ", ".join('{ name = "numpy", marker = "%s" }' % text for text in marker_texts)
        return (
            '[[package]]\nname = "ephe"\nversion = "0.1.0"\nsource = { editable = "." }\n'
            f"dependencies = [{edges}]\n\n"
            '[[package]]\nname = "numpy"\nversion = "2.5.2"\n'
            'source = { registry = "https://pypi.org/simple" }\n'
        )

    def test_given_every_marker_raises_then_the_run_refuses_to_claim_evaluation(self):
        # GIVEN a lock whose only conditional edges carry markers the library cannot parse
        lock = instrument.read_lock_text(self._root_with(self.UNREADABLE), "<test lock>")
        admits, account = instrument.marker_admits(instrument.resolution_environment("3.13.1"))
        findings = instrument.compare(lock, {"numpy": "2.5.2"}, admits=admits)
        # THEN nothing was decided, the fallback answered both, and the report says so by name
        assert account.available is True, "packaging is present; it is the markers that failed"
        assert (account.asked, account.decided, account.errored) == (2, 0, 2), account
        assert account.evaluated is False
        code, lines = instrument.report(lock, findings, python="py", installed_count=1, markers=account)
        assert code == instrument.EXIT_OK
        assert "NOT evaluated — all 2 marker(s) raised" in lines[1], lines[1]

    def test_given_one_readable_marker_beside_a_broken_one_then_the_account_says_partially(self):
        lock = instrument.read_lock_text(
            self._root_with(("python_version >= '3.0'", self.UNREADABLE[0])), "<test lock>"
        )
        admits, account = instrument.marker_admits(instrument.resolution_environment("3.13.1"))
        findings = instrument.compare(lock, {"numpy": "2.5.2"}, admits=admits)
        assert (account.asked, account.decided, account.errored) == (2, 1, 1), account
        assert account.evaluated is False
        _, lines = instrument.report(lock, findings, python="py", installed_count=1, markers=account)
        assert "partially evaluated — 1 of 2 decided here" in lines[1], lines[1]

    def test_given_an_unreadable_marker_then_the_edge_is_still_held_to_the_lock(self):
        """The conservative direction the fix must not move: unanswered is judged, never excused."""
        lock = instrument.read_lock_text(self._root_with((self.UNREADABLE[0],)), "<test lock>")
        admits, account = instrument.marker_admits(instrument.resolution_environment("3.13.1"))
        findings = instrument.compare(lock, {}, admits=admits)
        assert kinds(findings) == {"numpy": "missing"}
        assert account.evaluated is False
        code, _ = instrument.report(lock, findings, python="py", installed_count=0, markers=account)
        assert code == instrument.EXIT_DIFFERS

    def test_given_a_clean_marker_run_then_the_account_states_what_it_decided(self):
        lock = instrument.read_lock_text(
            self._root_with(("python_version >= '3.0'", "python_version < '3.0'")), "<test lock>"
        )
        admits, account = instrument.marker_admits(instrument.resolution_environment("3.13.1"))
        instrument.compare(lock, {"numpy": "2.5.2"}, admits=admits)
        assert (account.asked, account.decided, account.errored) == (2, 2, 0), account
        assert account.evaluated is True
        assert account.note().startswith("evaluated here — 2 of 2")

    def test_given_a_lock_with_no_marker_at_all_then_nothing_was_asked(self):
        lock = lock_from(always_on={"fastapi": "1.0.0"})
        admits, account = instrument.marker_admits(instrument.resolution_environment("3.13.1"))
        instrument.compare(lock, {"fastapi": "1.0.0"}, admits=admits)
        assert account.asked == 0
        assert account.evaluated is False, "an empty account may not read as a decided one"
        assert account.note() == "no conditional edge in this lock; nothing was asked"

    def test_given_no_packaging_then_the_account_names_the_missing_library(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "packaging.markers", None)
        admits, account = instrument.marker_admits()
        assert admits("python_version < '3.0'") is True, "the absent library excuses nothing"
        assert account.available is False
        assert (account.asked, account.decided, account.errored) == (0, 0, 0), account
        assert account.note().startswith("NOT evaluated — no packaging library")

    def test_the_machine_readable_run_carries_the_counts_beside_the_bool(self):
        """A json consumer may not get `decided` without being told how many were asked."""
        lock = lock_from(always_on={"fastapi": "1.0.0"})
        account = instrument.MarkerEvaluation(available=True, asked=3, decided=3, errored=0)
        payload = json.loads(
            instrument.as_json(lock, [], python="py", installed_count=1, markers=account)
        )
        assert payload["markers_evaluated"] is True
        assert (payload["markers_asked"], payload["markers_decided"], payload["markers_errored"]) == (3, 3, 0)
        unmeasured = json.loads(instrument.as_json(lock, [], python="py", installed_count=1))
        assert unmeasured["markers_evaluated"] is None, "an unmeasured run may not report a verdict"


class TestProviderAndPlumbing:
    @dataclass
    class FakeDist:
        name: str
        version: str

        @property
        def metadata(self):
            return {"Name": self.name}

    def test_given_an_injected_reader_then_the_environment_comes_from_the_test(self):
        # GIVEN distributions named in mixed spellings and one name installed twice
        rows = [
            TestProviderAndPlumbing.FakeDist("Python_DateUtil", "2.9.0"),
            TestProviderAndPlumbing.FakeDist("fastapi", "1.0.0"),
            TestProviderAndPlumbing.FakeDist("fastapi", "1.0.1"),
        ]
        # WHEN the provider reads them
        versions, shadows = instrument.installed_distributions(reader=lambda: rows)
        # THEN names are canonical, one version wins, and the doubled name is reported
        assert versions["python-dateutil"] == "2.9.0"
        assert shadows == ["fastapi"]

    def test_given_a_distribution_whose_metadata_raises_then_the_run_still_counts_it_as_unreadable(self):
        # GIVEN a broken dist-info that raises on access
        class Broken:
            @property
            def metadata(self):
                raise RuntimeError("corrupt")

            @property
            def version(self):
                raise RuntimeError("corrupt")

        # WHEN the provider reads the environment
        versions, shadows = instrument.installed_distributions(reader=lambda: [Broken()])
        # THEN it is skipped without taking the whole scan down with it
        assert versions == {} and shadows == []

    def test_given_a_clean_environment_through_the_cli_then_json_and_exit_zero_agree(self, tmp_path, capsys, monkeypatch):
        # GIVEN a lock on disk and an environment handed in through the provider seam
        lock_file = tmp_path / "uv.lock"
        lock_file.write_text(lock_text(always_on={"fastapi": "1.0.0"}), encoding="utf-8")
        monkeypatch.setattr(
            instrument, "installed_distributions", lambda reader=None: ({"fastapi": "1.0.0"}, [])
        )
        # WHEN the command runs
        code = instrument.main(["--lock", str(lock_file), "--json"])
        payload = json.loads(capsys.readouterr().out)
        # THEN the report is machine-readable and says there is nothing to refuse
        assert code == instrument.EXIT_OK
        assert payload["findings"] == []
        assert payload["refusing"] == ["drift", "missing"]

    def test_given_a_planted_drift_through_the_cli_then_the_command_exits_one(self, tmp_path, capsys, monkeypatch):
        # GIVEN the same lock and an environment one version off
        lock_file = tmp_path / "uv.lock"
        lock_file.write_text(lock_text(always_on={"fastapi": "1.0.0"}), encoding="utf-8")
        monkeypatch.setattr(
            instrument, "installed_distributions", lambda reader=None: ({"fastapi": "0.9.9"}, [])
        )
        # WHEN the command runs
        code = instrument.main(["--lock", str(lock_file)])
        printed = capsys.readouterr().out
        # THEN the printed line and the exit code both refuse
        assert code == instrument.EXIT_DIFFERS
        assert "fastapi" in printed and "drift" in printed

    def test_given_a_lock_without_a_root_package_then_the_command_refuses_to_guess(self, tmp_path, capsys):
        # GIVEN a file that is valid TOML but no project lock
        lock_file = tmp_path / "uv.lock"
        lock_file.write_text('[[package]]\nname = "anyio"\nversion = "4.0.0"\n', encoding="utf-8")
        # WHEN the command runs
        code = instrument.main(["--lock", str(lock_file)])
        # THEN it says so on stderr instead of comparing against nothing
        assert code == instrument.EXIT_DIFFERS
        assert "no editable or virtual root package" in capsys.readouterr().err

    def test_given_the_real_interpreter_then_markers_are_evaluated_not_assumed(self):
        """`evaluated` is earned by a decided marker, never handed out for an empty run."""
        admits, markers = instrument.marker_admits()
        assert markers.evaluated is False, "an account that was never asked may not claim evaluation"
        assert admits("python_version >= '3.0'") is True
        assert admits("python_version < '3.0'") is False
        assert markers.evaluated is True
        assert markers.note().startswith("evaluated here")

    def test_given_the_two_dev_extras_then_the_split_is_the_suite_s_own_tools(self):
        assert instrument.DEV_EXTRAS == frozenset({"dev", "bench"})
        # Frozen so no test can widen the excuse column at runtime.
        with pytest.raises(AttributeError):
            instrument.DEV_EXTRAS.add("sandbox")
