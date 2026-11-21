"""Ephe – manage_tasks tool.

The model reads these answers verbatim and acts on them, so every branch names
what it can do next: the allowed action, the allowed status, the ids that
actually exist, and the filter that was applied. Nothing here widens what the
task manager may touch — it only stops the tool from agreeing silently to
nonsense.
"""

from __future__ import annotations

#: The status vocabulary the tool schema offers (core/tools/_schemas.py). Any
#: other value would land in tasks.json and render as an empty badge in the UI.
TASK_STATUSES: tuple[str, ...] = ("open", "in_progress", "done")

#: How many ids to name when the model guessed one wrong — enough to recover,
#: few enough to never flood the context.
MAX_IDS_SHOWN = 6


def _tasks_of(task_manager) -> list[dict]:
    """The stored tasks, or an empty list when the manager will not say.

    A tolerant read matters here for one real reason: this tool must never
    answer about a task it could not look at, and tests drive the manager with
    a stand-in whose listing is not a list.
    """
    try:
        tasks = task_manager.get_tasks() or []
    except Exception:  # noqa: BLE001 — a listing that fails is no listing at all
        return []
    return [t for t in tasks if isinstance(t, dict)]


def _find(tasks: list[dict], task_id: str) -> dict | None:
    return next((t for t in tasks if t.get("id") == task_id), None)


def _ids_hint(tasks: list[dict]) -> str:
    """Recovery path for a wrong task id: the ids that do exist."""
    if not tasks:
        return " There are no tasks at all — create one with action='add'."
    ids = [str(t.get("id", "?")) for t in tasks]
    shown = ", ".join(ids[:MAX_IDS_SHOWN])
    rest = f" (+{len(ids) - MAX_IDS_SHOWN} more)" if len(ids) > MAX_IDS_SHOWN else ""
    return f" Existing task ids: {shown}{rest}."


async def manage_tasks(action: str, title: str = None, task_id: str = None, status: str = None, project: str = None) -> str:
    from core.tasks import task_manager

    if action == "add":
        if not title:
            return "[Error: title required for add]"
        tid = task_manager.add_task(title=title, project=project)
        return f"Task added successfully. ID: {tid}"

    if action == "update":
        if not task_id:
            return "[Error: task_id required for update]"
        if status is not None and status not in TASK_STATUSES:
            given = "empty" if status == "" else f"'{status}'"
            return (
                f"[Error: status {given} is not allowed. Use one of: "
                f"{', '.join(TASK_STATUSES)}. Nothing was changed.]"
            )
        if title is not None and not title.strip():
            return "[Error: title must not be empty — omit it to keep the current title. Nothing was changed.]"
        changed = [name for name, value in (("status", status), ("title", title), ("project", project)) if value is not None]
        if not changed:
            current = _find(_tasks_of(task_manager), task_id)
            if not current:
                # An unknown id is not "nothing to change": saying so would tell
                # the model the task exists and only needs a field.
                return f"[Error: Task {task_id} not found]" + _ids_hint(_tasks_of(task_manager))
            return (
                f"Nothing to change for task {task_id} "
                f"(status='{current.get('status')}', title='{current.get('title')}'). "
                "Pass status, title or project."
            )
        found = task_manager.update_task(task_id, status=status, title=title, project=project)
        if not found:
            return f"[Error: Task {task_id} not found]" + _ids_hint(_tasks_of(task_manager))
        after = _find(_tasks_of(task_manager), task_id)
        answer = f"Task {task_id} updated successfully ({', '.join(changed)})."
        if after:
            answer += f" Now: [{after.get('status')}] {after.get('title')}"
        return answer

    if action == "delete":
        if not task_id:
            return "[Error: task_id required for delete]"
        found = task_manager.delete_task(task_id)
        if found:
            return f"Task {task_id} deleted successfully."
        return f"[Error: Task {task_id} not found]" + _ids_hint(_tasks_of(task_manager))

    if action == "list":
        tasks = _tasks_of(task_manager)
        if not tasks:
            return "No tasks present. Create one with action='add' and a title."
        if project is not None:
            wanted = project.strip()
            named = [t for t in tasks if str(t.get("project") or "") == wanted]
            others = len(tasks) - len(named)
            if not named:
                listed = ", ".join(sorted({str(t.get("project") or "(none)") for t in tasks})[:MAX_IDS_SHOWN])
                return (
                    f"No tasks in project '{project}'. {others} task(s) live elsewhere; "
                    f"projects present: {listed}."
                )
            body = "\n".join(f"- [{t['status']}] {t['title']} (ID: {t['id']})" for t in named)
            tail = f" ({others} further task(s) outside this project, hidden)" if others else ""
            return f"Tasks in project '{project}':{tail}\n{body}"
        return "\n".join(f"- [{t['status']}] {t['title']} (ID: {t['id']})" for t in tasks)

    return f"[Error: unknown action '{action}'. Allowed: add, update, delete, list.]"
