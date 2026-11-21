"""Every published `/api/*` path is exercised by a test, not only named in the freeze list.

`tests/test_w3_68_api_contract_frozen.py` compares the OpenAPI document against a frozen list, so a
route that exists stays green forever — even one whose handler no test has ever entered. On
2026-11-17 that was true of four paths: `GET /api/audit/usage`, `POST /api/channels/discord/stop`,
`GET /api/market/updates` and `POST /api/secrets/remove`. One of them carried a live defect because
of it (see `tests/test_routes_nobody_called.py`).

A path counts as exercised when its string is the argument of an HTTP call under `tests/`, or when
its handler's name is used as a call — a route test may drive the handler directly. Both halves are
name checks in the same sense as the surface guard in `tests/test_surface_of_routes.py`: neither can
tell an assertion from an unanswered call. What they do catch is the case that hid here: a route
known only to the contract freeze list, where the quoted path sits beside no client.

`KNOWN_GAPS` is where a path goes when it is deliberately unexercised. An entry has to name the
decision it waits on, and the control test below proves a path really does land in the gap list when
nothing calls it — the failure mode of a guard that reports nothing because it sees nothing.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from server.main import create_app

TESTS = Path(__file__).resolve().parent

#: path -> the decision an exercise would have to wait on. Empty is the intended state.
KNOWN_GAPS: dict[str, str] = {}

#: A file that never opens a client cannot exercise a route over HTTP.
CALL_OPEN = re.compile(r"TestClient\(|AsyncClient\(|httpx\.|\.(get|post|put|patch|delete|request)\(")

#: A URL a test wrote down. The string has to start at the path or at an interpolated base, which is
#: how a contract entry (`"GET /api/audit/usage"`) stays out while `f"{BASE}/api/x"` stays in. To the
#: end of the line, so a URL assembled from pieces keeps all of its literal segments and an f-string
#: subscript with its own quotes survives.
URL_LITERAL = re.compile(r"[\"']((?:/api/|\{)[^\n]*)")

#: A handler reached directly rather than over HTTP counts, but only as a call.
HANDLER_CALL = re.compile(r"\b([a-z_][a-z0-9_]{3,})\s*\(")


def _braced(text: str) -> str:
    """`{sid}` in a test's f-string and `{session_id}` on the route are the same hole."""
    return re.sub(r"\{[^{}]*\}", "{}", text)


def _declared_api_paths(app) -> dict[str, set[str]]:
    """`path -> handler names`, with included routers flattened.

    `include_router` keeps a family behind `_IncludedRouter`, whose own `routes` is empty while
    `original_router.routes` carry the relative paths, so the prefix has to be joined here — the same
    walk `server/main.py` does to build the 405 hints.
    """
    found: dict[str, set[str]] = {}

    def walk(routes, prefix: str) -> None:
        for route in routes:
            context = getattr(route, "include_context", None)
            inner = getattr(route, "original_router", None)
            if context is not None and inner is not None:
                walk(inner.routes, prefix + (getattr(context, "prefix", "") or ""))
                continue
            path, methods = getattr(route, "path", None), getattr(route, "methods", None)
            if not path or not methods:
                continue
            if not (prefix + path).startswith("/api/"):
                continue
            handler = getattr(getattr(route, "endpoint", None), "__name__", None)
            found.setdefault(prefix + path, set()).add(handler or "")

    walk(app.router.routes, "")
    return found


def _gaps(declared: dict[str, set[str]], corpus: dict[str, str]) -> list[str]:
    """Declared paths that no test exercises, sorted and without the accepted ones.

    Two things count as exercise, and both are collected before the loop rather than searched per
    path: a URL written down by a file that opens a client, and a handler whose name is used as a
    call. The distinction from a plain mention is the whole point —
    `tests/test_w3_68_api_contract_frozen.py` holds a quoted `"GET /api/audit/usage"` for every route
    and opens no client, so a rule that accepted a mention anywhere would report full coverage while
    four handlers stayed unentered. A regex that has to fail also scans the whole suite, which cost
    15 s; the two blobs and the name set bring this back to about a second.
    """
    pieces: list[str] = []
    for name, text in corpus.items():
        if name == Path(__file__).name or not CALL_OPEN.search(text):
            continue
        pieces.extend(URL_LITERAL.findall(text))
    urls = "\n".join(_braced(piece) for piece in pieces)
    names = frozenset(HANDLER_CALL.findall("\n".join(corpus.values())))
    missing: list[str] = []
    for path, handlers in declared.items():
        if path in KNOWN_GAPS:
            continue
        trailing_param = path.endswith("}")
        segments = [seg for seg in re.split(r"\{[^}]*\}", path) if seg]
        # Within one line only: each piece is one line of one caller file, so a path's segments have
        # to be found together there and cannot be assembled out of two unrelated files.
        needle = "[^\n]*".join(re.escape(seg) for seg in segments)
        if not trailing_param:
            # `/api/docs` must not be read as a hit on `/api/documents`.
            needle += r"(?![\w-])"
        if re.search(needle, urls) is not None or handlers & names:
            continue
        missing.append(path)
    return sorted(missing)


def test_the_live_app_publishes_the_api_surface_this_guard_is_about() -> None:
    """A guard over an empty or partial route list would pass by seeing nothing."""
    declared = _declared_api_paths(create_app())
    assert len(declared) > 200, f"only {len(declared)} /api paths enumerated"
    assert "/api/health" in declared and "/api/sessions" in declared, sorted(declared)[:3]


def test_the_classifier_finds_the_gap_it_claims_to_find() -> None:
    """The controls, so a guard that sees nothing cannot read as full coverage.

    The second case is the one this file exists for. That file does open a client, for another route,
    and the frozen entry sitting next to it still must not read as coverage: mentioning a path is not
    calling it.
    """
    declared = {"/api/never-called/{thing}/trash": {"never_called"}}
    prose = {"tests/notes.py": "the route /api/never-called/{thing}/trash exists"}
    assert _gaps(declared, prose) == ["/api/never-called/{thing}/trash"]

    freeze_list = {
        "tests/frozen.py": 'body = client.get("/api/other")\n'
                           'FROZEN = ["GET /api/never-called/{thing}/trash"]',
    }
    assert _gaps(declared, freeze_list) == ["/api/never-called/{thing}/trash"]

    called = {"tests/routes.py": 'client.get(f"/api/never-called/{other}/trash")'}
    assert _gaps(declared, called) == []

    built = {"tests/routes.py": 'client.get("/api/never-called/" + sid + "/trash")'}
    assert _gaps(declared, built) == []

    direct = {"tests/handler.py": "assert never_called('x') == {}"}
    assert _gaps(declared, direct) == []


def test_every_published_api_path_is_exercised_by_a_test() -> None:
    declared = _declared_api_paths(create_app())
    corpus = {
        str(path.relative_to(TESTS)): path.read_text(encoding="utf-8", errors="replace")
        for path in TESTS.rglob("*.py")
        if "__pycache__" not in path.parts
    }
    missing = _gaps(declared, corpus)
    assert not missing, (
        f"{len(missing)} published path(s) appear in no test that calls them: {missing} — the "
        "freeze list proves a route exists, not that anything exercises it; name the decision in "
        "KNOWN_GAPS or add the call"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
