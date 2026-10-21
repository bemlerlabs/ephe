"""Runtime P0 invariants: the secret boundary, call identity, cancel and the ledger.

SEC-1 — a protected root is refused, a credential-shaped name needs a human, and the
redactor is the filter every sink passes; TL-1/TL-2 — a call id names turn, round and
position, and a cancelled run kills its process group; OB-1/RL-1 — the ledger is
content-free, survives a kill and projects the five phases; LC-1 — health names the
process and the contract.
"""
from __future__ import annotations

import asyncio
import contextvars
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from core.path_guard import deny_paths, denied
from core.redact import redact, redact_deep
from core.tools._shell_proc import _exec_sync
from core.tools.cancel_scope import active_groups, enter_run, kill_run

SECRETS = [
    "sk-proj-abcdefghijklmnop1234567890",
    "sk-ant-api03-abcdefghijklmnop1234567890",
    "sk-or-v1-abcdefghijklmnop1234567890",
    "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
    "gho_abcdefghijklmnopqrstuvwxyz0123456789",
    "ghu_abcdefghijklmnopqrstuvwxyz0123456789",
    "github_pat_11ABCDEFG0123456789_abcdefghijklmnop",
    "xoxb-123456789012-abcdefghijkl",
    "xoxp-123456789012-abcdefghijkl",
    "hf_abcdefghijklmnopqrstuvwxyz0123456789",
    "AKIAIOSFODNN7EXAMPLE",
    "AIzaSyA1234567890abcdefghijklmnopqrstuvwxyz",
    "glpat-abcdefghijklmnopqrst",
    "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9zzz",
    "https://x.test/v1?token=supersecretvalue",
    'api_key = "abcdef1234567890"',
    "password: 'hunter2hunter2'",
    "EPHE_OPENAI_COMPAT_API_KEY=abcdef1234567890",
    "EPHE_ACCESS_TOKEN=abcdef1234567890",
    "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n-----END RSA PRIVATE KEY-----",
]


@pytest.mark.parametrize("secret", SECRETS)
def test_the_redactor_masks_every_family(secret: str) -> None:
    masked = redact(secret)
    assert "***" in masked, masked
    # The tail of a masked literal must not survive; the prefix is kept for triage.
    assert secret[-12:] not in masked or "PRIVATE KEY" in secret, masked


def test_the_redactor_pairs_each_private_key_block_once() -> None:
    two = (
        "-----BEGIN RSA PRIVATE KEY-----\nfirst-body\n-----END RSA PRIVATE KEY-----\n"
        "-----BEGIN OPENSSH PRIVATE KEY-----\nsecond-body\n-----END OPENSSH PRIVATE KEY-----"
    )
    masked = redact(two)
    assert "first-body" not in masked and "second-body" not in masked
    assert masked.count("***") == 2
    # A header without a footer is not a block, and the redactor must not invent one.
    unclosed = "-----BEGIN RSA PRIVATE KEY-----\nno footer"
    assert redact(unclosed) == unclosed


def test_the_redactor_walks_nested_event_payloads() -> None:
    event = {"type": "tool_done", "result": {"text": SECRETS[3], "rows": [SECRETS[14]]}}
    masked = redact_deep(event)
    assert SECRETS[3] not in str(masked)
    assert "supersecretvalue" not in str(masked)


def test_a_credential_corpus_never_reaches_a_sink(tmp_path: Path) -> None:
    files = {
        ".env": "OPENAI_API_KEY=sk-proj-abcdefghijklmnop1234567890",
        "id_rsa": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA\n-----END RSA PRIVATE KEY-----",
        "credentials.json": '{"token": "ghp_abcdefghijklmnopqrstuvwxyz0123456789"}',
        "config.pem": "sk-ant-api03-abcdefghijklmnop1234567890",
        "cloud.yaml": "key: AKIAIOSFODNN7EXAMPLE",
        "maps.env.local": "AIzaSyA1234567890abcdefghijklmnopqrstuvwxyz",
        "slack.txt": "xoxb-123456789012-abcdefghijkl",
        "hf.txt": "hf_abcdefghijklmnopqrstuvwxyz0123456789",
        "gitlab.txt": "glpat-abcdefghijklmnopqrst",
        "bearer.txt": "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9zzz",
        "query.txt": "https://x.test/v1?token=supersecretvalue",
        "app.conf": 'password = "hunter2hunter2"',
    }
    assert len(files) == 12
    corpus = "\n".join(files.values())
    masked = redact(corpus)
    for raw in files.values():
        if "PRIVATE KEY" in raw:
            assert "MIIEowIBAAKCAQEA" not in masked
            continue
        token = raw.split("=")[-1].split(": ")[-1].strip(" \"'")
        assert token not in masked, f"{token!r} survived redaction"


def test_protected_roots_are_refused_and_ordinary_paths_pass() -> None:
    assert denied("~/.ssh/id_rsa")
    assert denied("~/.ephe/audit.log")
    assert denied("~/.aws/credentials")
    assert not denied("/tmp/ephe-public-beta8/README.md")
    assert deny_paths({"path": "~/.ssh/config"}) == ["~/.ssh/config"]
    assert deny_paths({"command": "ls -la"}) == []


def test_a_secret_shaped_name_needs_an_approval_even_on_a_read_tool(tmp_path: Path) -> None:
    from core.tools.chat_gate import confirm_for_chat

    secret = tmp_path / ".env"
    secret.write_text("X=1", encoding="utf-8")
    asked: list[str] = []

    async def approve(name: str, args: dict) -> bool:
        asked.append(name)
        return True

    allowed, denial = asyncio.run(
        confirm_for_chat("read_file", {"path": str(secret)}, on_confirm=approve)
    )
    assert allowed and not denial
    assert asked == ["read_file"], "a read-only tool was not sent to the dialog"


def test_a_protected_root_is_denied_without_asking_a_human() -> None:
    from core.tools.chat_gate import confirm_for_chat

    asked: list[str] = []

    async def approve(name: str, args: dict) -> bool:
        asked.append(name)
        return True

    allowed, denial = asyncio.run(
        confirm_for_chat("read_file", {"path": "~/.ssh/id_rsa"}, on_confirm=approve)
    )
    assert not allowed
    assert "protected root" in denial
    assert asked == [], "the dialog must not be shown for a path no answer can open"


def test_the_call_id_names_turn_round_and_position() -> None:
    from core.chat_detect import _call_id

    first = _call_id("turn-abcdef", 0, 1)
    second = _call_id("turn-abcdef", 0, 2)
    assert first == "turn-abc-r1-0"
    assert second == "turn-abc-r2-0"
    assert first != second


@pytest.mark.skipif(not hasattr(Path("/"), "exists"), reason="posix only")
def test_a_cancelled_run_kills_its_process_group() -> None:
    run_id = f"cancel-{time.time_ns()}"
    enter_run(run_id)
    ctx = contextvars.copy_context()
    done = threading.Event()

    def run_sleep() -> None:
        try:
            _exec_sync(["sleep", "30"], None, False)
        except Exception:
            pass
        finally:
            done.set()

    thread = threading.Thread(target=ctx.run, args=(run_sleep,), daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not active_groups(run_id) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert active_groups(run_id), "the child was not registered under its run"
    assert kill_run(run_id) >= 1
    assert done.wait(5), "the process group survived the cancel"
    thread.join(1)


def test_the_ledger_is_content_free_and_survives_a_kill(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    from core.run import ledger

    run = ledger.start("run-p0", "req-p0")
    ledger.record_event(
        {"type": "tool_start", "tool": "read_file", "call_id": "c1", "args": {"path": "/secret/path"}}
    )
    ledger.record_event({"type": "chunk", "data": "raw answer text"})
    rows = ledger.read_run("run-p0")
    assert rows, "the start line must exist"
    text = (tmp_path / "run" / "run-p0.jsonl").read_text(encoding="utf-8")
    assert "raw answer text" not in text
    assert "/secret/path" not in text, "raw tool arguments are not ledger content"
    assert rows[0]["run_id"] == "run-p0" and rows[0]["request_id"] == "req-p0"
    assert rows[0]["seq"] == 1 and rows[0]["schema"] == ledger.SCHEMA
    assert any(row["kind"] == "tool_start" for row in rows)
    snapshot = ledger.snapshot("run-p0")
    assert set(snapshot["phases"]) == {"Now", "Waiting", "Changed", "Result", "Next"}
    assert snapshot["phases"]["Now"] is not None
    assert run.seq == len(rows)


def test_the_fleet_row_carries_the_ledger_view(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    from core import fleet
    from core.run import ledger

    ledger.start("run-view", "req")
    ledger.record_event({"type": "activity", "cmd": "Tool round 1", "status": "running"})
    row = fleet._row(
        run_id="run-view",
        kind="workspace",
        agent="ephe",
        state="running",
        running_for_seconds=1,
    )
    assert row["ledger"] is not None
    assert row["ledger"]["run_id"] == "run-view"


def test_health_names_the_process_and_the_contract(monkeypatch) -> None:
    from server.routes import health as health_mod

    async def fake_probe(base_url: str, model: str):
        return True, "engine reachable", [model], "ok", False

    monkeypatch.setattr(health_mod, "_quick_engine_status", fake_probe)
    monkeypatch.setattr(
        health_mod,
        "get_active_provider",
        lambda: SimpleNamespace(
            provider="openai_compatible",
            model="m",
            base_url="http://127.0.0.1:1",
            api_key_configured=False,
            offline_capable=False,
            requires_internet=True,
        ),
    )
    app = FastAPI()
    app.include_router(health_mod.router, prefix="/api")
    body = TestClient(app).get("/api/health").json()
    assert body["version"]
    assert body["instance_id"]
    assert body["pid"] > 0
    assert Path(body["root"]).resolve() == Path(__file__).resolve().parents[1]
    assert body["api_contract"] >= 1
    assert "owner" in body


def test_a_late_approval_is_gone(monkeypatch) -> None:
    from server.routes import chat

    token = "late-token"
    chat._active_sandbox_events[token] = {
        "event": asyncio.Event(),
        "approved": False,
        "requested_at": time.time() - chat.APPROVAL_TTL_SECONDS - 5,
    }
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chat.approve_sandbox(chat.ApproveRequest(token=token, approved=True)))
    assert exc.value.status_code == 410
    assert token in chat._expired_sandbox_tokens
    assert token not in chat._active_sandbox_events
