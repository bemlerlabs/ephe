"""Four /api operations existed only as a name in the freeze list — nothing ever called them.

`tests/test_w3_68_api_contract_frozen.py` proves the OpenAPI document still carries every operation,
which is a statement about the document. A route can satisfy it while its handler has never been
entered: measured over the 872 files under `tests/`, four paths were mentioned nowhere except that
freeze list, and no test called their handler either — `GET /api/audit/usage`,
`POST /api/channels/discord/stop`, `GET /api/market/updates` and `POST /api/secrets/remove`.

The gap was not cosmetic. `GET /api/market/updates` filtered its error rows with
`row["source"] == BUNDLED_ID`, comparing a source *title* to a source *id*, so a bundled catalog that
could not be read answered `{"updates": [], "errors": []}` — "nothing to install" where the truth was
"the catalog is broken". `core/marketplace_inventory.updates()` now carries `source_id` beside the
display title and the route filters on it; the third class below pins both halves.

Each test here goes through `TestClient(create_app())`, so the middleware, the router and the response
model are on the path, and the assertion is about what a caller receives.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

import core.audit_log as audit_log
import core.marketplace_inventory as marketplace_inventory
import core.marketplace_service as marketplace_service
import core.marketplace_sources as marketplace_sources
import core.secret_store as secret_store
import server.routes.channels as channels
from server.main import create_app

AJAX = {"X-Requested-With": "XMLHttpRequest"}


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client
    channels.reset_for_tests()


def _exec_line(tool: str, *, status: str = "ok", decision: str = "approved",
               ts: str = "2026-01-04T09:00:00+00:00") -> str:
    return json.dumps({
        "ts": ts, "kind": "tool_exec", "tool": tool, "turn_id": "t-1",
        "args": "", "args_hash": f"h-{tool}", "decision": decision,
        "status": status, "duration_ms": 12.0,
    }) + "\n"


class TestAuditUsage:
    """`GET /api/audit/usage` — the "most used" facts, and the window they stand on."""

    @pytest.fixture
    def log(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        path = tmp_path / "audit.log"
        monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", path)
        return path

    def test_the_ranking_names_the_tools_that_ran_and_says_how_many_calls_stood_behind_it(
        self, client: TestClient, log: Path
    ) -> None:
        log.write_text(
            _exec_line("shell")
            + _exec_line("shell")
            + _exec_line("shell", status="error")
            + _exec_line("read_file")
            + _exec_line("read_file", decision="blocked", status="error")
            + json.dumps({"ts": "2026-01-04T09:30:00+00:00", "kind": "turn", "tool": "chat",
                          "status": "ok"}) + "\n",
            encoding="utf-8",
        )

        body = client.get("/api/audit/usage").json()

        assert [row["tool"] for row in body["tools"]] == ["shell", "read_file"]
        shell, read_file = body["tools"]
        assert (shell["calls"], shell["ok"], shell["errors"]) == (3, 2, 1)
        assert (read_file["calls"], read_file["errors"], read_file["blocked"]) == (2, 1, 1)
        assert body["population"] == 5, "a turn line is not a call and must not join the population"
        assert body["window"] == 500

    def test_top_is_clamped_inside_the_range_a_surface_can_draw(
        self, client: TestClient, log: Path
    ) -> None:
        log.write_text("".join(
            _exec_line(f"tool{i:02d}") for i in range(30)
        ), encoding="utf-8")

        widest = client.get("/api/audit/usage", params={"top": 1000}).json()
        narrowest = client.get("/api/audit/usage", params={"top": 0}).json()
        negative = client.get("/api/audit/usage", params={"top": -5}).json()

        assert len(widest["tools"]) == 24, "the route caps the list at what a panel holds"
        assert widest["tools"][0]["tool"] == "tool00", "ties rank by name, so the cut is reproducible"
        assert [row["tool"] for row in narrowest["tools"]] == ["tool00"]
        assert [row["tool"] for row in negative["tools"]] == ["tool00"]

    def test_a_top_that_is_not_a_number_is_refused_before_the_log_is_read(
        self, client: TestClient, log: Path
    ) -> None:
        log.write_text(_exec_line("shell"), encoding="utf-8")

        response = client.get("/api/audit/usage", params={"top": "all"})

        assert response.status_code == 422


class TestDiscordStop:
    """`POST /api/channels/discord/stop` — the admin button that has to leave nothing running."""

    class _Task:
        def __init__(self) -> None:
            self.cancelled = False

        def done(self) -> bool:
            return False

        def cancel(self) -> None:
            self.cancelled = True

        def __await__(self):
            """A stopped worker raises this out of the await.

            The handler lists `CancelledError` by name because it is a BaseException, and
            `except Exception` alone would walk past it.
            """
            raise asyncio.CancelledError()
            yield

    class _Runner:
        def __init__(self) -> None:
            self.stopped = 0

        def stop(self) -> None:
            self.stopped += 1

    def test_stopping_reports_stopped_and_leaves_no_task_or_runner_for_the_next_start(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        task, runner, rows = self._Task(), self._Runner(), []
        monkeypatch.setattr(channels, "_discord_task", task)
        monkeypatch.setattr(channels, "_discord_runner", runner)
        monkeypatch.setattr(channels, "audit_event",
                            lambda kind, **kw: rows.append({"kind": kind, **kw}))

        response = client.post("/api/channels/discord/stop")

        assert response.status_code == 200
        assert response.json() == {"running": False}
        assert runner.stopped == 1 and task.cancelled is True
        assert channels._discord_task is None, "a stopped channel must not look resumable"
        assert rows == [{
            "kind": "channel", "tool": "discord_admin", "decision": "allow",
            "status": "stopped", "detail": "discord_channel_stopped",
        }], "the stop is only auditable through this row"

    def test_stopping_a_channel_that_never_started_is_a_statement_not_an_error(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(channels, "_discord_task", None)
        monkeypatch.setattr(channels, "_discord_runner", None)

        response = client.post("/api/channels/discord/stop")

        assert response.status_code == 200
        assert response.json() == {"running": False}


class TestMarketUpdates:
    """`GET /api/market/updates` — the installed view answers for the bundled catalog only."""

    @staticmethod
    def _payload() -> dict[str, list[dict[str, Any]]]:
        return {
            "updates": [
                {"name": "from-bundled", "version": "1.1.0", "installed_version": "1.0.0",
                 "trust": "bundled", "source_id": marketplace_sources.BUNDLED_ID,
                 "source_title": "Ephe bundled"},
                {"name": "from-stranger", "version": "2.0.0", "installed_version": "1.0.0",
                 "trust": "verified", "source_id": "community", "source_title": "Community"},
            ],
            "errors": [
                {"source": "Ephe bundled", "source_id": marketplace_sources.BUNDLED_ID,
                 "error": "index_unreadable"},
                {"source": "Community", "source_id": "community", "error": "http_404"},
            ],
        }

    def test_only_the_bundled_catalog_answers_for_this_install(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(marketplace_service, "updates", self._payload)

        body = client.get("/api/market/updates").json()

        assert [row["name"] for row in body["updates"]] == ["from-bundled"]
        assert [row["source"] for row in body["errors"]] == ["Ephe bundled"]

    def test_a_bundled_catalog_that_cannot_be_read_is_reported_as_broken_not_as_empty(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The defect this file was written for: the filter compared a title to an id.

        With `row["source"] == BUNDLED_ID` no error row ever matched — `"Ephe bundled"` is not
        `"bundled"` — so the endpoint promised `{"updates": [], "errors": []}` for a catalog that
        failed to load, and a page reading it showed "no updates" over a broken install.
        """
        broken = self._payload()
        broken["updates"] = []
        monkeypatch.setattr(marketplace_service, "updates", lambda: broken)

        body = client.get("/api/market/updates").json()

        assert body["updates"] == []
        assert body["errors"], "a catalog that failed to read is not a catalog with nothing to install"
        assert body["errors"][0]["error"] == "index_unreadable"
        assert body["errors"][0]["source"] == "Ephe bundled", "the page still shows the title"

    def test_the_inventory_names_the_source_id_behind_every_error_row(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The route filter is only honest while the inventory carries the id it filters on."""
        sources = [marketplace_sources.bundled_source(),
                   {"id": "community", "title": "Community", "kind": "remote",
                    "url": "https://example.invalid/index.json", "trust": "verified",
                    "removable": True}]
        monkeypatch.setattr(marketplace_inventory, "installed", lambda: {"plugins": []})
        monkeypatch.setattr(marketplace_sources, "load_sources", lambda: {"sources": sources})
        monkeypatch.setattr(
            marketplace_sources, "read_source",
            lambda source: ({"index": {"plugins": {}}} if source["id"] == "bundled"
                            else {"error": "offline"}),
        )

        errors = marketplace_inventory.updates()["errors"]

        assert errors == [{"source": "Community", "source_id": "community", "error": "offline"}]


class TestSecretRemove:
    """`POST /api/secrets/remove` — presence may be answered, a value never."""

    @pytest.fixture
    def vault(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        directory = tmp_path / "secrets"
        monkeypatch.setattr(secret_store, "secrets_dir", lambda: directory)
        monkeypatch.setattr(secret_store, "_store_keyring", lambda name, value: False)
        monkeypatch.setattr(secret_store, "_load_keyring", lambda name: None)
        monkeypatch.setattr(secret_store, "_delete_keyring", lambda name: None)
        return directory

    def test_a_removal_that_does_not_arrive_as_an_ajax_call_never_reaches_the_vault(
        self, client: TestClient, vault: Path
    ) -> None:
        """A form that is not this app's own call cannot delete a vault entry.

        The router carries `X-Requested-With: XMLHttpRequest` as a dependency, which a cross-site
        form cannot set; `LocalRequestGuardMiddleware` is the layer in front of it. The vault keeps
        the entry and the value stays out of the answer either way.
        """
        secret_store.put("OPENAI_API_KEY", "sk-test-value")

        response = client.post("/api/secrets/remove", json={"name": "OPENAI_API_KEY"})

        assert response.status_code == 403
        body = response.json()["error"]
        assert body["code"] == "auth_error"
        assert body["detail"]["code"] in {"unauthorized", "untrusted_host"}, \
            "either guard may answer first; both refuse a request that is not this app's own call"
        assert "sk-test-value" not in response.text
        assert (vault / "OPENAI_API_KEY").is_file(), "a refused request must not have deleted"

    def test_the_name_is_forgotten_and_the_value_never_appears_in_the_answer(
        self, client: TestClient, vault: Path
    ) -> None:
        secret_store.put("OPENAI_API_KEY", "sk-test-value")
        assert (vault / "OPENAI_API_KEY").is_file()

        response = client.post("/api/secrets/remove", json={"name": "OPENAI_API_KEY"}, headers=AJAX)

        assert response.status_code == 200
        assert response.json() == {"name": "OPENAI_API_KEY", "present": False, "mode": ""}
        assert not (vault / "OPENAI_API_KEY").exists()
        assert "sk-test-value" not in response.text

    def test_a_name_that_was_never_stored_is_answered_absent_rather_than_missing(
        self, client: TestClient, vault: Path
    ) -> None:
        for name in ("NOT_STORED", "lowercase-is-not-a-name", ""):
            response = client.post("/api/secrets/remove", json={"name": name}, headers=AJAX)
            assert response.status_code == 200, name
            assert response.json()["present"] is False
