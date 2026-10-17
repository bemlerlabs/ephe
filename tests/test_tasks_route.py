"""Route contract for /api/tasks — the four verbs the surfaces actually use.

Surfaces (proved by search on 2026-10-08, finding #18):
  GET    app/src/hooks/useTasks.ts:49, app/src/components/dashboard/AgentStatusButton.tsx:110,
         app/src/components/dashboard/agent/tabsC.tsx:44,
         app/src/components/dashboard/settings/model/useSettingsLists.ts:45,
         app/src/components/dashboard/settings/model/useSettingsCore.ts:98
  POST   app/src/components/dashboard/agent/tabsC.tsx:55,
         app/src/components/dashboard/settings/model/useSettingsLists.ts:97
  PUT    app/src/components/dashboard/agent/tabsC.tsx:63 (status) and :79 (title),
         app/src/components/dashboard/settings/model/useSettingsLists.ts:74
  DELETE app/src/components/dashboard/agent/tabsC.tsx:67,
         app/src/components/dashboard/settings/model/useSettingsLists.ts:82

None of the four is dead, so none is removed. GET and POST were already pinned
here and in tests/test_tasks_ui.py; PUT and DELETE answered only through the
``success`` flag and had no route-level pin at all. That flag is what this file
pins: a write that reports success for a task it never touched stays invisible
to the surface (both callers ignore the body and simply reload the list), so the
row would refuse to move and nobody would know why.

Isolation: ``core.tasks.task_manager`` is a module-level singleton pointed at
``~/.ephe/tasks.json``. Before this file had a fixture, its tests created and
deleted rows in the user's real task file.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.tasks import task_manager
from server.main import create_app


@pytest.fixture(autouse=True)
def isolated_task_store(tmp_path, monkeypatch):
    """Keep every case in this file off the user's ~/.ephe/tasks.json."""
    store = tmp_path / "tasks.json"
    store.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(task_manager, "storage_path", store)
    return store


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _create(client: TestClient, title: str, project: str | None = None) -> str:
    body = {"title": title} if project is None else {"title": title, "project": project}
    resp = client.post("/api/tasks", json=body)
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    return payload["id"]


def _rows(client: TestClient) -> list[dict]:
    resp = client.get("/api/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    return data


def _row(client: TestClient, task_id: str) -> dict:
    return next(t for t in _rows(client) if t["id"] == task_id)


# POST

def test_post_tasks_creates_and_lists(client):
    task_id = _create(client, "QA test task", project="qa")
    assert len(_rows(client)) == 1
    assert _row(client, task_id)["title"] == "QA test task"


def test_post_tasks_rejects_empty_title(client):
    """Both surfaces trim before sending (tabsC.tsx:52, useSettingsLists.ts:93),
    so this 200-with-success-false answer is the server's own guard, not a path
    a user can reach — pinned so a later change to the status code is a decision
    and not an accident."""
    resp = client.post("/api/tasks", json={"title": "   "})
    assert resp.status_code == 200
    assert resp.json()["success"] is False
    assert _rows(client) == []


# GET

def test_get_tasks_answers_the_fields_the_list_renders(client):
    """The task card and the Settings rows read exactly these four keys; a fifth
    appearing or one of them going is a contract change for two surfaces."""
    task_id = _create(client, "Fields contract", project="api")
    row = _row(client, task_id)
    assert set(row) == {"id", "title", "status", "project"}
    assert row["status"] == "open"  # the vocabulary toggle() switches between
    assert row["project"] == "api"


# PUT

def test_put_status_round_trips_into_the_list(client):
    task_id = _create(client, "Toggle me")
    resp = client.put(f"/api/tasks/{task_id}", json={"status": "done"})
    assert resp.status_code == 200
    assert resp.json() == {"success": True}
    assert _row(client, task_id)["status"] == "done"


def test_put_title_round_trips_into_the_list(client):
    """The inline edit path (tabsC.tsx:79) sends {title} only."""
    task_id = _create(client, "Before")
    resp = client.put(f"/api/tasks/{task_id}", json={"title": "After"})
    assert resp.json()["success"] is True
    row = _row(client, task_id)
    assert row["title"] == "After"
    assert row["status"] == "open"  # an untouched field stays untouched


def test_put_unknown_task_does_not_report_success(client):
    resp = client.put("/api/tasks/task-does-not-exist", json={"status": "done"})
    assert resp.status_code == 200
    assert resp.json() == {"success": False}


def test_put_empty_patch_on_existing_task_reports_found(client):
    """update_task() answers whether the id was found, not whether a field
    changed — an empty patch therefore stays a no-op on a real task."""
    task_id = _create(client, "Untouched")
    resp = client.put(f"/api/tasks/{task_id}", json={})
    assert resp.json() == {"success": True}
    assert _row(client, task_id)["title"] == "Untouched"



def test_delete_removes_the_row_and_reports_it(client):
    task_id = _create(client, "Delete me")
    resp = client.delete(f"/api/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json() == {"success": True}
    assert _rows(client) == []


def test_delete_unknown_task_does_not_report_success(client):
    resp = client.delete("/api/tasks/task-never-created")
    assert resp.status_code == 200
    assert resp.json() == {"success": False}
