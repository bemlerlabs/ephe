"""One HTTP leg of the WG-47 restart proof, run in its own interpreter.

WG-47 asks whether a memory a running Ephe wrote is still readable after Ephe
restarts. A restart is a process boundary, so the store and the read happen in
separate interpreters: this file is the whole program each of them runs, and the
parent test starts it twice against one EPHE_MEMORY_DIR.

Usage, from the repo root with the checkout on PYTHONPATH:

    python tests/e2e/memory_restart_leg.py store "<text>"
    python tests/e2e/memory_restart_leg.py read  "<query>"

Only the route layer of the shipped app is exercised here; the engine is never
built, so the leg needs no model and no network. One JSON object goes to stdout.
"""
from __future__ import annotations

import json
import sys

from fastapi.testclient import TestClient

from server.main import create_app


def _store(client: TestClient, text: str) -> dict:
    response = client.post(
        "/api/memory/store",
        json={"text": text, "metadata": {"source": "wg47-e2e"}},
    )
    return {"status": response.status_code, "body": response.json()}


def _read(client: TestClient, query: str) -> dict:
    listing = client.get("/api/memory/list").json()
    search = client.get("/api/memory/search", params={"q": query, "top_k": 5}).json()
    stats = client.get("/api/memory/stats").json()
    return {
        "entries": listing.get("entries"),
        "total": listing.get("total"),
        "stats_total": stats.get("total"),
        "results": search.get("results"),
    }


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "read"
    payload = argv[2] if len(argv) > 2 else ""
    with TestClient(create_app()) as client:
        result = _store(client, payload) if mode == "store" else _read(client, payload)
    print(json.dumps({"mode": mode, "result": result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
