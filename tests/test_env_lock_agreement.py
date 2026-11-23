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
        body = (
            lock_text(always_on={})
            + '\n\n[[package]]\nname = "ephe"\nversion = "0.1.0"\nsource = { editable = "." }\n'
            'dependencies = [ { name = "numpy", marker = "python_full_version < \'3.12\'" },'
            ' { name = "numpy", marker = "python_full_version >= \'3.12\'" } ]\n\n'
            '[[package]]\nname = "numpy"\nversion = "2.5.2"\n'
            'source = { registry = "https://pypi.org/simple" }\n'
        )
        lock = instrument.read_lock_text(body, "<test lock>")
        # WHEN this interpreter (>= 3.12) is compared against a drifted numpy
        findings = instrument.compare(lock, {"numpy": "2.0.0"}, admits=instrument.marker_admits()[0])
        # THEN the pair of markers counts as required and the drift refuses
        assert kinds(findings) == {"numpy": "drift"}


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
        # GIVEN this environment, where packaging is present through the lock itself
        admits, evaluated = instrument.marker_admits()
        # WHEN a true and a false marker are asked
        assert evaluated is True
        assert admits("python_version >= '3.0'") is True
        assert admits("python_version < '3.0'") is False

    def test_given_the_two_dev_extras_then_the_split_is_the_suite_s_own_tools(self):
        assert instrument.DEV_EXTRAS == frozenset({"dev", "bench"})
        # Frozen so no test can widen the excuse column at runtime.
        with pytest.raises(AttributeError):
            instrument.DEV_EXTRAS.add("sandbox")
