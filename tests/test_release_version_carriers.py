"""One list of six carriers, and a bump that cannot land half of them.

`pyproject.toml` declares the version; `app/package.json`, `tauri.conf.json` and the Cargo
manifest repeat it, and `uv.lock` plus `Cargo.lock` record it for the two package managers.
The cut used to compare three files, the checklist three, and a Cargo lock drift passed both
and failed only in the tag CI after the tag was public. These tests hold the shared list to
the six files, `set_versions` to every spelling each file needs, and the bump to a whole
write.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARRIERS = ROOT / "scripts" / "version_carriers.py"


def _load():
    spec = importlib.util.spec_from_file_location("version_carriers_under_test", CARRIERS)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


carriers = _load()


def plant(root: Path, version: str = "1.2.3") -> Path:
    (root / "app" / "src-tauri").mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "ephe"\nversion = "{version}"\n', encoding="utf-8"
    )
    (root / "app" / "package.json").write_text(
        json.dumps({"name": "ephe-frontend", "version": version, "private": True}) + "\n",
        encoding="utf-8",
    )
    (root / "app" / "src-tauri" / "tauri.conf.json").write_text(
        json.dumps({"productName": "Ephe", "version": version}) + "\n", encoding="utf-8"
    )
    (root / "app" / "src-tauri" / "Cargo.toml").write_text(
        f'[package]\nname = "app"\nversion = "{version}"\n', encoding="utf-8"
    )
    (root / "app" / "src-tauri" / "Cargo.lock").write_text(
        "[[package]]\n"
        f'name = "app"\nversion = "{version}"\n'
        "\n[[package]]\n"
        'name = "serde"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    (root / "uv.lock").write_text(
        "[[package]]\n"
        f'name = "ephe"\nversion = "{version}"\nsource = {{ editable = "." }}\n'
        "\n[[package]]\n"
        'name = "serde"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    return root


def test_the_shared_list_names_all_six_carriers():
    assert set(carriers.CARRIERS) == {
        "pyproject.toml",
        "app/package.json",
        "app/src-tauri/tauri.conf.json",
        "app/src-tauri/Cargo.toml",
        "app/src-tauri/Cargo.lock",
        "uv.lock",
    }


def test_the_checked_in_tree_agrees_on_one_number():
    declared, versions, problems = carriers.check(ROOT)
    assert problems == []
    assert set(versions) == set(carriers.CARRIERS)
    assert all(value for value in versions.values()), (declared, versions)


def test_a_bump_writes_all_six_and_leaves_other_lock_entries_alone(tmp_path):
    root = plant(tmp_path)
    versions = carriers.set_versions(root, "1.3.0")
    assert set(versions.values()) == {"1.3.0"}
    assert (root / "app" / "src-tauri" / "Cargo.lock").read_text(encoding="utf-8").count(
        'version = "1.0.0"'
    ) == 1
    assert (root / "uv.lock").read_text(encoding="utf-8").count('version = "1.0.0"') == 1


def test_a_prerelease_keeps_the_semver_spelling_in_the_manifests_and_pep440_in_uv(tmp_path):
    root = plant(tmp_path)
    carriers.set_versions(root, "1.3.0-beta.2")
    assert 'version = "1.3.0-beta.2"' in (root / "app" / "src-tauri" / "Cargo.lock").read_text(
        encoding="utf-8"
    )
    assert 'version = "1.3.0b2"' in (root / "uv.lock").read_text(encoding="utf-8")
    assert carriers.check(root)[2] == []


def test_a_drifted_carrier_is_named(tmp_path):
    root = plant(tmp_path)
    (root / "app" / "src-tauri" / "Cargo.lock").write_text(
        '[[package]]\nname = "app"\nversion = "1.2.2"\n', encoding="utf-8"
    )
    _declared, _versions, problems = carriers.check(root, "1.2.3")
    assert any("Cargo.lock" in problem for problem in problems), problems


def test_a_tag_that_names_another_version_is_refused(tmp_path):
    root = plant(tmp_path)
    declared, _versions, problems = carriers.check(root, "1.2.4")
    assert declared == "1.2.3"
    assert problems and "the release is 1.2.4" in problems[0]


def test_a_malformed_tag_is_a_usage_error():
    try:
        carriers.tag_version("release-1.2.3")
    except ValueError as exc:
        assert "not a release tag" in str(exc)
    else:  # pragma: no cover - the assertion above is the test
        raise AssertionError("a malformed tag was accepted")


def test_the_cli_refuses_a_number_that_is_not_semver(tmp_path):
    root = plant(tmp_path)
    assert carriers.main(["--root", str(root), "--set", "1.2"]) == 2
    assert carriers.declared_version(root) == "1.2.3"


def test_the_checklist_reads_the_same_six_files(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "release_checklist_carriers", ROOT / "scripts" / "release_checklist.py"
    )
    assert spec and spec.loader
    checklist = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checklist)
    assert set(checklist.carrier_versions(ROOT)) == set(carriers.CARRIERS)


def test_the_bump_cli_writes_all_six(tmp_path):
    root = plant(tmp_path)
    done = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "bump_version.py"),
            "--root", str(root),
            "--version", "1.3.0",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert carriers.read_versions(root) == {rel: "1.3.0" for rel in carriers.CARRIERS}


def test_the_bump_can_derive_the_next_minor(tmp_path):
    root = plant(tmp_path, "1.2.3")
    done = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "bump_version.py"),
            "--root", str(root),
            "--next-minor",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert carriers.declared_version(root) == "1.3.0"
