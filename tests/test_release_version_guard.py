"""The release tag has to name the version the tagged tree carries.

`release.yml` takes the release name and notes from `GITHUB_REF_NAME` and the bundle version
from `tauri.conf.json`, so a hand-pushed or moved tag can publish bundles of one version under
another. `release_cut.sh` refuses that before a tag exists; a direct `git push origin vX.Y.Z`
never reaches it. The guard is the first release job, before the build, and these tests hold
the workflow and the script to that one comparison.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
GUARD = ROOT / "scripts" / "version_guard.py"


def _doc() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8")) or {}


def _jobs() -> dict:
    return _doc().get("jobs") or {}


def _steps(job: dict) -> list[dict]:
    return [step for step in (job.get("steps") or []) if isinstance(step, dict)]


def _needs(job: dict) -> list[str]:
    needs = job.get("needs") or []
    return [needs] if isinstance(needs, str) else list(needs)


def _load():
    spec = importlib.util.spec_from_file_location("version_guard_under_test", GUARD)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _plant(root: Path, version: str) -> Path:
    (root / "app" / "src-tauri").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "ephe"\nversion = "{version}"\n', encoding="utf-8"
    )
    (root / "app" / "package.json").write_text(
        json.dumps({"version": version}), encoding="utf-8"
    )
    (root / "app" / "src-tauri" / "tauri.conf.json").write_text(
        json.dumps({"version": version}), encoding="utf-8"
    )
    (root / "app" / "src-tauri" / "Cargo.toml").write_text(
        f'[package]\nname = "app"\nversion = "{version}"\n', encoding="utf-8"
    )
    (root / "app" / "src-tauri" / "Cargo.lock").write_text(
        f'[[package]]\nname = "app"\nversion = "{version}"\n', encoding="utf-8"
    )
    (root / "uv.lock").write_text(
        f'[[package]]\nname = "ephe"\nversion = "{version}"\n', encoding="utf-8"
    )
    return root


def test_the_guard_runs_before_the_bundle_build_and_stops_it():
    jobs = _jobs()
    assert "version-guard" in jobs, "release.yml has no version-guard job"
    guard = jobs["version-guard"]
    assert "version_guard.py" in "\n".join(str(step.get("run", "")) for step in _steps(guard))
    assert '"$GITHUB_REF_NAME"' in "\n".join(str(step.get("run", "")) for step in _steps(guard))
    assert "version-guard" in _needs(jobs["build-bundles"]), (
        "build-bundles does not wait for the tag/version guard"
    )


def test_the_guard_refuses_a_tag_that_names_another_version(tmp_path):
    module = _load()
    root = _plant(tmp_path, "1.2.3")
    assert module.main(["--root", str(root), "--tag", "v1.2.3"]) == 0
    assert module.main(["--root", str(root), "--tag", "v1.2.4"]) == 1


def test_the_guard_accepts_the_v_prefix_and_refuses_a_malformed_tag(tmp_path):
    module = _load()
    root = _plant(tmp_path, "1.2.3")
    assert module.main(["--root", str(root), "--tag", "1.2.3"]) == 0
    assert module.main(["--root", str(root), "--tag", "release-1.2.3"]) == 2


def test_the_production_guard_agrees_with_the_checked_in_tree():
    # The tree's carrier is read, not assumed: the tag has to be the one `pyproject.toml` names.
    declared = (ROOT / "pyproject.toml").read_text(encoding="utf-8").split('version = "', 1)[1].split('"', 1)[0]
    done = subprocess.run(
        [sys.executable, str(GUARD), "--tag", f"v{declared}"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "PASS" in done.stdout
