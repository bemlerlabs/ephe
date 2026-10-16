"""The cell pin: `ephe[sandbox]` holds the release whose policy this codebase measured.

Owner decision 2026-10-09: Ephemora Cell is our own product, so its BUSL-1.1 rungs
bind nothing here and a licence never justified the bound. What the bound does hold is
the release whose enforcement was read off the artifact. `core/cpython_cell.py` writes
the WASIConfig caps, and `core/cell_policy.policy_snapshot()` reports those same
numbers (max_fuel, max_memory_mb, timeout_seconds, network=none) to the settings card,
`ephe doctor` and the status page, so the two have to describe one runtime. A fresh
`pip install 'ephe[sandbox]'` past the pin quotes caps nobody re-measured, and `ephe
doctor` used to recommend exactly that step as its repair command. Each release keeps
its licence and wheel hash in `.github/cell-runtime-fence.json`, read from the wheel and
cross-checked against the installed dist-info.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import importlib.metadata
import importlib.util
import io
import json
import re
from pathlib import Path
from tests.toml_compat import tomllib
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / ".github" / "cell-runtime-fence.json"
LOCK = ROOT / "uv.lock"
PYPROJECT = ROOT / "pyproject.toml"

#: The rung this codebase measured, and the next published rung above it.
MEASURED_RUNG = "1.0.4.3"
NEXT_RUNG = "1.0.5"


def _version_tuple(value: str) -> tuple[int, ...]:
    from ephe_cli import _version_tuple as impl

    return impl(value)


def _sandbox_pin_bounds() -> tuple[str, str]:
    """(lower, upper) from the sandbox extra, in the form `>=A,<B`."""
    raw = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    specs = [s for s in raw["project"]["optional-dependencies"]["sandbox"] if "ephemora-cell" in s]
    assert len(specs) == 1, f"expected exactly one ephemora-cell line: {specs}"
    match = re.fullmatch(r"ephemora-cell\s*>=\s*([^,<]+)\s*,\s*<\s*([^,<]+)", specs[0].strip())
    assert match, f"unexpected pin form: {specs[0]!r}"
    return match.group(1).strip(), match.group(2).strip()


def test_the_upper_bound_excludes_the_unmeasured_rung():
    lower, upper = _sandbox_pin_bounds()
    assert lower == MEASURED_RUNG
    assert _version_tuple(MEASURED_RUNG) < _version_tuple(upper), "the measured rung must stay inside"
    assert not _version_tuple(NEXT_RUNG) < _version_tuple(upper), (
        f"{NEXT_RUNG}, measured by nobody, falls through the bound"
    )


def test_uv_lock_carries_the_same_bound_as_pyproject():
    """A lockfile that loses the fence is the same defect, only quieter."""
    lower, upper = _sandbox_pin_bounds()
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")
    lines = [ln for ln in lock.splitlines() if 'name = "ephemora-cell"' in ln and "specifier" in ln]
    assert len(lines) == 1, f"expected exactly one specifier entry: {lines}"
    assert f'specifier = ">={lower},<{upper}"' in lines[0], f"lockfile drifts against pyproject:\n{lines[0]}"


def test_the_documentation_quotes_the_pin_word_for_word():
    """The documentation quotes the pin and names the reason the pin exists."""
    doc = (ROOT / "docs" / "SANDBOX_EXECUTION.md").read_text(encoding="utf-8")
    assert f">={MEASURED_RUNG},<{NEXT_RUNG}" in doc, "documentation shows another pin than pyproject"
    assert re.search(r"policy[_ ]snapshot", doc), (
        "the sandbox documentation no longer states what the pin holds: the release whose "
        "policy snapshot this codebase measured"
    )
    assert "BUSL-1.1" in doc, "the licence is still a fact the documentation owes the reader"


@pytest.mark.skipif(
    importlib.util.find_spec("ephemora_cell") is None,
    reason="ephemora-cell not installed (opt-in extra)",
)
def test_the_installed_cell_sits_inside_the_bound():
    lower, upper = _sandbox_pin_bounds()
    installed = importlib.metadata.version("ephemora-cell")
    assert _version_tuple(lower) <= _version_tuple(installed) < _version_tuple(upper), (
        f"installed {installed} lies outside the measured range {lower}..{upper}"
    )


class _Resp(contextlib.AbstractContextManager):
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self) -> bytes:
        import json

        return json.dumps(self._payload).encode()


def _run_doctor(payload: dict) -> tuple[int, str]:
    """The full doctor run with a faked PyPI answer — the watch line is the
    contract, so this is taken from real code runtime here."""
    import ephe_cli

    args = ephe_cli.build_parser().parse_args(["doctor", "--model", "gemma4:12b"])
    with (
        patch("ephe_cli._ollama_binary", return_value="/usr/local/bin/ollama"),
        patch("ephe_cli._model_installed", return_value=True),
        patch("ephe_cli._json_get") as json_get,
        patch("ephe_cli._model_loadable", return_value=(True, "test generation ok")),
        patch("ephe_cli._doctor_image_endpoint", return_value=(True, "ok")),
        patch("ephe_cli._doctor_voice", return_value=(True, "ok")),
        patch("ephe_cli._cell_pinned_ceiling", return_value=NEXT_RUNG),
        patch("ephe_cli._active_engine_choice", return_value=None),
        patch(
            "importlib.metadata.version",
            side_effect=lambda name: MEASURED_RUNG if name == "ephemora-cell" else "0.0.0",
        ),
        patch("urllib.request.urlopen", return_value=_Resp(payload)),
    ):
        json_get.side_effect = [{"models": [{"name": "gemma4:12b"}]}, {"status": "ok"}]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = args.func(args)
    cell_lines = [ln for ln in out.getvalue().splitlines() if "ephemora-cell" in ln]
    assert len(cell_lines) == 1, out.getvalue()
    return code, cell_lines[0]


def test_doctor_names_an_unmeasured_rung_as_a_decision():
    """A release above the measured rung is a re-measurement decision: the watch says so
    and withholds the repair command, because the bound is the intent."""
    code, line = _run_doctor({"info": {"version": NEXT_RUNG, "license": "BUSL-1.1"}})
    assert "re-measure" in line, line
    assert "uv pip install" not in line, "the watch must not lead past the bound"
    assert code == 0, "a deliberate bound is not a failure"


def test_doctor_keeps_the_repair_command_for_a_real_update():
    """Same line, other case: a release inside the fence still gets
    the repair command — the fence must not mute the watch."""
    code, line = _run_doctor({"info": {"version": "1.0.4.4", "license": "Apache-2.0"}})
    assert "uv pip install" in line
    assert code == 0


def test_version_tuple_carries_build_suffixes():
    assert _version_tuple("1.0.4.3") == (1, 0, 4)
    assert _version_tuple("1.0.5rc1") == (1, 0, 5)
    assert _version_tuple("") == (0, 0, 0)
    assert _version_tuple("2") == (2, 0, 0)
    assert _version_tuple("1.0") == _version_tuple("1.0.0"), "a shorter version must not read smaller"


def test_doctor_reads_the_ceiling_from_our_own_metadata():
    """The watch quotes the pin that shipped, so the ceiling read from installed package
    metadata has to equal the bound in pyproject.toml.
    """
    import ephe_cli

    lower, upper = _sandbox_pin_bounds()
    observed = ephe_cli._cell_pinned_ceiling()
    assert observed == upper, (
        f"ephe_cli reads a ceiling of {observed!r} while pyproject.toml declares <{upper}: the "
        "installed `ephe` metadata is stale, so the doctor is quoting the pin that shipped, not "
        "the one in the tree. Reinstall the package (`pip install -e .`) or the bound you just "
        "edited is not the bound anyone runs."
    )


# The cell-runtime register: the fence as a machine check rather than a constant.
# Everything above ties pyproject, uv.lock and the documentation to two version
# literals written in this file. That holds while the literals are true and stops
# holding the moment someone widens a bound: editing `<1.0.5` to `<1.1.1` and
# updating `NEXT_RUNG` in the same breath leaves the whole upper block green while a
# release nobody measured becomes what a fresh `ephe[sandbox]` install runs — and the
# settings card, `ephe doctor` and the status page would still quote the caps that
# were read off the old one. The tests below read `.github/cell-runtime-fence.json`
# instead: one entry per PUBLISHED VERSION, its licence and wheel sha256 taken from
# that artifact, and whether this codebase measured its policy. Licences are recorded
# and drift-checked against the artifact — Ephemora Cell is our own product.

POLICY_KEYS = ("max_fuel", "max_memory_mb", "timeout_seconds", "network")


def _register() -> dict[str, dict]:
    assert REGISTER.is_file(), (
        f"missing fence register {REGISTER}: the pin has no evidence source, restore it "
        "or replace it with a register that names every pinned runtime"
    )
    packages = json.loads(REGISTER.read_text(encoding="utf-8")).get("packages")
    assert packages, f"{REGISTER} declares no package — an empty fence fences nothing"
    return packages


def _requirement_bounds(name: str) -> list[tuple[str, str, str]]:
    """(where, lower, upper) for every `>=A,<B` bound pyproject.toml puts on `name`,
    across extras and dependency groups: the fence only holds if it reads the surface
    that installs it."""
    raw = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    surfaces = {f"optional-dependencies.{k}": v
                for k, v in (raw["project"].get("optional-dependencies") or {}).items()}
    surfaces.update({f"dependency-groups.{k}": v
                     for k, v in (raw.get("dependency-groups") or {}).items()})
    found: list[tuple[str, str, str]] = []
    for where, reqs in surfaces.items():
        for req in reqs:
            if not isinstance(req, str) or name not in req:
                continue
            spec = rf"{re.escape(name)}\s*(?:\[[^\]]*\])?\s*>=\s*([^,<]+?)\s*,\s*<\s*([^,<]+?)$"
            m = re.fullmatch(spec, req.strip())
            assert m, (
                f"{where} pins {name!r} in a form the fence cannot read; the register can only "
                "guard an explicit `>=lower,<upper` bound — widen this test deliberately instead "
                "of loosening the pin"
            )
            found.append((where, m.group(1), m.group(2)))
    assert found, f"{name} is in the register but no requirement in pyproject.toml pins it"
    return found


def _lock_blocks(name: str, path: Path | None = None) -> list[tuple[str, str]]:
    """Every (version, wheel sha256) block the lockfile carries for `name`.

    A forked resolution writes one block per version — six names in this lock do,
    `numpy` with three — and each block is a rung a fresh install can land on, so the
    fence reads all of them. `_lock_resolution` keeps the first-wins answer because
    `scripts/uv_lock_sync.sh --verdict` reads it and collects the forks itself.
    """
    found: list[tuple[str, str]] = []
    for block in (path or LOCK).read_text(encoding="utf-8").split("[[package]]"):
        if not re.search(rf'^name = "{re.escape(name)}"\s*$', block, re.M):
            continue
        version = re.search(r'^version = "([^"]+)"', block, re.M)
        wheel = re.search(r"wheels\s*=\s*\[.*?sha256:([0-9a-f]{64})", block, re.S)
        assert version, f"uv.lock has a {name} block without a version"
        found.append((version.group(1), (wheel.group(1) if wheel else "")))
    return found


def _lock_resolution(name: str) -> tuple[str, str] | None:
    """(version, wheel sha256) the first lockfile block resolves for `name`, or None when
    it carries no such package."""
    blocks = _lock_blocks(name)
    return blocks[0] if blocks else None


def _release(pkg: dict, name: str, version: str, why: str) -> dict:
    """The register entry for one published version, evidence included. A version nobody
    read an artifact for stops the run."""
    entry = (pkg.get("releases") or {}).get(version)
    assert entry, (
        f"{name} {version} ({why}) has no entry in {REGISTER}. The register only holds what was "
        "read from that wheel, so an unknown version stops the run: download it "
        f"(`pip download --no-deps --no-build-isolation {name}=={version}`), read its "
        "`*.dist-info/METADATA` and `licenses/LICENSE`, measure the cell policy against it and "
        f"add the entry — or move the bound back under {version}."
    )
    assert entry.get("proven") == "artifact", (
        f"{REGISTER} describes {name} {version} on {entry.get('proven')} evidence only; a "
        'registry field is not an artifact, re-read the wheel and set proven="artifact"'
    )
    sha = entry.get("wheel_sha256") or ""
    assert re.fullmatch(r"[0-9a-f]{64}", sha), (
        f"{name} {version}: wheel_sha256 {sha!r} is not a sha256 — a licence or policy claim "
        "attached to no particular bytes is not evidence"
    )
    assert entry.get("license"), f"{name} {version}: no licence recorded"
    assert entry.get("policy_evidence"), (
        f"{name} {version}: no policy_evidence — the register says what was measured but not "
        "where it was read from"
    )
    return entry


def _measurable(pkg: dict, name: str, version: str) -> None:
    """Assert the release carries a live measurement. The licence is deliberately not
    asked about here: it is recorded and drift-checked, it fences nothing."""
    entry = _release(pkg, name, version, "admitted by the declared bound")
    measured = entry.get("policy_measured")
    assert measured, (
        f"{name} {version} is admitted by our bound but has never been measured: "
        "`core/cell_policy.policy_snapshot()` would report caps read off a different runtime. "
        "Run the measurement, fill policy_measured / policy_recheck / policy_snapshot in "
        f"{REGISTER}, or move the bound back under {version}."
    )
    recheck = dt.date.fromisoformat(entry["policy_recheck"])
    assert recheck >= dt.date.today(), (
        f"{name} {version}: the policy measurement was taken {measured} and expired on "
        f"{entry['policy_recheck']} — re-measure and move the date with a written note, or "
        "narrow the bound"
    )
    snap = entry.get("policy_snapshot") or {}
    missing = [k for k in POLICY_KEYS if k not in snap]
    assert not missing, (
        f"{name} {version}: policy_snapshot lacks {missing}; a snapshot without its four caps "
        "is a date, not a measurement"
    )


def test_every_release_the_declared_bound_admits_is_measured():
    """GIVEN a widened bound in pyproject.toml THEN every published release it now
    admits has to carry a live measurement in the register — no version literal in this
    file takes part in that verdict, so editing the literals cannot walk the fence open.
    """
    for name, pkg in _register().items():
        for where, lower, upper in _requirement_bounds(name):
            admitted = [v for v in (pkg.get("releases") or {})
                        if _version_tuple(lower) <= _version_tuple(v) < _version_tuple(upper)]
            assert admitted, f"{where} admits no release the register knows: {lower}..{upper}"
            for version in admitted:
                _measurable(pkg, name, version)


def test_the_lockfile_resolves_to_a_registered_and_measured_artifact():
    """GIVEN `uv lock --upgrade-package` moved the resolved version THEN the bytes the
    lock installs must be the bytes the register read, the release must be measured, and
    it must sit inside the declared bound. A forked resolution writes one block per
    version, and every block is a rung a fresh install can land on, so all of them are
    judged: reading only the first block fences one rung of a fork and never looks at the
    rest.
    """
    for name, pkg in _register().items():
        blocks = _lock_blocks(name)
        if not blocks:
            pytest.fail(
                f"{name} is fenced in {REGISTER} but uv.lock resolves no version for it — either "
                "the runtime left the dependency set (delete the register entry in writing) or "
                "the lock is broken"
            )
        bounds = _requirement_bounds(name)
        for version, wheel_sha in blocks:
            entry = _release(pkg, name, version, "resolved by uv.lock")
            _measurable(pkg, name, version)
            assert wheel_sha == entry["wheel_sha256"], (
                f"uv.lock installs {name} {version} from sha256:{wheel_sha or '<missing>'}, but "
                f"{REGISTER} read its licence and policy off sha256:{entry['wheel_sha256']}. If the "
                "lock is right, the register is stale and has to be re-read from that artifact."
            )
            for where, lower, upper in bounds:
                assert _version_tuple(lower) <= _version_tuple(version) < _version_tuple(upper), (
                    f"uv.lock resolves {name} {version} while {where} declares "
                    f">={lower},<{upper}: the lock installs a rung the bound refuses"
                )


def test_the_installed_artifact_agrees_with_the_register_offline():
    """GIVEN the cell is installed THEN its own dist-info METADATA is the witness: the
    register may not state a licence the installed artifact does not carry. Offline on
    purpose; it skips only when the optional extra is genuinely absent.
    """
    if importlib.util.find_spec("ephemora_cell") is None:
        pytest.skip("ephemora-cell not installed (opt-in extra)")
    for name, pkg in _register().items():
        installed = importlib.metadata.version(name)
        entry = _release(pkg, name, installed, "installed here")
        licence = importlib.metadata.metadata(name).get("License")
        assert licence, (
            f"installed {name} {installed} ships METADATA without a License field — the register "
            "may not keep asserting a licence the artifact stopped declaring"
        )
        assert licence == entry["license"], (
            f"register says {name} {installed} is {entry['license']}, the installed dist-info "
            f"says {licence}; one of them is wrong and the installed one is what users run"
        )


def test_the_registers_snapshot_equals_the_caps_this_code_writes():
    """GIVEN the measured rung THEN its four numbers must be the numbers
    `core/cpython_cell.py` writes into the WASIConfig — otherwise report != enforced,
    which is the exact defect the pin exists to prevent.
    """
    from core import cpython_cell

    want = {
        "max_memory_mb": cpython_cell.DEFAULT_MAX_MEMORY_MB,
        "timeout_seconds": cpython_cell.DEFAULT_TIMEOUT_SECONDS,
        "network": "none",
    }
    checked = 0
    for name, pkg in _register().items():
        for version, entry in (pkg.get("releases") or {}).items():
            if not entry.get("policy_measured"):
                continue
            snap = entry["policy_snapshot"]
            for key, expected in want.items():
                assert snap.get(key) == expected, (
                    f"{name} {version}: register says {key}={snap.get(key)!r}, "
                    f"core/cpython_cell.py writes {expected!r}"
                )
            assert isinstance(snap.get("max_fuel"), int) and snap["max_fuel"] > 0, (
                f"{name} {version}: max_fuel {snap.get('max_fuel')!r} is not a fuel budget"
            )
            checked += 1
    assert checked, "no measured release in the register — the cross-check tested nothing"


def test_every_registered_release_carries_artifact_evidence():
    """GIVEN the register holds one entry per published version THEN every entry is
    artifact evidence and its measurement state is explicit. The tests above read only the
    rungs the bound admits, the lock resolves and this machine installs; a release outside
    all three — where the licence cut sits — would otherwise be recorded with nobody asking
    what the record says. `policy_measured: null` states that a release was not measured, so
    a snapshot beside that null is a claim with no measurement behind it.
    """
    for name, pkg in _register().items():
        releases = pkg.get("releases") or {}
        assert releases, f"{name} is in {REGISTER} with no release entry"
        for version, entry in releases.items():
            _release(pkg, name, version, "recorded in the register")
            if entry.get("policy_measured"):
                _measurable(pkg, name, version)
                continue
            assert entry.get("policy_recheck") is None and entry.get("policy_snapshot") is None, (
                f"{name} {version} records no measurement date but carries "
                f"policy_recheck={entry.get('policy_recheck')!r} and "
                f"policy_snapshot={entry.get('policy_snapshot')!r}: caps with no date on them "
                "cannot be re-checked, so the register would state a measurement it cannot date"
            )


def test_the_licence_cut_is_recorded_where_the_documentation_states_it():
    """GIVEN `docs/SANDBOX_EXECUTION.md` states the licence cut — the measured rung under a
    permissive licence, the rungs above it under BUSL-1.1 THEN the register agrees, rung for
    rung. Nothing is fenced on a licence, but a licence the register records while the
    documentation states another is a disagreement about bytes read from the wheel, and the
    register is the one that was read.
    """
    pkg = _register().get("ephemora-cell")
    assert pkg, f"{REGISTER} no longer fences ephemora-cell"
    measured = _release(pkg, "ephemora-cell", MEASURED_RUNG, "the measured rung")
    assert measured["license"] == "Apache-2.0", (
        f"the measured rung {MEASURED_RUNG} is recorded as {measured['license']!r}; the "
        "documentation states Apache-2.0"
    )
    above = {v: e for v, e in (pkg.get("releases") or {}).items()
             if _version_tuple(v) >= _version_tuple(NEXT_RUNG)}
    assert above, f"no registered release at or above the {NEXT_RUNG} licence cut"
    for version, entry in above.items():
        assert entry["license"] == "BUSL-1.1", (
            f"{version} sits at or above the {NEXT_RUNG} licence cut the documentation records as "
            f"BUSL-1.1, but the register says {entry['license']!r}: one of the two is wrong about "
            "the wheel"
        )


def test_every_block_of_a_forked_lock_is_read(tmp_path):
    """GIVEN `uv lock --upgrade-package` forked a fenced package into one block per
    version WHEN the fence reads the lock THEN it sees every block, not the first one: a
    first-wins reader fences one rung of the fork and never looks at the rest.
    """
    forked = tmp_path / "uv.lock"
    forked.write_text(
        '[[package]]\nname = "ephemora-cell"\nversion = "1.0.4.3"\n'
        'wheels = [\n    { hash = "sha256:' + "a" * 64 + '" },\n]\n\n'
        '[[package]]\nname = "ephemora-cell"\nversion = "1.1.0"\n'
        'wheels = [\n    { hash = "sha256:' + "b" * 64 + '" },\n]\n',
        encoding="utf-8",
    )
    assert _lock_blocks("ephemora-cell", path=forked) == [
        ("1.0.4.3", "a" * 64),
        ("1.1.0", "b" * 64),
    ]
