"""server/routes/tasks.py — the global task list behind the Steps surfaces.

Finding #18 audit (2026-10-08): all four verbs have a live caller, none is dead,
none is removed. Contract pinned in tests/test_tasks_route.py (GET also
tests/test_tasks_ui.py). Callers: the agent panel's Steps tab
(app/src/components/dashboard/agent/tabsC.tsx:44,55,63,67,79) and the Settings
tasks section (app/src/components/dashboard/settings/model/useSettingsLists.ts:45,74,82,97);
GET is additionally polled by app/src/hooks/useTasks.ts:49 and
app/src/components/dashboard/AgentStatusButton.tsx:110.

Note on the answers: PUT and DELETE report ``{"success": found}`` and both
callers ignore the body, reloading the list instead — so the flag is the only
place a failed write can surface. That is why the pin asserts it cannot lie.
"""
from fastapi import APIRouter
from core.tasks import task_manager

router = APIRouter()

@router.get("/tasks", tags=["Tasks"])
async def get_tasks():
    """Returns all tasks from the local JSON."""
    return task_manager.get_tasks()

@router.post("/tasks", tags=["Tasks"])
async def create_task(payload: dict):
    """Creates a task (reuses task_manager.add_task)."""
    title = (payload.get("title") or "").strip()
    if not title:
        return {"success": False, "id": None, "error": "title fehlt"}
    task_id = task_manager.add_task(title, payload.get("project"))
    return {"success": True, "id": task_id}

@router.put("/tasks/{task_id}", tags=["Tasks"])
async def update_task(task_id: str, payload: dict):
    """Updates a task via the API."""
    status = payload.get("status")
    title = payload.get("title")
    project = payload.get("project")
    found = task_manager.update_task(task_id, status=status, title=title, project=project)
    return {"success": found}

@router.delete("/tasks/{task_id}", tags=["Tasks"])
async def delete_task(task_id: str):
    """Deletes a task via the API."""
    found = task_manager.delete_task(task_id)
    return {"success": found}
