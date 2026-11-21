"""A tagged milestone release with no signing key stops before the bundle build.

The old workflow wrote `signed=false`, uploaded unsigned bundles and still left a draft release
the owner could publish; the updater then answered 404 and no installed desktop could reach the
release. The policy ships a signed shell, so the key is a build precondition, not a warning.
A local build without a key has one explicit path: `release_desktop.sh --unsigned`.
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / ".github" / "workflows" / "release.yml"
DESKTOP = ROOT / "scripts" / "release_desktop.sh"
CHECKLIST = ROOT / "scripts" / "release_checklist_updater.py"


def _doc() -> dict:
    return yaml.safe_load(RELEASE.read_text(encoding="utf-8")) or {}


def _steps(job: dict) -> list[dict]:
    return [step for step in (job.get("steps") or []) if isinstance(step, dict)]


def _run(step: dict) -> str:
    return str(step.get("run", ""))


def test_the_bundle_job_has_a_guard_that_exits_nonzero_without_the_key():
    job = (_doc().get("jobs") or {})["build-bundles"]
    steps = _steps(job)
    guard = [step for step in steps if "TAURI_SIGNING_PRIVATE_KEY" in str(step.get("env") or {}) and "::error::" in _run(step)]
    assert guard, "build-bundles has no step that refuses an empty signing key"
    text = _run(guard[0])
    assert "exit 1" in text, text
    assert "TAURI_SIGNING_PRIVATE_KEY" in text

    tauri = next(
        index for index, step in enumerate(steps) if "tauri-action" in str(step.get("uses", ""))
    )
    assert steps.index(guard[0]) < tauri, "the guard runs after the bundle action"


def test_the_workflow_has_no_unsigned_draft_path_left():
    text = RELEASE.read_text(encoding="utf-8")
    assert "signed=false" not in text, "an unsigned tagged release is still a reachable branch"


def test_the_checklist_treats_a_missing_key_as_a_refusal():
    text = CHECKLIST.read_text(encoding="utf-8")
    assert 'return "FAIL", f"{key} missing' in text
    assert "a signed milestone build cannot run" in text


def test_the_local_unsigned_build_is_explicit_and_not_publishable():
    text = DESKTOP.read_text(encoding="utf-8")
    assert "--unsigned" in text
    assert "UNSIGNED=1" in text
    assert "--publish needs the signed updater artifacts" in text
    assert "npx tauri build" in text


def test_the_release_desktop_build_still_fails_closed_without_a_key():
    text = DESKTOP.read_text(encoding="utf-8")
    assert "signing key missing" in text
    assert "exit 1" in text
