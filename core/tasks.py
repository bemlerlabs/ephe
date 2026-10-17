"""
◑ Ephe – Task Manager
core/tasks.py

Manages asynchronous and synchronous persistence of user tasks in a JSON file.
"""
import json
import uuid
import os
from pathlib import Path
from typing import Optional, List, Dict, Any


def _device_dir() -> Path:
    """The device folder — `EPHE_CONFIG_DIR`, otherwise `~/.ephe`.

    Resolved at construction time so a server started with a moved root owns a task
    list of its own; tests that build the manager after setting the env get the same.
    """
    return Path(os.environ.get("EPHE_CONFIG_DIR") or str(Path.home() / ".ephe"))


class TaskManager:
    def __init__(self, storage_path: Optional[Path | str] = None):
        if storage_path is None:
            # The device folder, like every other store (artifact_store, plugin_store).
            # Without this the recording against a throwaway root read the user's rows.
            storage_path = _device_dir() / "tasks.json"
        self.storage_path = Path(storage_path)
        self._ensure_file()

    def _ensure_file(self):
        if not self.storage_path.exists():
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            self.storage_path.write_text("[]", encoding="utf-8")

    def _read_tasks(self) -> List[Dict[str, Any]]:
        try:
            content = self.storage_path.read_text(encoding="utf-8")
            return json.loads(content)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _write_tasks(self, tasks: List[Dict[str, Any]]):
        self.storage_path.write_text(json.dumps(tasks, indent=2, ensure_ascii=False), encoding="utf-8")

    def get_tasks(self) -> List[Dict[str, Any]]:
        """Reads every task."""
        return self._read_tasks()

    def add_task(self, title: str, project: Optional[str] = None) -> str:
        """Adds a task and returns the new ID."""
        tasks = self._read_tasks()
        task_id = f"task-{uuid.uuid4().hex[:8]}"
        new_task = {
            "id": task_id,
            "title": title,
            "status": "open",
            "project": project
        }
        tasks.append(new_task)
        self._write_tasks(tasks)
        return task_id

    def update_task(self, task_id: str, status: Optional[str] = None, title: Optional[str] = None, project: Optional[str] = None) -> bool:
        """Updates a task. Returns True when it was found and changed."""
        tasks = self._read_tasks()
        updated = False
        for t in tasks:
            if t["id"] == task_id:
                if status is not None:
                    t["status"] = status
                if title is not None:
                    t["title"] = title
                if project is not None:
                    t["project"] = project
                updated = True
                break
        if updated:
            self._write_tasks(tasks)
        return updated

    def delete_task(self, task_id: str) -> bool:
        """Deletes a task. Returns True when it was found and removed."""
        tasks = self._read_tasks()
        new_tasks = [t for t in tasks if t["id"] != task_id]
        if len(new_tasks) < len(tasks):
            self._write_tasks(new_tasks)
            return True
        return False

# Global, importable manager
task_manager = TaskManager()
