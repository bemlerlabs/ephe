"""The cell runtime floor: an engine that is patched where it runs, and a config that still builds.

Ephemora Cell 1.1.0 declares ``wasmtime<48``. That bound predates the engine the advisories were
patched in. PyPI publishes 48.0.0 but not the 48.0.6 fix, and not the 49.0.3 fix; 50.0.1 is the
first published release outside every affected range. Ephe overrides the transitive bound.

Two different facts are checked here, and the file keeps them apart because they fail apart.
The declaration is a fact about `pyproject.toml`, so it is read out of that file with `tomllib`.
The run is a fact about the interpreter, so it is read out of the installed distribution with
`importlib.metadata`. A lock records an intention; the version that answers ``import wasmtime``
is the one the cell executes, which is why no case here judges the installed engine against
`uv.lock`. A file is read where the constraint exists only in a file the product cannot import:
the declaration, the lock's own resolution, and the installer's pip path.

The specifier parser is small and local on purpose: the tree writes four operators, an operator it
cannot read raises instead of reading as no bound, and no resolver library is pulled in to decide
a security bound.
"""
from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable
from importlib import metadata
from pathlib import Path

import pytest

from tests.toml_compat import tomllib

REPO = Path(__file__).resolve().parent.parent
ENGINE = "wasmtime"
#: The step that restates the floor for the pip path, and the date the gap was measured.
INSTALLER_STEP = "install.sh:530-546"
MEASURED_ON = "2026-11-01"

#: The only specifiers this file undertands to read. Anything else refuses, so a bound written in
#: a syntax nobody thought about cannot quietly become "no bound".
SUPPORTED_OPERATORS = (">=", "==", "<", "<=")
_OPERATOR = re.compile(r"\s*(>=|<=|==|!=|>|<|~=|\^)?\s*([0-9][0-9A-Za-z.\-]*)\s*")
_NAME_AND_SPECIFIER = re.compile(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(.*)$", re.S)


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _declared_requirements(name: str, text: str | None = None) -> tuple[str, ...]:
    """Every requirement the project declares for `name`, from the file that carries the bounds."""
    body = tomllib.loads(text if text is not None else (REPO / "pyproject.toml").read_text(encoding="utf-8"))
    project = body.get("project") or {}
    uv_block = (body.get("tool") or {}).get("uv") or {}
    rows: list[str] = []
    rows.extend(uv_block.get("override-dependencies") or [])
    rows.extend(uv_block.get("constraint-dependencies") or [])
    rows.extend(project.get("dependencies") or [])
    for extra_rows in (project.get("optional-dependencies") or {}).values():
        rows.extend(extra_rows)
    found = []
    for row in rows:
        if not isinstance(row, str):
            continue
        match = _NAME_AND_SPECIFIER.match(row)
        if match is None or _canonical(match.group(1)) != _canonical(name):
            continue
        if not match.group(2).strip():
            raise AssertionError(f"{name} is declared bare, with no bound to check")
        found.append(row.strip())
    if not found:
        raise AssertionError(f"{name} carries no declared bound")
    return tuple(dict.fromkeys(found))


def _pyproject_with_engine_floor(bound: str) -> str:
    """A declaration body whose only engine statement is one override row at `bound`.

    A plant passes this so the bound under test arrives from the file shape rather than from a
    constant in here; the reader below cannot tell it from the shipped one.
    """
    return (
        '[project]\nname = "ephe"\nversion = "0.1.0"\n\n'
        "[project.optional-dependencies]\nsandbox = ['ephemora-cell>=1.1.0,<1.2']\n\n"
        f'[tool.uv]\noverride-dependencies = ["{ENGINE}{bound}"]\n'
    )


def _clauses(requirement: str) -> tuple[tuple[str, tuple[int, ...]], ...]:
    """The operator/version pairs of one requirement string, e.g. ``>=50.0.1,<51``."""
    match = _NAME_AND_SPECIFIER.match(requirement)
    assert match, f"cannot read the requirement {requirement!r}"
    clauses: list[tuple[str, tuple[int, ...]]] = []
    for piece in match.group(2).split(";")[0].split(","):
        if not piece.strip():
            continue
        clause = _OPERATOR.fullmatch(piece)
        if clause is None:
            raise ValueError(f"cannot read the specifier {piece.strip()!r} of {requirement!r}; refusing to read it as no bound")
        operator = clause.group(1)
        if operator not in SUPPORTED_OPERATORS:
            raise ValueError(f"{operator!r} in {requirement!r} is not a bound this file can check")
        clauses.append((operator, _version(clause.group(2), requirement)))
    if not clauses:
        raise ValueError(f"{requirement!r} carries no readable bound")
    return tuple(clauses)


def _version(text: str, requirement: str = "") -> tuple[int, ...]:
    """Dotted numeric version as a comparable tuple. Prerelease and local suffixes refuse."""
    parts: list[int] = []
    for chunk in text.split("."):
        digits = re.match(r"(\d+)(.*)$", chunk)
        if digits is None or digits.group(2):
            raise ValueError(
                f"cannot read the version {text!r} of {requirement!r}: a prerelease or local suffix is"
                " below the release it names, and this file will not floor it silently"
            )
        parts.append(int(digits.group(1)))
    if not parts:
        raise ValueError(f"{text!r} is not a version")
    return tuple(parts)


def _compare(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    """Compare two dotted versions of unequal length; a missing component is 0."""
    width = max(len(left), len(right))

    def padded(parts: tuple[int, ...]) -> tuple[int, ...]:
        return parts + (0,) * (width - len(parts))

    left, right = padded(left), padded(right)
    return (left > right) - (left < right)


def _unsatisfied(version: tuple[int, ...], clauses: tuple[tuple[str, tuple[int, ...]], ...]) -> list[str]:
    broken = []
    for operator, bound in clauses:
        order = _compare(version, bound)
        if (operator == ">=" and order < 0) or (operator == "==" and order != 0) or (
            operator == "<" and order >= 0
        ) or (operator == "<=" and order > 0):
            broken.append(f"{operator}{'.'.join(str(part) for part in bound)}")
    return broken


def _installed_engine_version(reader: Callable[[str], str] | None = None) -> str | None:
    """The engine version this interpreter would load, or None when the extra was never installed."""
    read = reader or metadata.version
    try:
        return str(read(ENGINE))
    except metadata.PackageNotFoundError:
        return None


def _refusal(installed: str, unsatisfied: list[str], declaration: str | None = None) -> str:
    """The refusal text, written to name the way out rather than only the fact."""
    override = _declared_requirements(ENGINE, text=declaration)[0]
    return (
        f"the {ENGINE} answering `import {ENGINE}` here is {installed}, outside "
        f"{', '.join(unsatisfied)} as declared in pyproject.toml. uv.lock records an intention; the"
        f" version answering the import is the one the cell executes. {INSTALLER_STEP} names this"
        f" gap — measured {MEASURED_ON}, a pip resolver follows ephemora-cell's own bound because"
        f" only uv reads [tool.uv] override-dependencies — and repairs it with"
        f' `pip install "{override}"`. The lock\'s own pin lands through'
        f" `uv sync --frozen --inexact --extra sandbox`, and scripts/env_lock_agreement.py prints"
        f" every gap of this kind in one run."
    )


def _assert_installed_engine(
    *,
    reader: Callable[[str], str] | None = None,
    declaration: str | None = None,
) -> str:
    """Refuse unless the engine this interpreter loads sits inside every declared bound.

    Both sides are injectable so the case can be shown refusing without touching an environment:
    `reader` stands in for `importlib.metadata.version`, `declaration` for the file the bounds are
    read from. Left alone, both are the machine and the tree this test runs on.
    """
    installed = _installed_engine_version(reader)
    if installed is None:
        pytest.skip("the sandbox extra is not installed, so nothing here imports the engine")
    version = _version(installed)
    broken: list[str] = []
    for requirement in _declared_requirements(ENGINE, text=declaration):
        broken.extend(f"{requirement!r} -> {part}" for part in _unsatisfied(version, _clauses(requirement)))
    assert not broken, _refusal(installed, broken, declaration)
    return installed


def _locked_wasmtime() -> tuple[int, ...]:
    text = (REPO / "uv.lock").read_text(encoding="utf-8")
    match = re.search(r'name = "wasmtime"\nversion = "([^"]+)"', text)
    assert match, "wasmtime is not resolved in uv.lock"
    return _version(match.group(1))


class TestTheInstalledEngine:
    """The run: what this interpreter loads, against what the project declares."""

    def test_the_engine_running_here_sits_inside_every_declared_bound(self):
        """GIVEN the patched engine, installed as part of the sandbox extra
        WHEN the version the interpreter actually loads is read from its own distribution
        THEN it satisfies each bound pyproject declares for it."""
        assert _assert_installed_engine() is not None

    def test_given_a_planted_engine_below_the_floor_then_the_case_refuses_by_version(self):
        # GIVEN the version this repository's own `.venv` carried on 2026-11-01, handed in through
        # the provider instead of read from the machine
        reader = lambda name: "47.0.1"  # noqa: E731 — one provider for this one case
        # WHEN the case checks it
        with pytest.raises(AssertionError) as info:
            _assert_installed_engine(reader=reader)
        # THEN the refusal names both versions and the way out, so a red run is actionable
        message = str(info.value)
        assert "47.0.1" in message
        assert ">=50.0.1" in message
        assert "uv.lock records an intention" in message
        assert INSTALLER_STEP in message and MEASURED_ON in message
        assert f'pip install "{ENGINE}>=50.0.1,<51"' in message
        assert "env_lock_agreement.py" in message

    def test_given_a_planted_engine_at_or_above_the_ceiling_then_the_case_refuses_too(self):
        """GIVEN the upper half of the declared range violated, which is how an unnoticed major
        bump would arrive
        WHEN the case checks it
        THEN the ceiling is enforced as well as the floor."""
        with pytest.raises(AssertionError) as info:
            _assert_installed_engine(reader=lambda name: "51.0.0")
        assert "51.0.0" in str(info.value)

    def test_given_a_planted_engine_exactly_at_the_floor_then_the_case_passes(self):
        # GIVEN the first published release outside every affected range
        # WHEN the case checks it
        assert _assert_installed_engine(reader=lambda name: "50.0.1") == "50.0.1"

    def test_given_a_planted_floor_above_the_engine_then_the_same_engine_refuses(self):
        """GIVEN the engine version that satisfies the tree's own declaration, proven by the case
        above, and a declaration raised one patch above it
        WHEN that same version is checked against the raised declaration
        THEN it refuses, and names the raised floor in the way out. The bound arrives from the
        file, so nothing in this file can be the reason the case is green."""
        raised = _pyproject_with_engine_floor(">=50.0.2,<51")
        real = _installed_engine_version()
        candidates = [value for value in dict.fromkeys([real, "50.0.1"]) if value]
        for candidate in candidates:
            with pytest.raises(AssertionError) as info:
                _assert_installed_engine(
                    reader=lambda name, value=candidate: value, declaration=raised
                )
            message = str(info.value)
            assert candidate in message
            assert ">=50.0.2" in message
            assert f'pip install "{ENGINE}>=50.0.2,<51"' in message

    def test_given_a_declaration_whose_floor_is_the_engine_itself_then_the_case_passes(self):
        """GIVEN a declaration raised to exactly the version the engine reports
        WHEN that version is checked against it
        THEN it passes, so the refusal above tracks the bound and is not a fixed mismatch."""
        declaration = _pyproject_with_engine_floor(">=50.0.0,<51")
        assert _assert_installed_engine(reader=lambda name: "50.0.0", declaration=declaration) == "50.0.0"

    def test_given_an_engine_that_was_never_installed_then_the_case_skips_with_the_reason(self):
        # GIVEN a machine where the opt-in sandbox extra was never requested
        def missing(name: str) -> str:
            raise metadata.PackageNotFoundError(name)

        # WHEN the case checks it
        with pytest.raises(pytest.skip.Exception) as info:
            _assert_installed_engine(reader=missing)
        # THEN it skips on the opt-in, and does not report a clean engine it never saw
        assert "sandbox extra is not installed" in str(info.value)


class TestTheDeclarationReader:
    """The declaration: read out of the parsed file, and unreadable things refuse."""

    def test_the_bound_is_taken_from_the_parsed_file(self):
        # GIVEN a pyproject body written the way uv's override block is written
        body = (
            '[project]\nname = "ephe"\ndependencies = ["pillow"]\n'
            "[project.optional-dependencies]\nsandbox = ['ephemora-cell>=1.1.0,<1.2']\n"
            '[tool.uv]\noverride-dependencies = ["wasmtime>=50.0.1,<51"]\n'
        )
        # WHEN the declaration is read
        # THEN the requirement arrives from the override block
        assert _declared_requirements(ENGINE, text=body) == ("wasmtime>=50.0.1,<51",)

    def test_given_a_bare_declaration_then_the_reader_refuses_instead_of_passing(self):
        # GIVEN the engine named without any bound at all
        body = '[project]\nname = "ephe"\ndependencies = ["wasmtime"]\n'
        # WHEN the declaration is read
        with pytest.raises(AssertionError, match="no bound to check"):
            _declared_requirements(ENGINE, text=body)

    def test_given_an_operator_this_file_does_not_read_then_it_raises(self):
        """GIVEN a bound written in an operator nobody here thought about
        WHEN it is checked against a version
        THEN the reader raises, and the bound never becomes an absent bound."""
        with pytest.raises(ValueError, match="not a bound this file can check"):
            _clauses("wasmtime~=50.0")

    def test_given_an_unreadable_clause_then_it_raises_rather_than_reading_no_bound(self):
        """GIVEN a clause the operator pattern cannot match
        WHEN it is parsed
        THEN it raises, because an unreadable clause must not read as no clause."""
        with pytest.raises(ValueError, match="refusing to read it as no bound"):
            _clauses("wasmtime latest")

    def test_given_a_prerelease_then_it_is_below_the_release_it_names(self):
        """GIVEN a version carrying a prerelease suffix, which names an unpublished build
        WHEN it is compared to the floor
        THEN it raises, so a suffix cannot be floored into passing."""
        with pytest.raises(ValueError, match="prerelease or local suffix"):
            _version("50.0.1rc1")

    def test_a_missing_component_reads_as_zero(self):
        """GIVEN spellings of the same release at different lengths, and two releases whose third
        component differs by more than one
        WHEN they are compared
        THEN a shortened spelling equals its full form, 49.0.3 sits below 50.0.1, and 50.0.10
        above 50.0.2 — the ordering is numeric per component."""
        assert _compare(_version("50.0"), _version("50.0.0")) == 0
        assert _compare(_version("49.0.3"), _version("50.0.1")) < 0
        assert _compare(_version("50.0.10"), _version("50.0.2")) > 0

    def test_the_ceiling_and_the_floor_are_both_enforced_by_one_string(self):
        # GIVEN the requirement the project actually declares
        clauses = _clauses(_declared_requirements(ENGINE)[0])
        # WHEN the interesting versions are asked
        assert _unsatisfied(_version("47.0.1"), clauses) == [">=50.0.1"]
        assert _unsatisfied(_version("50.0.0"), clauses) == [">=50.0.1"]
        assert _unsatisfied(_version("50.0.1"), clauses) == []
        assert _unsatisfied(_version("50.9.9"), clauses) == []
        assert _unsatisfied(_version("51.0.0"), clauses) == ["<51"]


class TestTheShippedDeclaration:
    """The lock and the installer: the two paths that have to agree with the file."""

    def test_the_locked_wasmtime_is_at_or_above_the_patched_floor(self):
        """GIVEN the dependency lock we ship
        THEN the resolved wheel is at least the floor pyproject declares. This is the intention
        side of the pair; the case above is the run, and a green run here says nothing about a
        machine that never installed the lock."""
        floor = next(bound for operator, bound in _clauses(_declared_requirements(ENGINE)[0]) if operator == ">=")
        assert _compare(_locked_wasmtime(), floor) >= 0

    def test_the_project_overrides_the_transitive_upper_bound(self):
        """GIVEN ephemora-cell declares ``wasmtime<48``
        THEN Ephe overrides that bound in its own file at or above 50.0.1, the first published
        release outside every affected range."""
        text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
        assert "override-dependencies" in text, "no uv override block"
        floor = _clauses(_declared_requirements(ENGINE)[0])
        assert _unsatisfied(_version("50.0.1"), floor) == [], f"the declared wasmtime floor excludes 50.0.1: {floor}"
        assert _compare(_locked_wasmtime(), _version("50.0.1")) >= 0

    def test_the_pip_install_path_restates_the_floor(self):
        """GIVEN install.sh adds the sandbox extra with pip, a resolver that never reads the uv
        override THEN the script puts wasmtime back at the floor itself and refuses to finish on
        a version below it. Measured 2026-11-01: this checkout's `.venv` had resolved 47.0.1 —
        the release the floor above refuses — while uv.lock resolves 50.0.1, because only uv
        honours `[tool.uv] override-dependencies`. The lock and the installer are two paths, and
        a floor that holds on one of them is a floor that ships an unpatched engine on the other.
        """
        text = (REPO / "install.sh").read_text(encoding="utf-8")
        override = _declared_requirements(ENGINE)[0]
        assert f'pip install "{override}"' in text, (
            f"install.sh does not restate the wasmtime bound {override} for the pip path"
        )
        assert 'm.version("wasmtime")' in text, "install.sh never reads the engine version back"


def test_the_cell_config_still_builds_on_the_patched_engine():
    """GIVEN the patched engine
    WHEN the cell builds its sandbox config
    THEN the configuration object exists with its caps, so the version bump did not break the
    seam the product calls."""
    pytest.importorskip("ephemora_cell", reason="the sandbox extra is not installed")

    from ephemora_cell import WASIConfig

    config = WASIConfig()
    assert config.max_fuel > 0
    assert config.max_memory_mb > 0


def test_fuel_is_enforced_by_the_patched_engine(tmp_path):
    """GIVEN the patched engine and the cell's own config builder
    WHEN a guest spins without consuming any other resource
    THEN execution traps on exhausted fuel. The flags on ``wasmtime.Config`` cannot be read back,
    so enforcement is the only honest check: a config the engine ignores would run forever
    instead of trapping."""
    pytest.importorskip("wasmtime", reason="the sandbox extra is not installed")

    script = tmp_path / "fuel_probe.py"
    script.write_text(
        "import wasmtime\n"
        "from ephemora_cell._engine_config import build_engine_config\n"
        "engine = wasmtime.Engine(build_engine_config(max_fuel=10_000, memory64=False))\n"
        "module = wasmtime.Module(engine, '(module (func (export \\\"spin\\\") (loop br 0)))')\n"
        "store = wasmtime.Store(engine)\n"
        "store.set_fuel(10_000)\n"
        "inst = wasmtime.Instance(store, module, [])\n"
        "try:\n"
        "    inst.exports(store)['spin'](store)\n"
        "    print('NO-TRAP')\n"
        "except wasmtime.Trap:\n"
        "    print('TRAPPED')\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, timeout=45
    )
    assert "TRAPPED" in result.stdout, (result.stdout, result.stderr[-400:])
