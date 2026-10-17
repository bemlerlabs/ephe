"""
Chat export — GWT, 3 levels deep.

GIVEN: the current chat history
WHEN:  the export button is clicked
THEN:  the messages download, formatted as Markdown.

GIVEN: the backend
WHEN:  a POST request with JSON messages arrives at /api/export
THEN:  the backend returns the formatted Markdown string.

GIVEN: the UI
WHEN:  the export button is looked for in the chat header
THEN:  a valid export button exists.
"""
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

# Perspective 1: Markdown Formatting

class TestExportFormattingPerspective:
    """GIVEN a list of messages, WHEN formatted, THEN markdown structure is correct."""

    def test_given_messages_when_formatted_then_markdown_is_correct(self):
        """
        GIVEN: a list of dictionaries with 'role' and 'content'
        WHEN:  the formatting function is called
        THEN:  the return value is valid Markdown
        """
        from core.export import format_chat_markdown

        messages = [
            {"role": "user", "content": "Hallo Ephe"},
            {"role": "assistant", "content": "Hallo Mensch!"}
        ]

        md = format_chat_markdown(messages)

        assert "## Chat Export" in md
        assert "**Nutzer:**" in md
        assert "Hallo Ephe" in md
        assert "**Ephe:**" in md
        assert "Hallo Mensch!" in md


# Perspective 2: API endpoint

class TestExportApiPerspective:
    """GIVEN export API, WHEN posted with messages, THEN returns file payload."""

    def test_given_app_when_post_export_then_returns_markdown(self):
        """
        GIVEN: the FastAPI TestClient and a payload with chat history
        WHEN:  POST /api/export
        THEN:  returns 200 and content type text/markdown
        """
        from server.main import app

        with TestClient(app) as client:
            payload = {
                "messages": [
                    {"role": "user", "content": "Test"}
                ]
            }
            res = client.post("/api/export", json=payload)

            assert res.status_code == 200
            assert "text/markdown" in res.headers.get("content-type", "")
            assert "Test" in res.text


# Perspective 3: UI button

class TestExportUiPerspective:
    """GIVEN index.html, WHEN parsed, THEN export button exists."""

    @pytest.mark.skip(reason="Legacy PWA migrated to React+Vite; source files (app/src/index.html, main.js, i18n.js, service-worker.js) and legacy UI features (export button, mode toggle, tasks tab) were removed/refactored. Test references stale paths.")
    def test_given_html_when_parsed_then_export_button_exists(self):
        """
        GIVEN: index.html
        WHEN:  the export element is looked for
        THEN:  a button with matching ID and event binding exists
        """
        html = (Path(__file__).parent.parent / "app" / "src" / "index.html").read_text()

        # Perspective: button in the chat header
        assert 'id="btn-export-chat"' in html or 'Export' in html
    @pytest.mark.skip(reason="Legacy PWA migrated to React+Vite; source files (app/src/index.html, main.js, i18n.js, service-worker.js) and legacy UI features (export button, mode toggle, tasks tab) were removed/refactored. Test references stale paths.")

    def test_given_js_when_parsed_then_export_logic_exists(self):
        """
        GIVEN: main.js
        WHEN:  the download logic is looked for
        THEN:  fetch('/api/export') and Blob creation exist
        """
        js = (Path(__file__).parent.parent / "app" / "src" / "main.js").read_text()
        js_modules = js
        for f in (Path(__file__).parent.parent / "app" / "src" / "modules").glob("*.js"):
            js_modules += f.read_text()

        assert 'exportChat' in js_modules
        assert 'Blob' in js_modules
        assert 'createObjectURL' in js_modules
