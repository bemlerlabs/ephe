"""The lockfile check against planted manifest/lock pairs, and its diff math as pure functions.

`scripts/lockfile_check.py` reads `app/package.json` and `app/pnpm-lock.yaml`, so every planted case
here runs against a directory in `tmp_path` with `--app`; the repository's own lock is only ever read,
never rewritten. The `--diff` half is tested two ways: the movement arithmetic as functions, and one
`HEAD..HEAD` smoke run, because a test that needed two committed revisions would have to commit.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "lockfile_check.py"

_spec = importlib.util.spec_from_file_location("lockfile_check", SCRIPT)
assert _spec is not None and _spec.loader is not None
lockfile_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lockfile_check)

LOCK_HEADER = "lockfileVersion: '9.0'\nimporters:\n  .:\n"


@pytest.mark.parametrize(("source", "pattern"), [
    (".github/workflows/tests.yml", r"uv==([0-9.]+)"),
    (".github/workflows/verify.yml", r"uv==([0-9.]+)"),
    (".github/workflows/supply-chain.yml", r"uv==([0-9.]+)"),
    (".github/workflows/lockfile.yml", r'EPHE_UV_VERSION: "([0-9.]+)"'),
    ("scripts/clean_room_install.sh", r"EPHE_UV_VERSION:-([0-9.]+)"),
    ("scripts/lockfile_check.py", r'EXPECTED_UV_VERSION = "([0-9.]+)"'),
])
def test_uv_version_contracts_use_the_approved_pin(source, pattern):
    body = "\n".join(line for line in (ROOT / source).read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("#"))
    pins = re.findall(pattern, body)
    assert pins and set(pins) == {"0.13.6"}, f"{source}: uv pins {pins}"


def write_pair(tmp_path: Path, manifest: dict, lock_body: str) -> Path:
    app = tmp_path / "app"
    app.mkdir(parents=True, exist_ok=True)
    (app / "package.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (app / "pnpm-lock.yaml").write_text(LOCK_HEADER + lock_body, encoding="utf-8")
    return app


def _local_uv_version() -> str:
    """The uv on this machine, read the same way the check reads it, or "" when none.

    A hosted runner carries no uv. The check's verdict there is the documented skip,
    so this helper reads it the same way and returns "" instead of raising where the
    check does not.
    """
    try:
        done = subprocess.run(["uv", "--version"], text=True, capture_output=True, check=False)
    except OSError:
        return ""
    if done.returncode != 0:
        return ""
    found = re.search(r"\d+\.\d+\.\d+", done.stdout)
    return found.group(0) if found else ""


def _fake_pnpm(tmp_path: Path, version: str) -> Path:
    """An executable `pnpm` that answers `version`, on a PATH of our own.

    A case about the pin must not read whatever pnpm the runner happens to carry: a
    hosted leg carries none, and a different one would make the verdict a property of
    the machine. The shim makes the pin the only input.
    """
    bin_dir = tmp_path / "fake-bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    shim = bin_dir / "pnpm"
    shim.write_text(f"#!/bin/sh\necho '{version}'\n", encoding="utf-8")
    shim.chmod(0o755)
    return bin_dir


def run(
    app: Path | None = None, *flags: str, path: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """The check as a subprocess. `path` replaces PATH, so a case can decide which
    (if any) pnpm the check resolves instead of reading the runner's own."""
    argv = [sys.executable, str(SCRIPT), "--skip-uv", *flags]
    if app is not None:
        argv += ["--app", str(app)]
    env = None
    if path is not None:
        env = dict(os.environ)
        env["PATH"] = str(path)
    return subprocess.run(argv, text=True, capture_output=True, check=False, cwd=ROOT, env=env)


class TestRealTreeAgrees:
    def test_the_committed_manifest_and_lock_match(self):
        done = run(ROOT / "app")
        assert done.returncode == 0, done.stdout + done.stderr
        # The contract is "every declared entry was compared and none disagreed". The count
        # belongs to the manifest, so pinning it made this test fail every time a dependency
        # landed. A floor keeps the assertion from passing on an empty comparison.
        assert "0 disagreement(s)" in done.stdout, done.stdout
        compared = re.search(r"(\d+) declared entries compared", done.stdout)
        assert compared and int(compared.group(1)) >= 50, done.stdout

    def test_the_pinned_pnpm_is_the_pnpm_this_checkout_resolves(self):
        """`packageManager` says pnpm@11.10.0 and `pnpm --version` answers it on this machine.

        A leg that never installed pnpm — the coverage leg pins node but not pnpm —
        resolves nothing, and the documented verdict for that is a loud skip rather
        than a crash (`--require-pnpm` is what makes it a refusal; planted below). The
        version is therefore only asserted where a pnpm actually answers.
        """
        manifest = json.loads((ROOT / "app" / "package.json").read_text(encoding="utf-8"))
        assert manifest["packageManager"].startswith("pnpm@")
        pinned = manifest["packageManager"].split("@")[1]
        actual = lockfile_check.resolved_pnpm_version()
        if actual is None:
            pytest.skip("no pnpm on this PATH: the check's documented verdict is a skip")
        assert actual == pinned, (
            f"pnpm on this PATH is {actual!r}, packageManager pins {pinned!r}"
        )


def test_pnpm_version_is_read_from_the_application_directory(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shim = bin_dir / "pnpm"
    shim.write_text(
        '#!/bin/sh\nif [ "$PWD" = "$EXPECTED_APP" ]; then\n'
        '  printf "11.11.0\\n"\nelse\n  printf "11.10.0\\n"\nfi\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("EXPECTED_APP", str(tmp_path.resolve()))
    assert lockfile_check.resolved_pnpm_version(tmp_path) == "11.11.0"


def test_cli_probes_pnpm_in_the_app_given_by_the_caller(tmp_path, monkeypatch):
    app = write_pair(tmp_path, {"name": "x", "packageManager": "pnpm@11.11.0"}, "    dependencies: {}\n")
    bin_dir = _fake_pnpm(tmp_path, "11.10.0")
    (bin_dir / "pnpm").write_text(
        '#!/bin/sh\nif [ "$PWD" = "$EXPECTED_APP" ]; then\n'
        '  printf "11.11.0\\n"\nelse\n  printf "11.10.0\\n"\nfi\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("EXPECTED_APP", str(app.resolve()))
    done = run(app, "--require-pnpm", path=bin_dir)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "`pnpm --version` says 11.11.0" in done.stdout


class TestPlantedDisagreements:
    def test_a_specifier_the_lock_never_recorded_names_the_dependency(self, tmp_path):
        app = write_pair(
            tmp_path,
            {"name": "x", "dependencies": {"left-pad": "^1.3.0"}, "packageManager": "pnpm@11.10.0"},
            "    dependencies:\n      left-pad:\n        specifier: 1.3.0\n        version: 1.3.0\n",
        )
        done = run(app)
        assert done.returncode == 1, done.stdout
        assert "the lock recorded specifier '1.3.0', the manifest says '^1.3.0'" in done.stdout

    def test_an_absent_importer_entry_is_a_different_failure_than_a_drift(self, tmp_path):
        app = write_pair(
            tmp_path,
            {"name": "x", "dependencies": {"left-pad": "^1.3.0"}, "packageManager": "pnpm@11.10.0"},
            "    devDependencies: {}\n",
        )
        done = run(app)
        assert done.returncode == 1, done.stdout
        assert "absent from the lock" in done.stdout, done.stdout

    def test_a_lock_entry_with_nothing_declaring_it_is_refused(self, tmp_path):
        app = write_pair(
            tmp_path,
            {"name": "x", "dependencies": {}, "packageManager": "pnpm@11.10.0"},
            "    dependencies:\n      ghost:\n        specifier: ^1.0.0\n        version: 1.0.0\n",
        )
        done = run(app)
        assert done.returncode == 1, done.stdout
        assert "with nothing declaring it" in done.stdout, done.stdout

    def test_a_package_manager_that_is_not_exact_is_refused(self, tmp_path):
        app = write_pair(
            tmp_path,
            {"name": "x", "dependencies": {}, "packageManager": "pnpm@11"},
            "    dependencies: {}\n",
        )
        done = run(app)
        assert done.returncode == 1, done.stdout
        assert "not an exact pnpm@major.minor.patch pin" in done.stdout, done.stdout

    def test_a_pnpm_that_is_not_the_pin_is_a_failure(self, tmp_path):
        app = write_pair(
            tmp_path,
            {"name": "x", "dependencies": {}, "packageManager": "pnpm@9.15.0"},
            "    dependencies: {}\n",
        )
        # The runner's own pnpm is not the subject: a hosted leg carries none, and a
        # different one would make the verdict a property of the machine. Supply one
        # that answers a version other than the manifest pin.
        done = run(app, "--require-pnpm", path=_fake_pnpm(tmp_path, "11.10.0"))
        assert done.returncode == 1, done.stdout
        assert "ran where packageManager pins 9.15.0" in done.stdout, done.stdout

    def test_a_lockfile_version_the_pinned_pnpm_does_not_write_is_refused(self, tmp_path):
        app = write_pair(
            tmp_path,
            {"name": "x", "dependencies": {}, "packageManager": "pnpm@11.10.0"},
            "    dependencies: {}\n",
        )
        (app / "pnpm-lock.yaml").write_text(
            "lockfileVersion: '6.0'\nimporters:\n  .:\n    dependencies: {}\n", encoding="utf-8")
        done = run(app)
        assert done.returncode == 1, done.stdout
        assert "is not the '9.0'" in done.stdout, done.stdout


class TestRefusals:
    def test_a_missing_lockfile_refuses_with_exit_two(self, tmp_path):
        app = tmp_path / "app"
        app.mkdir()
        (app / "package.json").write_text('{"name":"x"}\n', encoding="utf-8")
        done = run(app)
        assert done.returncode == 2, done.stdout + done.stderr
        assert "lockfile: FAIL" in done.stdout, done.stdout

    def test_a_layout_the_lock_is_not_for_is_named(self, tmp_path):
        app = write_pair(
            tmp_path,
            {"name": "x", "dependencies": {}, "packageManager": "pnpm@11.10.0"},
            "    dependencies: {}\n",
        )
        (app / "pnpm-lock.yaml").write_text(
            "lockfileVersion: '9.0'\nimporters:\n  packages/a:\n    dependencies: {}\n",
            encoding="utf-8",
        )
        done = run(app)
        assert done.returncode == 2, done.stdout + done.stderr
        assert "no `importers: .` entry" in done.stdout, done.stdout

    def test_a_runner_without_pnpm_is_a_skip_and_a_required_refusal(self, tmp_path):
        """The documented verdict when pnpm does not resolve on this PATH.

        A hosted leg installs node but not pnpm. The check must read that as its
        documented skip — not as a version, not as a clean pass, and not as a crash —
        and `--require-pnpm` is what turns it into the refusal the leg installed pnpm
        for. The PATH carries no pnpm on purpose.
        """
        app = write_pair(
            tmp_path,
            {"name": "x", "dependencies": {}, "packageManager": "pnpm@11.10.0"},
            "    dependencies: {}\n",
        )
        absent = tmp_path / "no-pnpm"
        absent.mkdir()

        skipped = run(app, path=absent)
        assert skipped.returncode == 0, skipped.stdout + skipped.stderr
        assert "pnpm did not resolve" in skipped.stdout, skipped.stdout

        refused = run(app, "--require-pnpm", path=absent)
        assert refused.returncode == 1, refused.stdout
        assert "pnpm did not resolve" in refused.stdout, refused.stdout

    def test_uv_is_only_ever_checked_under_its_own_pin(self, tmp_path):
        """A uv that is not the pin may never stand in as a green for the resolver that wrote
        uv.lock: its verdict is a loud skip, and the leg that installed uv may not skip. On the
        pin itself the check runs, and `require` changes nothing about the verdict it returns."""
        local = _local_uv_version()
        note = lockfile_check.check_uv_lock(require=False)
        required = lockfile_check.check_uv_lock(require=True)
        if local == lockfile_check.EXPECTED_UV_VERSION:
            assert note[1].startswith(("agrees", "refused")), note
            assert required[0] == note[0], "require must not change the pinned resolver's verdict"
        else:
            assert note[0] == [] and "skipped" in note[1], note
            assert required[0], "the leg that installed uv must not be able to skip the check"


class TestDiffMath:
    def test_movements_are_split_into_updated_added_and_removed(self, capsys):
        before = {"a": "1.0.0", "b": "2.0.0", "c": "3.1.0(peer@1.0.0)"}
        after = {"a": "1.2.0", "b": "2.0.0", "d": "0.1.0"}
        total, majors = lockfile_check.describe_diff("probe", before, after)
        printed = capsys.readouterr().out
        assert total == 3 and majors == []
        assert "1 updated, 1 added, 1 removed" in printed, printed
        assert "a: 1.0.0 -> 1.2.0" in printed, printed
        assert "d: added at 0.1.0" in printed, printed
        assert "c: removed (was 3.1.0)" in printed, printed
        assert "b: " not in printed, printed

    def test_a_major_move_is_called_out_separately(self, capsys):
        total, majors = lockfile_check.describe_diff(
            "probe", {"react": "18.3.1"}, {"react": "19.0.0"}
        )
        printed = capsys.readouterr().out
        assert total == 1 and majors == ["react: 18.3.1 -> 19.0.0"]
        assert "MAJOR react: 18.3.1 -> 19.0.0" in printed
        assert "1 of them a major version" in printed

    def test_a_same_version_entry_with_new_peers_says_so(self, capsys):
        lockfile_check.describe_diff(
            "probe", {"z": "5.0.15(peer@1.6.0)"}, {"z": "5.0.15(peer@1.7.0)"}
        )
        assert "(peer set moved)" in capsys.readouterr().out

    def test_head_against_itself_moves_nothing(self):
        done = subprocess.run(
            [sys.executable, str(SCRIPT), "--diff", "HEAD..HEAD"],
            text=True, capture_output=True, check=False, cwd=ROOT,
        )
        assert done.returncode == 0, done.stdout + done.stderr
        assert "0 movement(s)" in done.stdout, done.stdout


class TestCargoAgreement:
    """The Tauri manifest pair, planted. Both files are read as text, so a case needs no Rust
    toolchain, no registry and no network — which is the reason the check is written that way.
    """

    def _point(self, monkeypatch, tmp_path, manifest: str, lock: str) -> None:
        manifest_path = tmp_path / "Cargo.toml"
        lock_path = tmp_path / "Cargo.lock"
        manifest_path.write_text(manifest, encoding="utf-8")
        lock_path.write_text(lock, encoding="utf-8")
        monkeypatch.setattr(lockfile_check, "CARGO_MANIFEST", manifest_path)
        monkeypatch.setattr(lockfile_check, "CARGO_LOCK", lock_path)

    def test_a_declared_crate_missing_from_the_lock_is_named(self, monkeypatch, tmp_path):
        self._point(monkeypatch, tmp_path,
                    '[dependencies]\nserde = { version = "1.0", features = ["derive"] }\n',
                    'version = 3\n\n[[package]]\nname = "serde_json"\nversion = "1.0.1"\n')
        problems, _ = lockfile_check.check_cargo_lock(require=True)
        assert any("serde:" in problem and "absent from Cargo.lock" in problem
                   for problem in problems), problems

    def test_a_lock_below_the_declared_minimum_is_named(self, monkeypatch, tmp_path):
        self._point(monkeypatch, tmp_path, '[dependencies]\ntauri = "2.11.3"\n',
                    'version = 3\n\n[[package]]\nname = "tauri"\nversion = "2.10.0"\n')
        problems, _ = lockfile_check.check_cargo_lock(require=True)
        assert problems and "2.10.0" in problems[0], problems

    def test_a_caret_above_the_minimum_passes(self, monkeypatch, tmp_path):
        self._point(monkeypatch, tmp_path, '[dependencies]\ntauri = "2.11.3"\n',
                    'version = 3\n\n[[package]]\nname = "tauri"\nversion = "2.12.3"\n')
        problems, summary = lockfile_check.check_cargo_lock(require=True)
        assert problems == [], problems
        assert "1 declared crate(s)" in summary, summary

    def test_a_build_dependency_table_is_read_too(self, monkeypatch, tmp_path):
        self._point(monkeypatch, tmp_path,
                    '[build-dependencies]\ntauri-build = { version = "2.6.3", features = [] }\n',
                    'version = 3\n\n[[package]]\nname = "tauri-build"\nversion = "2.6.3"\n')
        problems, summary = lockfile_check.check_cargo_lock(require=True)
        assert problems == [], problems
        assert "1 declared crate(s)" in summary, summary

    def test_a_requirement_this_check_cannot_read_is_not_a_verdict(self):
        """A comma range and a wildcard are not judged. A comparison the instrument cannot
        compute must not become a red step, or the ratchet gets switched off for being wrong.
        """
        assert lockfile_check._satisfies("1.0.0", ">=1.0, <2.0")
        assert lockfile_check._satisfies("1.0.0", "*")
        assert lockfile_check._satisfies("1.0.0", "<2.0")
        assert not lockfile_check._satisfies("1.0.0", "2.0")
        assert lockfile_check._satisfies("2.12.3", "2.11.3")

    def test_the_real_tauri_pair_agrees(self):
        problems, summary = lockfile_check.check_cargo_lock(require=True)
        assert problems == [], problems
        declared = re.search(r"(\d+) declared crate", summary)
        assert declared and int(declared.group(1)) >= 8, summary



class TestCargoSourceAudit:
    """The `source` line of every locked Cargo package, planted case by case. Added
    2026-11-24 after the vendored glib decision: the manifest-to-lock comparison reads
    name and version only, so a registry crate swapped for a git repository of the same
    version passed it, and the path pin of the vendored copy is a source change the audit
    must see and name. Both directions prove: the real pair passes, planted swaps refuse.
    """

    MANIFEST = ('[package]\nname = "app"\nversion = "0.1.0"\nedition = "2021"\n\n'
                '[dependencies]\nserde = "1.0"\n')

    def _point(self, monkeypatch, tmp_path, manifest: str, lock: str,
               vendor: str | None = None) -> None:
        manifest_path = tmp_path / "Cargo.toml"
        lock_path = tmp_path / "Cargo.lock"
        manifest_path.write_text(manifest, encoding="utf-8")
        lock_path.write_text(lock, encoding="utf-8")
        if vendor:
            (tmp_path / vendor).mkdir(parents=True, exist_ok=True)
            (tmp_path / vendor / "Cargo.toml").write_text(
                '[package]\nname = "glib"\nversion = "0.18.5"\n', encoding="utf-8")
        monkeypatch.setattr(lockfile_check, "CARGO_MANIFEST", manifest_path)
        monkeypatch.setattr(lockfile_check, "CARGO_LOCK", lock_path)

    def _lock(self, serde_source: str = 'source = "registry+https://github.com/rust-lang/crates.io-index"\n',
              glib_block: str = "") -> str:
        return ("version = 3\n\n[[package]]\nname = \"app\"\nversion = \"0.1.0\"\n\n"
                "[[package]]\nname = \"serde\"\nversion = \"1.0.200\"\n" + serde_source +
                "\n" + glib_block)

    def test_the_real_pair_passes_with_glib_named(self):
        problems, summary = lockfile_check.check_cargo_sources(require=True)
        assert problems == [], problems
        assert "0 git source(s)" in summary, summary
        assert "1 path-sourced patch(es) against 1 named" in summary, summary

    def test_a_git_sourced_registry_crate_is_a_finding(self, monkeypatch, tmp_path):
        """The force case: same name, same version, different source. The comparison above
        never reads `source`, so this is the swap that used to sail through — planted and
        refused here."""
        lock = self._lock(serde_source='source = "git+https://attacker.example/serde.git'
                                       '?rev=beefcafe#beefcafe"\n')
        self._point(monkeypatch, tmp_path, self.MANIFEST, lock)
        problems, _ = lockfile_check.check_cargo_sources(require=True)
        assert any(problem.startswith("serde v1.0.200 resolves from git source")
                   for problem in problems), problems

    def test_an_unnamed_path_source_is_a_finding(self, monkeypatch, tmp_path):
        """A vendored crate outside the named allowlist ships without the registry audit
        trail; naming it here is what separates the vendored glib decision from silence."""
        lock = self._lock() + ('[[package]]\nname = "hidden"\nversion = "1.2.3"\n\n'
                               '[[package]]\nname = "glib"\nversion = "0.18.5"\n')
        self._point(monkeypatch, tmp_path, self.MANIFEST +
                    '[patch.crates-io]\nglib = { path = "vendor/glib-0.18.5" }\n',
                    lock, vendor="vendor/glib-0.18.5")
        problems, _ = lockfile_check.check_cargo_sources(require=True)
        assert any(problem.startswith("hidden v1.2.3 is path-sourced")
                   for problem in problems), problems
        assert not any(problem.startswith("glib ") for problem in problems), problems

    def test_the_named_glib_patch_alone_passes(self, monkeypatch, tmp_path):
        lock = self._lock(glib_block='[[package]]\nname = "glib"\nversion = "0.18.5"\n\n')
        self._point(monkeypatch, tmp_path,
                    self.MANIFEST + '[patch.crates-io]\nglib = { path = "vendor/glib-0.18.5" }\n',
                    lock, vendor="vendor/glib-0.18.5")
        problems, summary = lockfile_check.check_cargo_sources(require=True)
        assert problems == [], problems
        assert "1 path-sourced patch(es) against 1 named" in summary, summary

    def test_a_second_patch_without_a_register_constant_is_a_finding(self, monkeypatch, tmp_path):
        """A patch cannot arrive alone: it has to move the allowlist, which is where the
        written decision lives."""
        lock = self._lock(glib_block='[[package]]\nname = "glib"\nversion = "0.18.5"\n\n'
                                     '[[package]]\nname = "serde"\nversion = "1.0.200"\n')
        self._point(monkeypatch, tmp_path,
                    self.MANIFEST + '[patch.crates-io]\nglib = { path = "vendor/glib-0.18.5" }\n'
                    'serde = { path = "vendor/serde" }\n', lock, vendor="vendor/glib-0.18.5")
        problems, _ = lockfile_check.check_cargo_sources(require=True)
        assert any("[patch.crates-io] serde is not a named patch" in problem
                   for problem in problems), problems

    def test_a_declared_patch_absent_from_the_lock_is_a_finding(self, monkeypatch, tmp_path):
        """A stale pair must not audit yesterday's decision: the declared patch must be the
        lock's own path entry, and a glib still named by the registry says the patch is off."""
        lock = self._lock(glib_block='[[package]]\nname = "glib"\nversion = "0.18.5"\n'
                                     'source = "registry+https://github.com/rust-lang/crates.io-index"\n'
                                     'checksum = "233daaf6e83ae6a12a52055f568f9d7cf4671dabb78ff9560ab6da230ce00ee5"\n')
        self._point(monkeypatch, tmp_path,
                    self.MANIFEST + '[patch.crates-io]\nglib = { path = "vendor/glib-0.18.5" }\n',
                    lock, vendor="vendor/glib-0.18.5")
        problems, _ = lockfile_check.check_cargo_sources(require=True)
        assert any("[patch.crates-io] glib is declared but the lock carries no path-sourced glib"
                   in problem for problem in problems), problems

    def test_a_patch_pinning_an_absent_vendor_tree_is_a_finding(self, monkeypatch, tmp_path):
        lock = self._lock(glib_block='[[package]]\nname = "glib"\nversion = "0.18.5"\n\n')
        self._point(monkeypatch, tmp_path,
                    self.MANIFEST + '[patch.crates-io]\nglib = { path = "vendor/glib-0.18.5" }\n',
                    lock, vendor=None)
        problems, _ = lockfile_check.check_cargo_sources(require=True)
        assert any("holds no Cargo.toml" in problem for problem in problems), problems

    def test_a_git_patch_is_refused_even_for_a_named_crate(self, monkeypatch, tmp_path):
        lock = self._lock(glib_block='[[package]]\nname = "glib"\nversion = "0.18.5"\n'
                                     'source = "git+https://someone.example/glib.git'
                                     '?rev=deadbeef#deadbeef"\n')
        self._point(monkeypatch, tmp_path,
                    self.MANIFEST + '[patch.crates-io]\nglib = '
                    '{ git = "https://someone.example/glib.git", rev = "deadbeef" }\n',
                    lock)
        problems, _ = lockfile_check.check_cargo_sources(require=True)
        assert any("[patch.crates-io] glib points at git" in problem
                   for problem in problems), problems
        assert any("resolves from git source" in problem for problem in problems), problems

    def test_a_lock_with_no_packages_refuses_the_audit(self, monkeypatch, tmp_path):
        with pytest.raises(lockfile_check.CheckError):
            self._point(monkeypatch, tmp_path, self.MANIFEST, "version = 3\n")
            lockfile_check.check_cargo_sources(require=True)
