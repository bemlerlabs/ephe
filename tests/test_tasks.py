"""
Task manager — GWT, 3 levels deep.

GIVEN: the task system
WHEN:  tasks are created, read, marked and deleted (CRUD)
THEN:  the changes are persisted as JSON and loaded correctly

GIVEN: the tooling system
WHEN:  the manage_tasks tool is called
THEN:  the tool handles the action correctly and gives feedback to the LLM

GIVEN: a running chat system
WHEN:  a user words a task in the text
THEN:  the task is added in the background through the tool
"""
import os
import json
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock

# Perspective 1: unit level — TaskManager CRUD

class TestTaskManagerUnitPerspective:
    """GIVEN TaskManager, WHEN CRUD operations performed, THEN JSON is updated correctly."""

    @pytest.fixture
    def temp_tasks_file(self, tmp_path):
        return tmp_path / "tasks.json"

    def test_given_manager_when_add_task_then_saved_to_json(self, temp_tasks_file):
        """
        GIVEN: a fresh TaskManager
        WHEN:  a task is added
        THEN:  the task lands in the JSON file with status 'open'
        """
        from core.tasks import TaskManager

        manager = TaskManager(storage_path=temp_tasks_file)
        task_id = manager.add_task("Milch einkaufen", project="Privat")

        # Perspective 1: an ID is returned
        assert task_id is not None

        # Perspective 2: present in RAM
        tasks = manager.get_tasks()
        assert len(tasks) == 1
        assert tasks[0]["title"] == "Milch einkaufen"
        assert tasks[0]["status"] == "open"
        assert tasks[0]["project"] == "Privat"

        # Perspective 3: persisted in the file
        saved_data = json.loads(temp_tasks_file.read_text())
        assert len(saved_data) == 1
        assert saved_data[0]["id"] == task_id

    def test_given_manager_when_complete_task_then_status_done(self, temp_tasks_file):
        """
        GIVEN: a TaskManager holding one open task
        WHEN:  the task is completed
        THEN:  the status changes to 'done'
        """
        from core.tasks import TaskManager

        manager = TaskManager(storage_path=temp_tasks_file)
        task_id = manager.add_task("Wäsche waschen")

        manager.update_task(task_id, status="done")

        tasks = manager.get_tasks()
        assert tasks[0]["status"] == "done"

    def test_given_manager_when_delete_task_then_removed(self, temp_tasks_file):
        """
        GIVEN: a TaskManager holding tasks
        WHEN:  a task is deleted
        THEN:  it disappears from the list and the file
        """
        from core.tasks import TaskManager

        manager = TaskManager(storage_path=temp_tasks_file)
        task_id = manager.add_task("Lösch mich")
        assert len(manager.get_tasks()) == 1

        manager.delete_task(task_id)
        assert len(manager.get_tasks()) == 0


# Perspective 2: integration level — tool calling

class TestTaskToolIntegrationPerspective:
    """GIVEN manage_tasks tool, WHEN called by LLM, THEN routes to TaskManager."""

    @pytest.fixture
    def mock_manager(self):
        with patch("core.tasks.task_manager") as mock:
            yield mock

    @pytest.mark.asyncio
    async def test_given_tool_schema_when_checked_then_manage_tasks_exists(self):
        """
        GIVEN: the tool definitions
        WHEN:  manage_tasks is looked up
        THEN:  it exists with the correct parameters (action, title, task_id)
        """
        from core.tools import get_tool_schemas

        task_tool = next((t for t in get_tool_schemas() if t["function"]["name"] == "manage_tasks"), None)
        assert task_tool is not None, "THEN: manage_tasks muss als Tool registriert sein"

        props = task_tool["function"]["parameters"]["properties"]
        assert "action" in props
        assert "title" in props
        assert "task_id" in props

    @pytest.mark.asyncio
    async def test_given_tool_when_add_action_then_manager_add_called(self, mock_manager):
        """
        GIVEN: the execute_tool system
        WHEN:  manage_tasks is called with action='add'
        THEN:  task_manager.add_task runs
        """
        from core.tools import execute_tool

        mock_manager.add_task.return_value = "task-123"

        res = await execute_tool("manage_tasks", {"action": "add", "title": "Brot kaufen"})

        mock_manager.add_task.assert_called_once_with(title="Brot kaufen", project=None)
        assert "added successfully" in res.lower()
        assert "task-123" in res


# Perspective 3: system level — initialization

class TestTaskSystemPerspective:
    """GIVEN the application startup, WHEN initialized, THEN tasks are loaded from disk."""

    def test_given_app_startup_when_tasks_json_exists_then_loaded(self, tmp_path):
        """
        GIVEN: a tasks.json exists in the appDataDir
        WHEN:  the global TaskManager is loaded
        THEN:  the tasks are available right away
        """
        from core.tasks import TaskManager

        tasks_file = tmp_path / "tasks.json"
        tasks_file.write_text(json.dumps([{"id": "t1", "title": "Alt-Task", "status": "open", "project": None}]))

        manager = TaskManager(storage_path=tasks_file)
        tasks = manager.get_tasks()

        assert len(tasks) == 1
        assert tasks[0]["title"] == "Alt-Task"
