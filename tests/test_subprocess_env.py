"""tests/test_subprocess_env.py — the loader allowlist carries, application state does not.

The CI failures this guards against are on the self-hosted arm64 runner, and they are two
causes wearing one shape: a from-scratch environment cannot exec the shared-linked
interpreter (exit 127, measured with the runner's own tool-cache CPython on 2026-10-09),
and it cannot import what the parent interpreter can import (`No module named pytest` on
the py3.12 leg, whose tool-cache `python` does not list its own `site-packages`). A hosted
runner shows nothing — its build carries an rpath, and its paths are the ones CPython
expects — so the contract is pinned here instead: which keys the base environment
may hold, and which it must never invent or inherit.

Two host shapes are needed, and the split is the point: the dictionary assertions want a
machine with no loader variable at all, while the assertions that exec a real child need
whatever loader view this interpreter requires. Getting that wrong is a test that passes
on a Mac and fails on the runner for reasons that have nothing to do with the helper.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.subprocess_env import LOADER_KEYS, hermetic_env, python_path_for

#: The repository root: the directory `tests/…` is imported from.
REPO = Path(__file__).resolve().parents[1]

#: Host state a hermetic child must not see: import paths, product config, locale.
HOST_LEAKS = {
    "PYTHONPATH": "/host/other-project",
    "EPHE_MODEL": "whatever-the-host-runs",
    "EPHE_CONFIG_DIR": "/host/.ephe",
    "LANG": "de_DE.UTF-8",
}

RUNNER_TOOL_LIB = "/runner/_work/_tool/Python/3.13.16/arm64/lib"

#: This machine's loader view, read before any fixture touches `os.environ`: a
#: shared-linked interpreter needs it to exec at all, and the fixtures below delete it.
_MACHINE_LOADER = {key: value for key in LOADER_KEYS if (value := os.environ.get(key)) is not None}


@pytest.fixture(autouse=True)
def host_without_loader_vars(monkeypatch):
    """A host that leaks application state and carries no loader variable.

    Both halves are load-bearing: the Spark runner *does* set `LD_LIBRARY_PATH`, and a dev
    machine usually sets none — fixing one shape makes the assertions mean the same thing
    everywhere.
    """
    for key in LOADER_KEYS:
        monkeypatch.delenv(key, raising=False)
    for key, value in HOST_LEAKS.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def machine_loader_env(host_without_loader_vars, monkeypatch):
    """Put this machine's loader variables back, for a test that really execs a child."""
    for key, value in _MACHINE_LOADER.items():
        monkeypatch.setenv(key, value)


class TestLoaderKeysCarryThrough:
    def test_given_ld_library_path_when_env_is_built_then_it_reaches_the_child(self, monkeypatch):
        """GIVEN the shared-linked interpreter's loader path WHEN the base env is built
        THEN the child is told where libpython lives — that is the 127 fix."""
        monkeypatch.setenv("LD_LIBRARY_PATH", RUNNER_TOOL_LIB)
        assert hermetic_env()["LD_LIBRARY_PATH"] == RUNNER_TOOL_LIB

    @pytest.mark.parametrize("key", ["DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH"])
    def test_given_a_macos_loader_key_when_env_is_built_then_it_carries_too(self, monkeypatch, key):
        """GIVEN dyld's two spellings on macOS WHEN the base env is built THEN both pass."""
        monkeypatch.setenv(key, "/tool/lib")
        assert hermetic_env()[key] == "/tool/lib"

    def test_given_a_real_child_when_it_runs_on_the_base_env_then_it_exits_clean(
        self, machine_loader_env
    ):
        """GIVEN the base env as this machine needs it WHEN a child execs
        THEN it runs AND reports no host application state.

        On the runner's shared-linked interpreter the exec half is the call that used to
        return 127; the empty JSON is the hermeticity half of the same proof.
        """
        probe = (
            "import json, os;"
            "print(json.dumps({k: v for k, v in os.environ.items()"
            " if k == 'PYTHONPATH' or k.startswith('EPHE_')}))"
        )
        run = subprocess.run(
            [sys.executable, "-c", probe],
            env=hermetic_env(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert run.returncode == 0, run.stderr
        assert json.loads(run.stdout.strip()) == {}


class TestNothingElseIsInherited:
    def test_given_no_loader_var_on_the_host_when_env_is_built_then_none_is_invented(self):
        """GIVEN a host without any loader variable WHEN the base env is built
        THEN the child gets none: an invented path would be a lie about the machine."""
        assert not set(hermetic_env()) & set(LOADER_KEYS)

    def test_given_caller_keys_when_env_is_built_then_the_env_is_exactly_those(self):
        """GIVEN PATH/HOME/PYTHONPATH named by the caller WHEN the base env is built
        THEN those three and nothing else — the from-scratch property is unchanged."""
        assert hermetic_env(PATH="/usr/bin:/bin", HOME="/tmp/home", PYTHONPATH="") == {
            "PATH": "/usr/bin:/bin",
            "HOME": "/tmp/home",
            "PYTHONPATH": "",
        }

    def test_given_a_carried_loader_key_when_the_caller_repins_it_then_the_caller_wins(
        self, monkeypatch
    ):
        """GIVEN the host loader path WHEN the caller names one too THEN the caller's
        value stands: the allowlist carries, it does not override."""
        monkeypatch.setenv("LD_LIBRARY_PATH", "/host/lib")
        assert hermetic_env(LD_LIBRARY_PATH="/chosen/lib")["LD_LIBRARY_PATH"] == "/chosen/lib"

    def test_given_overrides_when_env_is_built_then_the_host_keeps_its_own_state(self):
        """GIVEN a switch the test wants for the child WHEN the base env is built
        THEN only the child gets it — no mutation of the pytest process."""
        hermetic_env(EPHE_MEMORY_MCP_WRITE="1")
        assert "EPHE_MEMORY_MCP_WRITE" not in os.environ


class TestPackageRootsCarryThrough:
    def test_the_root_of_a_module_is_the_directory_that_holds_it(self):
        """GIVEN a package and a dotted module WHEN their roots are derived
        THEN each names the directory a `sys.path` entry has to be."""
        assert (Path(python_path_for("pytest")) / "pytest").is_dir()
        assert python_path_for("tests.subprocess_env") == str(REPO)

    def test_two_modules_sharing_a_root_are_listed_once(self):
        """GIVEN two modules of one installation WHEN derived together
        THEN the value is a single entry: no duplicated path, no ordering luck."""
        assert python_path_for("pytest", "_pytest") == python_path_for("pytest")

    def test_a_package_only_the_parent_knows_reaches_the_child(
        self, tmp_path, monkeypatch, machine_loader_env
    ):
        """GIVEN a package the child's interpreter cannot see by default, injected into the
        parent the way a job provides a root, WHEN the derived PYTHONPATH goes to the child
        THEN the child imports it — and without that entry the same child fails.

        That pair is the py3.12 leg of run 37954384269 in miniature: the scrubbed environment
        changed the interpreter's package offer, so the test measured the machine and not the
        switch. It bites on every machine, because the package is nowhere in a default path.
        """
        name = "ephe_probe_pkg"
        package = tmp_path / name
        package.mkdir()
        (package / "__init__.py").write_text("MARKER = 'from-derived-root'\n", encoding="utf-8")
        spec = importlib.util.spec_from_file_location(name, package / "__init__.py")
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, name, module)
        spec.loader.exec_module(module)

        root = python_path_for(name)
        assert Path(root).resolve() == tmp_path.resolve()

        probe = f"import {name}; print({name}.MARKER)"
        derived = subprocess.run(
            [sys.executable, "-c", probe],
            env=hermetic_env(PYTHONPATH=root),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert derived.returncode == 0, derived.stderr
        assert derived.stdout.strip() == "from-derived-root"

        without = subprocess.run(
            [sys.executable, "-c", probe],
            env=hermetic_env(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert without.returncode != 0, "no root, no package — that is the CI symptom"
        assert "No module named" in without.stderr

    def test_the_child_resolves_pytest_to_the_parent_own_file(self, machine_loader_env):
        """GIVEN the derived root WHEN a child imports pytest
        THEN it lands on the same file the parent uses: the entry offers the package,
        it does not shadow it with a second copy."""
        run = subprocess.run(
            [sys.executable, "-c", "import pytest; print(pytest.__file__)"],
            env=hermetic_env(PYTHONPATH=python_path_for("pytest")),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert run.returncode == 0, run.stderr
        assert Path(run.stdout.strip()).resolve() == Path(pytest.__file__).resolve()
