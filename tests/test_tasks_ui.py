"""
Task UI integration — GWT, 3 levels of depth.

GIVEN: the API for tasks
WHEN:  GET /api/tasks is called
THEN:  it returns the list of tasks from the manager

GIVEN: the DOM in the frontend
WHEN:  the tasks tab is opened
THEN:  a container for the list and a nav link exist

GIVEN: the JS logic
WHEN:  the UI renders
THEN:  a render function for tasks exists and handles the JSON status
"""
import pytest
from pathlib import Path

# Perspective 1: API endpoint

class TestTasksApiPerspective:
    """GIVEN tasks API, WHEN fetched, THEN returns JSON task list."""

    def test_given_app_when_get_tasks_then_returns_json(self):
        """
        GIVEN: the FastAPI TestClient
        WHEN:  GET /api/tasks
        THEN:  a 200 response and a JSON list
        """
        from fastapi.testclient import TestClient
        from server.main import app

        with TestClient(app) as client:
            res = client.get("/api/tasks")
            assert res.status_code == 200
            data = res.json()
            assert isinstance(data, list)


# Perspective 2: HTML DOM

class TestTasksHtmlPerspective:
    """GIVEN index.html, WHEN parsed, THEN task tab and container exist."""

    @pytest.mark.skip(reason="Legacy PWA migrated to React+Vite; source files (app/src/index.html, main.js, i18n.js, service-worker.js) and legacy UI features (export button, mode toggle, tasks tab) were removed/refactored. Test references stale paths.")
    def test_given_html_when_parsed_then_task_tab_exists(self):
        """
        GIVEN: index.html
        WHEN:  searched for the task elements
        THEN:  the nav item and the content tab are present
        """
        html = (Path(__file__).parent.parent / "app" / "src" / "index.html").read_text()

        # Perspective 1: the navigation link
        assert 'data-target="view-tasks"' in html or 'href="#tasks"' in html or 'id="nav-tasks"' in html or 'nav.tasks' in html

        # Perspective 2: the tab content area
        assert 'id="view-tasks"' in html

        # Perspective 3: the list for tasks
        assert 'id="tasks-list"' in html or 'id="task-list"' in html


# Perspective 3: JS rendering

class TestTasksJsPerspective:
    """GIVEN main.js, WHEN parsed, THEN task render logic exists."""
    @pytest.mark.skip(reason="Legacy PWA migrated to React+Vite; source files (app/src/index.html, main.js, i18n.js, service-worker.js) and legacy UI features (export button, mode toggle, tasks tab) were removed/refactored. Test references stale paths.")

    def test_given_js_when_parsed_then_render_logic_exists(self):
        """
        GIVEN: main.js
        WHEN:  searched for the task render code
        THEN:  code for loadTasks and the checkbox binding exists
        """
        js = (Path(__file__).parent.parent / "app" / "src" / "main.js").read_text()
        js_tasks = (Path(__file__).parent.parent / "app" / "src" / "modules" / "tasks.js").read_text()
        js_combined = js + js_tasks

        # Perspective 1: API call
        assert 'fetch(`${API}/tasks`)' in js_combined or "fetch(API + '/tasks')" in js_combined

        # Perspective 2: render function
        assert 'renderTasks' in js_combined or 'loadTasks' in js_combined

        # Perspective 3: Checkbox / Status toggle handler
        assert 'toggleTask' in js_combined or 'updateTask' in js_combined or 'status=' in js_combined
