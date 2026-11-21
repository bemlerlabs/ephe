import pytest
from fastapi.testclient import TestClient
from server.main import create_app

# W16: the shell route demands the XHR marker header (CSRF guard).
XHR_HEADERS = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture
def client():
    return TestClient(create_app())


def test_shell_whitelisted_command_runs(client):
    # 'echo' is in ALLOWED_COMMANDS → a real run through run_shell.
    r = client.post("/api/shell", json={"command": "echo hallo-ephe", "approved": True}, headers=XHR_HEADERS)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ok"] is True
    assert "hallo-ephe" in data["output"]


def test_shell_non_whitelisted_blocked(client):
    # 'rm' is NOT in ALLOWED_COMMANDS → run_shell refuses for safety reasons.
    r = client.post("/api/shell", json={"command": "rm -rf /tmp/xyz", "approved": True}, headers=XHR_HEADERS)
    assert r.status_code == 200  # refused, but no crash
    data = r.json()
    assert data["ok"] is False
    assert "Security" in data["output"]


def test_shell_empty_command(client):
    r = client.post("/api/shell", json={"command": "   ", "approved": True}, headers=XHR_HEADERS)
    assert r.status_code == 200
    assert r.json()["ok"] is False
