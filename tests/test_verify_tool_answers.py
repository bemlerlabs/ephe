"""Tool-surface tests for verify_artifact: the gate must not agree silently.

Exercises core/tools/verify_tools.py on the cases that used to answer
ARTIFACT_VERIFIED (or crash) while the check the model asked for was never
read: a typo'd key, an unknown kind, a non-number, a single required file sent
as a string, an empty folder. Hermetic: the allowed roots are patched onto
tmp_path where ``core.tools.base`` resolves them.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from core.tools import base as tools_base
from core.tools import verify_tools
from core.tools.verify_tools import _verify, verify_artifact


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    root = tmp_path / "artifacts"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(tools_base, "_resolve_allowed_roots", lambda: [root])
    return root


def run(path, checks=None):
    return asyncio.run(verify_artifact(str(path), json.dumps(checks) if checks else "{}"))


def report_of(answer: str) -> dict:
    return json.loads(answer.split(": ", 1)[1])


@pytest.fixture()
def textfile(sandbox):
    path = sandbox / "report.md"
    path.write_text(" ".join(f"word{i}" for i in range(40)), encoding="utf-8")
    return path


class TestChecksAreActuallyRead:
    def test_typo_in_a_check_key_fails_the_gate(self, sandbox, textfile):
        answer = run(textfile, {"kind": "file", "min_pagez": 3})
        assert answer.startswith("ARTIFACT_FAILED")
        assert "min_pagez" in answer
        assert "min_words" in answer  # names what this kind does accept

    def test_a_word_limit_for_the_wrong_kind_names_the_right_one(self, sandbox, textfile):
        answer = run(textfile, {"kind": "pdf", "min_words": 10})
        assert answer.startswith("ARTIFACT_FAILED")
        assert "min_words" in answer
        assert "min_pages" in answer

    def test_unknown_kind_lists_the_allowed_kinds(self, sandbox, textfile):
        answer = run(textfile, {"kind": "csv"})
        assert answer.startswith("ARTIFACT_FAILED")
        for kind in ("pdf", "pptx", "docx", "xlsx", "project", "file", "image"):
            assert kind in answer

    def test_non_numeric_limit_fails_instead_of_raising(self, sandbox, textfile):
        answer = run(textfile, {"kind": "file", "min_words": "many"})
        assert answer.startswith("ARTIFACT_FAILED")
        assert "min_words" in answer
        assert "not a number" in answer

    def test_negative_limit_is_refused_with_its_value(self, sandbox, textfile):
        answer = run(textfile, {"min_bytes": -5})
        assert answer.startswith("ARTIFACT_FAILED")
        assert "min_bytes" in answer

    def test_a_string_number_still_works_as_a_limit(self, sandbox, textfile):
        answer = run(textfile, {"kind": "file", "min_words": "1000"})
        assert answer.startswith("ARTIFACT_FAILED")
        assert "below min_words 1000" in answer


class TestPathsAndFolders:
    def test_missing_path_offers_names_from_the_same_folder(self, sandbox, textfile):
        answer = run(sandbox / "never-touched.pdf")
        assert answer.startswith("ARTIFACT_FAILED")
        assert report_of(answer)["kind"] == "missing"
        assert "report.md" in answer

    def test_missing_path_in_a_missing_folder_stays_short(self, sandbox):
        answer = run(sandbox / "gone" / "deep.pdf")
        assert answer.startswith("ARTIFACT_FAILED")
        assert "does not exist" in answer

    def test_empty_path_is_not_read_as_the_workspace(self, sandbox):
        answer = run("")
        assert answer.startswith("ARTIFACT_FAILED")
        assert "no path given" in answer

    def test_whitespace_path_is_not_read_as_the_workspace(self, sandbox):
        assert "no path given" in run("   ")

    def test_empty_folder_is_not_a_verified_project(self, sandbox):
        folder = sandbox / "proj"
        folder.mkdir()
        answer = run(folder, {"kind": "project"})
        assert answer.startswith("ARTIFACT_FAILED")
        assert "no files" in answer

    def test_min_bytes_on_a_folder_is_reported_not_ignored(self, sandbox):
        folder = sandbox / "proj2"
        folder.mkdir()
        (folder / "a.txt").write_text("content here for the gate" * 3)
        answer = run(folder, {"min_bytes": 10})
        assert answer.startswith("ARTIFACT_FAILED")
        assert "min_files" in answer

    def test_a_real_project_still_verifies(self, sandbox):
        project = sandbox / "app"
        (project / "src").mkdir(parents=True)
        (project / "README.md").write_text("# demo\n" + "real content here\n" * 4)
        (project / "src" / "main.py").write_text("def main():\n    return 1\n")
        answer = run(project, {"kind": "project", "min_files": 2, "required_files": ["README.md", "src/main.py"]})
        assert answer.startswith("ARTIFACT_VERIFIED"), answer


class TestRequiredFilesShape:
    def test_one_path_as_a_string_is_one_requirement_not_ten(self, sandbox):
        project = sandbox / "app2"
        project.mkdir()
        (project / "notes.txt").write_text("some content here for the gate")
        answer = run(project, {"kind": "project", "required_files": "README.md"})
        assert answer.startswith("ARTIFACT_FAILED")
        assert "missing required files: README.md" in answer
        assert "R, E, A" not in answer

    def test_a_non_list_shape_is_named(self, sandbox):
        project = sandbox / "app3"
        project.mkdir()
        (project / "notes.txt").write_text("some content here for the gate")
        answer = run(project, {"kind": "project", "required_files": 7})
        assert answer.startswith("ARTIFACT_FAILED")
        assert "required_files" in answer

    def test_report_never_raises_on_a_hostile_checks_object(self, sandbox, textfile):
        # The docstring promises a pure report; the numeric options used to
        # escape ValueError out of the tool.
        report = _verify(str(textfile), '{"min_bytes": [1,2], "kind": "file"}')
        assert report["verified"] is False
        assert any("min_bytes" in line for line in report["failures"])
