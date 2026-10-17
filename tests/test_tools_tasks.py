"""
◑ Ephe – core.tools.task_tools (Phase 0.8 TDD)
tests/test_tools_tasks.py

Covers manage_tasks.

Given / When / Then — strict adherence.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.tools.task_tools import manage_tasks


class TestManageTasks:

    @pytest.mark.asyncio
    async def test_add_returns_task_id(self):
        """
        GIVEN  action="add", title="Test task"
        WHEN   manage_tasks is called
        THEN   the result contains "added successfully" and the id
        """
        with patch("core.tasks.task_manager") as mock_mgr:
            mock_mgr.add_task.return_value = "t123"

            result = await manage_tasks(action="add", title="Test task")

            assert "added successfully" in result
            assert "t123" in result
            mock_mgr.add_task.assert_called_once_with(title="Test task", project=None)

    @pytest.mark.asyncio
    async def test_add_requires_title(self):
        """
        GIVEN  action="add", no title
        WHEN   manage_tasks is called
        THEN   the result contains "title required"
        """
        result = await manage_tasks(action="add")
        assert "title required" in result

    @pytest.mark.asyncio
    async def test_add_with_project(self):
        """
        GIVEN  action="add", title and project
        WHEN   manage_tasks is called
        THEN   project is passed on
        """
        with patch("core.tasks.task_manager") as mock_mgr:
            mock_mgr.add_task.return_value = "t1"

            await manage_tasks(action="add", title="Task", project="ephe")

            mock_mgr.add_task.assert_called_once_with(title="Task", project="ephe")

    @pytest.mark.asyncio
    async def test_update_returns_success(self):
        """
        GIVEN  action="update", task_id, status="done"
        WHEN   manage_tasks is called
        THEN   the result contains "updated successfully"
        """
        with patch("core.tasks.task_manager") as mock_mgr:
            mock_mgr.update_task.return_value = True

            result = await manage_tasks(action="update", task_id="t1", status="done")

            assert "updated successfully" in result
            mock_mgr.update_task.assert_called_once_with("t1", status="done", title=None, project=None)

    @pytest.mark.asyncio
    async def test_update_not_found(self):
        """
        GIVEN  action="update", task_id does not exist
        WHEN   manage_tasks is called
        THEN   the result contains the not-found message
        """
        with patch("core.tasks.task_manager") as mock_mgr:
            mock_mgr.update_task.return_value = False

            result = await manage_tasks(action="update", task_id="t_unknown")

            assert "not found" in result

    @pytest.mark.asyncio
    async def test_update_requires_task_id(self):
        """
        GIVEN  action="update", no task_id
        WHEN   manage_tasks is called
        THEN   the result contains "task_id required"
        """
        result = await manage_tasks(action="update")
        assert "task_id required" in result

    @pytest.mark.asyncio
    async def test_delete_returns_success(self):
        """
        GIVEN  action="delete", task_id="t1"
        WHEN   manage_tasks is called
        THEN   the result contains "deleted successfully"
        """
        with patch("core.tasks.task_manager") as mock_mgr:
            mock_mgr.delete_task.return_value = True

            result = await manage_tasks(action="delete", task_id="t1")

            assert "deleted successfully" in result

    @pytest.mark.asyncio
    async def test_delete_not_found(self):
        """
        GIVEN  action="delete", task_id does not exist
        WHEN   manage_tasks is called
        THEN   the result contains the not-found message
        """
        with patch("core.tasks.task_manager") as mock_mgr:
            mock_mgr.delete_task.return_value = False

            result = await manage_tasks(action="delete", task_id="t_unknown")

            assert "not found" in result

    @pytest.mark.asyncio
    async def test_delete_requires_task_id(self):
        """
        GIVEN  action="delete", no task_id
        WHEN   manage_tasks is called
        THEN   the result contains "task_id required"
        """
        result = await manage_tasks(action="delete")
        assert "task_id required" in result

    @pytest.mark.asyncio
    async def test_list_returns_empty_message(self):
        """
        GIVEN  no tasks exist
        WHEN   manage_tasks(action="list") is called
        THEN   the result contains "No tasks"
        """
        with patch("core.tasks.task_manager") as mock_mgr:
            mock_mgr.get_tasks.return_value = []

            result = await manage_tasks(action="list")

            assert "No tasks" in result

    @pytest.mark.asyncio
    async def test_list_returns_formatted_tasks(self):
        """
        GIVEN  tasks exist
        WHEN   manage_tasks(action="list") is called
        THEN   the result lists tasks in the format "- [status] title"
        """
        with patch("core.tasks.task_manager") as mock_mgr:
            mock_mgr.get_tasks.return_value = [
                {"status": "open", "title": "Task 1", "id": "t1"},
                {"status": "done", "title": "Task 2", "id": "t2"},
            ]

            result = await manage_tasks(action="list")

            assert "[open]" in result
            assert "[done]" in result
            assert "Task 1" in result
            assert "Task 2" in result

    @pytest.mark.asyncio
    async def test_unknown_action_returns_error(self):
        """
        GIVEN  action="unknown"
        WHEN   manage_tasks is called
        THEN   the result contains "unknown action"
        """
        result = await manage_tasks(action="unknown")
        assert "unknown action" in result
