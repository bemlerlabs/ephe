"""Latency budgets taken out of a feature file and run in the serial segment.

`pytest -n auto` shares the cores with every other worker, so a wall-clock budget in the
parallel leg measures the machine. CI run 37974211156 (commit 0054c641, 2026-10-09, job
`pytest (ubuntu-latest, py3.11)` on `the lab runner-3`) took
`tests/test_r25_session_search.py::test_search_route_returns_results_and_elapsed` to
324.7 ms against a 200 ms budget while the assertions on the same response body stayed
green. The cause is contention, so the fix is the segment: the budget moves, its number
stays where `docs/LATENCY_BUDGETS.md` put it.

`.github/workflows/tests.yml` runs this file inside "Run timing gates (serial)" and keeps
it out of the `-n auto` leg. `tests/test_timing_assertion_guard.py` fails when a new
upper-bound wall-clock assertion appears in the parallel set.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import core.multi_session as ms

# docs/LATENCY_BUDGETS.md, unchanged by the move.
SEARCH_ROUTE_BUDGET_MS = 200.0


@pytest.fixture(autouse=True)
def _hermetic_search_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The same isolation `test_r25_session_search.py` gives the route tests."""
    sessions = tmp_path / "sessions"
    sessions.mkdir()
    monkeypatch.setattr(ms, "SESSIONS_DIR", sessions)
    monkeypatch.setattr(ms, "REGISTRY_FILE", sessions / "registry.json")
    monkeypatch.setenv("EPHE_SEARCH_DB", str(tmp_path / "search.db"))
    for key, value in {
        "EPHE_MEMORY_DIR": tmp_path / "chroma_db",
        "EPHE_PROFILE_PATH": tmp_path / "user_profile.json",
        "EPHE_CORRECTIONS_PATH": tmp_path / "corrections.md",
        "EPHE_FEEDBACK_DIR": tmp_path,
        "EPHE_SKILLS_DIR": tmp_path / "skills",
    }.items():
        monkeypatch.setenv(key, str(value))


def test_search_route_cold_call_within_budget() -> None:
    """Budget: the first GET /api/search answers inside SEARCH_ROUTE_BUDGET_MS.

    Cold on purpose: that call also builds the FTS index, and the build is time the user
    waits for. Measured 2026-10-09 on the owner's 10-core Mac at 2.4 ms with the whole
    `-n auto` leg running beside the segment (load ~15); the CI assertion this test
    replaces read 324.7 ms inside the parallel leg of run 37974211156.
    """
    from fastapi.testclient import TestClient

    from server.main import create_app

    sid = ms.create_session("Budget-Route")["id"]
    ms.save_messages(  # type: ignore[arg-type]
        sid,
        [
            {"role": "user", "content": "The COUNTERSIGN sits in this message"},
            {"role": "assistant", "content": "answer"},
        ],
    )

    with TestClient(create_app()) as client:
        body = client.get("/api/search", params={"q": "COUNTERSIGN"}).json()

    assert body["total"] >= 1, body
    print(f"\n  [search route] elapsed_ms={float(body['elapsed_ms']):.1f} "
          f"(budget {SEARCH_ROUTE_BUDGET_MS:.0f} ms)")
    assert body["elapsed_ms"] < SEARCH_ROUTE_BUDGET_MS, (
        f"search route took {body['elapsed_ms']:.1f} ms, budget {SEARCH_ROUTE_BUDGET_MS:.0f} ms"
    )
