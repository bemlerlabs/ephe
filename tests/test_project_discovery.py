from __future__ import annotations

import json
from pathlib import Path

import pytest


def _make_python_project(root: Path) -> Path:
    project = root / "Documents" / "Developer" / "ephe-workbench"
    project.mkdir(parents=True)
    (project / ".git").mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='ephe-workbench'\n", encoding="utf-8")
    (project / "README.md").write_text("# Ephe Workbench\n\nLocal AI assistant.\n", encoding="utf-8")
    (project / "tests").mkdir()
    (project / "tests" / "test_app.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    return project


@pytest.mark.asyncio
async def test_given_allowed_mac_roots_when_discover_projects_then_code_project_is_ranked(monkeypatch, tmp_path):
    """
    GIVEN a real project under an allowed Mac-style user folder
    WHEN discover_projects runs
    THEN it finds and ranks the project with stack metadata.
    """
    project = _make_python_project(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    from core.project_discovery import discover_project_records

    records = discover_project_records(query="ephe", roots=[tmp_path / "Documents"], max_results=5)

    assert records
    assert records[0].path == project
    assert records[0].name == "ephe-workbench"
    assert records[0].score >= 8
    assert "python" in records[0].stacks
    assert "pyproject.toml" in records[0].markers


@pytest.mark.asyncio
async def test_given_project_path_when_analyze_project_then_report_contains_status_and_commands(monkeypatch, tmp_path):
    """
    GIVEN a local project path
    WHEN analyze_project runs
    THEN the report contains stack, tests, risks, and next commands.
    """
    project = _make_python_project(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    from core.project_discovery import analyze_project_path

    report = analyze_project_path(project)

    assert "ephe-workbench" in report
    assert "Python" in report
    assert "pytest" in report
    assert "Current state" in report
    assert "Next steps" in report


@pytest.mark.asyncio
async def test_given_project_tools_when_called_then_return_user_facing_markdown(monkeypatch, tmp_path):
    """
    GIVEN project discovery tools are called by the model
    WHEN discover_projects and analyze_project execute
    THEN they return markdown suitable for the chat.
    """
    project = _make_python_project(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    from core.tools import analyze_project, discover_projects

    listing = await discover_projects(query="workbench", root=str(tmp_path / "Documents"), max_results=3)
    report = await analyze_project(str(project))

    assert "ephe-workbench" in listing
    assert str(project) in listing
    assert "Current state" in report
    assert "README.md" in report


def test_given_tool_schemas_when_loaded_then_project_tools_are_available():
    from core.tools import get_tool_schemas

    names = {schema["function"]["name"] for schema in get_tool_schemas()}

    assert "discover_projects" in names
    assert "analyze_project" in names

