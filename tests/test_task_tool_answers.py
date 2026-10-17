"""Tool-surface tests for manage_tasks: answers a model can act on.

Exercises the boring failures of core/tools/task_tools.py — an empty list, an
id that does not exist, a status outside the schema, a filter nobody applied —
and pins what each one now answers. A real TaskManager on a temp file is used
(so "nothing was changed" is proven against the store, not against a mock).
"""
from __future__ import annotations

import pytest

from core.tasks import TaskManager
from core.tools.task_tools import TASK_STATUSES, manage_tasks


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    """A task manager writing inside tmp_path — never into ~/.ephe.

    autouse: without it a test that forgets the fixture reads the real
    ~/.ephe/tasks.json of whoever runs the suite (caught doing exactly that).
    """
    manager = TaskManager(storage_path=tmp_path / "tasks.json")
    monkeypatch.setattr("core.tasks.task_manager", manager)
    return manager


async def add(title: str, project: str | None = None) -> str:
    answer = await manage_tasks("add", title=title, project=project)
    return answer.split("ID: ")[-1].strip()


class TestEmptyAndUnknown:
    @pytest.mark.asyncio
    async def test_empty_list_names_the_next_action(self, store):
        answer = await manage_tasks("list")
        assert "No tasks" in answer
        assert "add" in answer

    @pytest.mark.asyncio
    async def test_unknown_id_offers_the_ids_that_actually_exist(self, store):
        first = await add("Write the changelog")
        answer = await manage_tasks("update", task_id="task-deadbeef", status="done")
        assert "not found" in answer
        assert first in answer
        assert "task-deadbeef" in answer

    @pytest.mark.asyncio
    async def test_unknown_id_on_an_empty_list_says_so(self, store):
        answer = await manage_tasks("delete", task_id="task-nope")
        assert "not found" in answer
        assert "no tasks" in answer.lower()

    @pytest.mark.asyncio
    async def test_unknown_action_lists_the_allowed_actions(self):
        answer = await manage_tasks("complete", task_id="whatever")
        assert "unknown action" in answer
        for action in ("add", "update", "delete", "list"):
            assert action in answer


class TestStatusGuard:
    @pytest.mark.asyncio
    async def test_status_outside_the_schema_is_refused_and_nothing_is_written(self, store):
        task = await add("Review the PR")
        answer = await manage_tasks("update", task_id=task, status="completed")
        assert "not allowed" in answer
        assert ", ".join(TASK_STATUSES) in answer
        assert "Nothing was changed" in answer
        assert store.get_tasks()[0]["status"] == "open"

    @pytest.mark.asyncio
    async def test_empty_status_is_refused_instead_of_blanking_the_badge(self, store):
        task = await add("Buy stamps")
        answer = await manage_tasks("update", task_id=task, status="")
        assert "not allowed" in answer
        assert store.get_tasks()[0]["status"] == "open"

    @pytest.mark.asyncio
    async def test_a_listed_status_still_updates_successfully(self, store):
        task = await add("Ship the wave")
        answer = await manage_tasks("update", task_id=task, status="done")
        assert "updated successfully" in answer
        assert "status" in answer
        assert store.get_tasks()[0]["status"] == "done"

    @pytest.mark.asyncio
    async def test_update_with_nothing_to_change_says_so(self, store):
        task = await add("Buy stamps")
        answer = await manage_tasks("update", task_id=task)
        assert "Nothing to change" in answer
        assert "Buy stamps" in answer

    @pytest.mark.asyncio
    async def test_a_bad_status_is_refused_before_the_store_is_read(self, store):
        """Ordering matters: the argument problem is the actionable answer, even
        for an id that does not exist."""
        answer = await manage_tasks("update", task_id="task-nope", status="wip")
        assert "not allowed" in answer
        assert ", ".join(TASK_STATUSES) in answer

    @pytest.mark.asyncio
    async def test_update_still_answers_when_the_manager_cannot_list(self, monkeypatch):
        """The read-back is a bonus, not a precondition — a manager that only
        answers update_task must still get a truthful success line."""

        class ListingBlind:
            def update_task(self, task_id, status=None, title=None, project=None):
                return True

            def get_tasks(self):
                raise TypeError("this manager does not list")

        monkeypatch.setattr("core.tasks.task_manager", ListingBlind())
        answer = await manage_tasks("update", task_id="t1", status="done")
        assert "updated successfully" in answer
        assert "(status)" in answer
        assert "Now:" not in answer


class TestProjectFilter:
    @pytest.mark.asyncio
    async def test_list_by_project_filters_and_says_so(self, store):
        await add("Write the changelog", project="release")
        await add("Review the PR", project="release")
        await add("Buy stamps")
        answer = await manage_tasks("list", project="release")
        assert "project 'release'" in answer
        assert "Write the changelog" in answer
        assert "Buy stamps" not in answer
        assert "hidden" in answer

    @pytest.mark.asyncio
    async def test_unknown_project_offers_the_projects_that_exist(self, store):
        await add("Write the changelog", project="release")
        answer = await manage_tasks("list", project="marketing")
        assert "No tasks in project 'marketing'" in answer
        assert "release" in answer

    @pytest.mark.asyncio
    async def test_unfiltered_list_still_shows_every_task(self, store):
        await add("One", project="release")
        await add("Two")
        answer = await manage_tasks("list")
        assert "One" in answer and "Two" in answer
