"""Every coded engine line has both halves, and the bundle has no silent key.

`docs/SERVER_SURFACE_LANGUAGE_DECISION_2026-10-09.md` §5 splits the dual-sink text: the
sentence the engine reads stays in the producer (`core/net_guard.py`, the tool modules,
`core/browser_url.py`), the sentence the user reads becomes `reader.<reason_code>` in
`app/src/locales/{de,en}.json`. Four things have to stay true for that split, and all four
are measured here — every coded line carries its code from the layer that wrote the
sentence, the code's parameters are exactly the placeholders both locale files interpolate,
the English entry reproduces the server's own sentence byte for byte, and the German entry
deliberately does not. The `reader.` family is named for the first surface that had one.

The German copy is read from `de.json`, never written into a literal in this file: a
locale file is protected prose by the language gate, a test file is not, and a second
copy of a sentence here would be free to drift from the one the user reads.
"""
from __future__ import annotations

import asyncio
import json
import re
import socket
import urllib.error
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.memory_kepta_bridge import KeptaBridgeProvider
from core.net_guard import check_url, reach_by_name
from core.reason import Reason
from core.tools.fetch_tools import FetchRefused, FetchTransport
from server.main import create_app

LOCALE_DIR = Path(__file__).resolve().parents[1] / "app" / "src" / "locales"
BUNDLES = {
    lng: json.loads((LOCALE_DIR / f"{lng}.json").read_text(encoding="utf-8"))["reader"]
    for lng in ("de", "en")
}
PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def _resolver(table: dict[str, list[str]]):
    def resolve(host: str) -> list[str]:
        if host in table:
            return table[host]
        raise socket.gaierror(f"no such host {host}")

    return resolve


def _broken_resolver(host: str) -> list[str]:
    raise ValueError("resolver broken")


def _empty_resolver(host: str) -> list[str]:
    return []


#: the 16 refusal statements of `core/net_guard.py`, one row per emission site, and
#: the parameters each one interpolates. `allow_private` is set wherever the answer
#: depends on it, so an exported environment variable cannot flip a row.
CASES = (
    ("url_empty", lambda _mp: _guard(""), ()),
    ("url_without_scheme", lambda _mp: _guard("example.com/docs"), ()),
    ("scheme_blocked", lambda _mp: _guard("file:///etc/passwd"), ("scheme",)),
    ("no_host", lambda _mp: _guard("https:///x"), ("url",)),
    (
        "metadata_host",
        lambda _mp: _guard("http://metadata.google.internal/", resolver=_resolver({})),
        ("host",),
    ),
    (
        "not_resolvable",
        lambda _mp: _guard("http://gone.invalid/x", resolver=_resolver({})),
        ("host",),
    ),
    (
        "not_resolvable",
        lambda _mp: _guard("http://nil.test/x", resolver=_empty_resolver),
        ("host",),
    ),
    (
        "dns_failed",
        lambda _mp: _guard("http://any.test/x", resolver=_broken_resolver),
        ("host", "error_type"),
    ),
    (
        "always_blocked_class",
        lambda _mp: _guard("http://169.254.169.254/x", allow_private=True),
        ("host", "address", "kind"),
    ),
    (
        "private_blocked_default",
        lambda _mp: _guard("http://127.0.0.1:3000/", allow_private=False),
        ("host", "address", "kind"),
    ),
    ("scheme_outside_channel", lambda _mp: _by_name("file:///etc/passwd"), ("scheme",)),
    ("no_host_in_url", lambda _mp: _by_name("https:///x"), ()),
    ("internal_target_name", lambda _mp: _by_name("http://localhost:8765/x"), ("host",)),
    ("internal_name_suffix", lambda _mp: _by_name("http://db.internal/x"), ("host",)),
    (
        "always_blocked_class_name",
        lambda _mp: _by_name("http://[fd00:ec2::254]/x", allow_private=True),
        ("host", "kind"),
    ),
    (
        "private_blocked_default_name",
        lambda _mp: _by_name("http://10.1.2.3/x", allow_private=False),
        ("host", "kind"),
    ),
)

class _FakeCollection:
    """The memory tier as a list — the sentences are under test, not the brain.

    ``memory()`` builds a ``Memory`` before it looks at the arguments, so every
    memory case needs this: the real one would write the case's fact into the
    developer's own Kepta store from a test.
    """

    def __init__(self) -> None:
        self.items: list[dict[str, str]] = []

    def count(self) -> int:
        return len(self.items)

    def store(self, text: str, metadata=None, **_kw) -> None:
        self.items.append({"id": f"e{len(self.items)}", "text": text})

    def list_all(self, limit: int = 50) -> list[dict[str, str]]:
        return list(self.items)

    def delete(self, entry_id: str) -> None:
        self.items = [e for e in self.items if e["id"] != entry_id]


class _FakeProfile:
    def __init__(self) -> None:
        self.topics_of_interest: list[str] = []

    def to_context_string(self) -> str:
        return ""


class _FakeCatalog:
    def __init__(self, *_a, **_kw) -> None:
        pass

    def load_all(self) -> list:
        return []

    def save(self, **_kw):
        from types import SimpleNamespace

        return SimpleNamespace(name="coded-skill")

    def delete(self, name: str) -> None:
        return None


class _FailingCatalog(_FakeCatalog):
    def save(self, **_kw):
        from core.skills import SkillLoadError

        raise SkillLoadError("invalid skill name: 'bad name'")

    def delete(self, name: str) -> None:
        raise FileNotFoundError("User skill 'coded-skill' not found.")


def _mem_line(monkeypatch, *calls: dict):
    """One collection behind the whole call sequence, so a remove sees the add."""
    import core.memory
    from core.tools.state_tools import memory

    collection = _FakeCollection()
    monkeypatch.setattr(core.memory, "Memory", lambda: collection)

    async def run():
        out = None
        for kw in calls:
            out = await memory(**kw)
        return out

    return asyncio.run(run())


def _profile_line(monkeypatch, **kw):
    import core.profile
    from core.tools.state_tools import memory

    monkeypatch.setattr(core.profile, "load_profile", lambda: _FakeProfile())
    monkeypatch.setattr(core.profile, "save_profile", lambda _p: None)
    return asyncio.run(memory(**kw))


def _skill_line(monkeypatch, catalog=_FakeCatalog, **kw):
    import core.skills
    from core.tools.state_tools import skill_manage

    monkeypatch.setattr(core.skills, "SkillLoader", catalog)
    return asyncio.run(skill_manage(**kw))


def _todo_line(monkeypatch, **kw):
    from core.tools import todo_tools

    return asyncio.run(todo_tools.todo_list(**kw))


def _todo_after_set(monkeypatch, **kw):
    from core.tools import todo_tools

    async def run():
        await todo_tools.todo_list(action="set", items="One\nTwo")
        return await todo_tools.todo_list(**kw)

    return asyncio.run(run())


def _todo_empty(monkeypatch):
    from core.tools import todo_tools

    async def run():
        todo_tools.reset_todo()
        return await todo_tools.todo_list(action="list")

    return asyncio.run(run())


def _bg(monkeypatch, action: str, *, live: bool = False, status: str = "done", out: str = ""):
    """process_manage against a register entry, which the tool never makes itself."""
    from core.tools import process_tools

    async def run():
        handle = asyncio.get_running_loop().create_future()
        if not live:
            handle.cancel()
        process_tools._BG_TASKS["bgC"] = {"handle": handle, "status": status, "out": out}
        try:
            return await process_tools.process_manage(action, "bgC")
        finally:
            process_tools._BG_TASKS.pop("bgC", None)

    return asyncio.run(run())


def _fetch_call(monkeypatch, url: str, get) -> Reason:
    import core.tools.fetch_tools as fetch_tools

    fetch_tools._FETCH_CACHE.clear()
    monkeypatch.setattr(fetch_tools, "_http_get", get)
    return asyncio.run(fetch_tools.fetch_url(url))


def _fetch_answers(monkeypatch, status: int, url: str = "https://example.test/missing"):
    async def get(_url):
        return status, ""

    return _fetch_call(monkeypatch, url, get)


def _fetch_raises(monkeypatch, exc: BaseException, url: str = "https://example.test/page"):
    async def get(_url):
        raise exc

    return _fetch_call(monkeypatch, url, get)


async def _no_http(_url):
    raise AssertionError("an empty URL must not reach the network")


#: The tool returns a card can show: `[memory]`, `[skill_manage]`, `[todo_list]`,
#: `[process_manage]`, `[fetch failed]`, `[fetch refused]`. Two fallthrough lines of
#: `state_tools` are missing here on purpose — the action guard above them admits exactly
#: the branches that handle every action, so no emission reaches them and a locale entry
#: for them would be a key nobody resolves.
TOOL_CASES = (
    ("memory_action_unknown", lambda mp: _mem_line(mp, {"action": "clear", "target": "memory"}), ()),
    ("memory_target_unknown", lambda mp: _mem_line(mp, {"action": "add", "target": "facts"}), ()),
    ("memory_add_needs_content", lambda mp: _mem_line(mp, {"action": "add", "target": "memory"}), ()),
    (
        "memory_stored",
        lambda mp: _mem_line(mp, {"action": "add", "target": "memory", "content": "coded case"}),
        ("count",),
    ),
    ("memory_empty", lambda mp: _mem_line(mp, {"action": "list", "target": "memory"}), ()),
    (
        "memory_remove_needs_old_text",
        lambda mp: _mem_line(mp, {"action": "remove", "target": "memory"}),
        (),
    ),
    (
        "memory_removed",
        lambda mp: _mem_line(
            mp,
            {"action": "add", "target": "memory", "content": "coded case"},
            {"action": "remove", "target": "memory", "old_text": "coded"},
        ),
        ("count",),
    ),
    (
        "memory_replace_needs_fields",
        lambda mp: _mem_line(mp, {"action": "replace", "target": "memory", "old_text": "coded"}),
        (),
    ),
    (
        "memory_replaced",
        lambda mp: _mem_line(
            mp,
            {"action": "add", "target": "memory", "content": "coded case"},
            {
                "action": "replace", "target": "memory",
                "old_text": "coded", "content": "replacement",
            },
        ),
        ("count",),
    ),
    ("profile_empty", lambda mp: _profile_line(mp, action="list", target="user"), ()),
    ("profile_updated", lambda mp: _profile_line(mp, action="add", target="user", content="x=y"), ()),
    (
        "profile_action_needs_content",
        lambda mp: _profile_line(mp, action="replace", target="user"),
        ("action",),
    ),
    (
        "profile_action_done",
        lambda mp: _profile_line(mp, action="remove", target="user", content="name=x"),
        ("action",),
    ),
    ("skill_list_empty", lambda mp: _skill_line(mp, action="list"), ()),
    ("skill_show_needs_name", lambda mp: _skill_line(mp, action="show"), ()),
    ("skill_create_needs_fields", lambda mp: _skill_line(mp, action="create", name="x"), ()),
    (
        "skill_create_needs_prompt",
        lambda mp: _skill_line(mp, action="create", name="x", trigger="t", description="d"),
        (),
    ),
    (
        "skill_create_failed",
        lambda mp: _skill_line(
            mp, catalog=_FailingCatalog, action="create", name="x", trigger="t",
            description="d", system_prompt="p",
        ),
        ("error",),
    ),
    (
        "skill_saved",
        lambda mp: _skill_line(
            mp, action="create", name="x", trigger="t", description="d", system_prompt="p"
        ),
        ("name",),
    ),
    ("skill_delete_needs_name", lambda mp: _skill_line(mp, action="delete"), ()),
    ("skill_deleted", lambda mp: _skill_line(mp, action="delete", name="coded-skill"), ("name",)),
    (
        "skill_delete_failed",
        lambda mp: _skill_line(mp, catalog=_FailingCatalog, action="delete", name="coded-skill"),
        ("error",),
    ),
    ("todo_set_needs_items", lambda mp: _todo_line(mp, action="set"), ()),
    ("todo_id_out_of_range", lambda mp: _todo_after_set(mp, action="update", id=9), ("limit",)),
    (
        "todo_status_unknown",
        lambda mp: _todo_after_set(mp, action="update", id=1, status="suspended"),
        ("status", "allowed"),
    ),
    ("todo_action_unknown", lambda mp: _todo_line(mp, action="drop"), ("action",)),
    ("todo_list_empty", _todo_empty, ()),
    ("process_action_unknown", lambda mp: _bg(mp, "clear"), ("action",)),
    ("process_needs_task_id", lambda mp: _missing_task(mp), ()),
    ("process_unknown_task", lambda mp: _missing_task(mp, task_id="bgMissing"), ("task_id",)),
    ("process_stopped", lambda mp: _bg(mp, "kill", live=True, status="running"), ("task_id",)),
    ("process_already_state", lambda mp: _bg(mp, "kill"), ("task_id", "state")),
    ("process_output_pending", lambda mp: _bg(mp, "poll", status="running"), ("task_id",)),
    ("process_no_output", lambda mp: _bg(mp, "poll"), ("task_id", "status")),
    ("fetch_empty_url", lambda mp: _fetch_call(mp, "", _no_http), ()),
    (
        "fetch_scheme_blocked",
        lambda mp: _fetch_raises(
            mp,
            FetchRefused(check_url("file:///etc/passwd")[1]),
            "file:///etc/passwd",
        ),
        ("scheme",),
    ),
    (
        "fetch_refused",
        lambda mp: _fetch_raises(mp, FetchRefused("Redirect without a target.")),
        ("detail",),
    ),
    ("fetch_http_error", lambda mp: _fetch_answers(mp, 404), ("status", "url")),
    (
        "fetch_timeout",
        lambda mp: _fetch_raises(mp, FetchTransport("example.test: TimeoutException")),
        (),
    ),
    (
        "fetch_unreachable",
        lambda mp: _fetch_raises(mp, FetchTransport("example.test: ConnectError")),
        (),
    ),
)

class _UnresolvablePath:
    """`path.resolve()` raising is the branch — no filesystem serves that on demand."""

    def __init__(self, value: str = "", *_a, **_kw) -> None:
        self.value = str(value)

    def expanduser(self):
        return self

    def resolve(self):
        raise OSError("File name too long")

    def __str__(self) -> str:
        return self.value


def _browser_line(monkeypatch, url: str, *, unresolvable: bool = False) -> Reason:
    import core.browser_url as browser_url

    if unresolvable:
        monkeypatch.setattr(browser_url, "Path", _UnresolvablePath)
    return browser_url.url_policy(url)[1]


#: The headless browser's five policy refusals. `core/browser.py:go()` prefixes them with
#: the detector marker and carries the code on — the marker is engine-side, the sentence
#: behind it is what the card resolves.
BROWSER_CASES = (
    ("browser_url_empty", lambda mp: _browser_line(mp, ""), ()),
    ("browser_scheme_blocked", lambda mp: _browser_line(mp, "javascript:alert(1)"), ("scheme",)),
    (
        "browser_path_unresolvable",
        lambda mp: _browser_line(mp, "file:///very/long", unresolvable=True),
        ("path", "error"),
    ),
    ("browser_target_not_a_file", lambda mp: _browser_line(mp, "file:///tmp"), ("resolved", "root")),
    (
        "browser_outside_artifact_roots",
        lambda mp: _browser_line(mp, "file:///etc/hosts"),
        ("resolved",),
    ),
)

ALL_CASES = CASES + TOOL_CASES + BROWSER_CASES
ALL_IDS = [f"{index}:{code}" for index, (code, _, _params) in enumerate(ALL_CASES)]


def _bridge(monkeypatch, transport=None) -> KeptaBridgeProvider:
    return KeptaBridgeProvider("http://127.0.0.1:3000", scope="agent", transport=transport)


def _no_route(_method, _path, _body=None, _params=None):
    raise urllib.error.URLError("no route to host")


def _bridge_error(build):
    """The exception a bridge call raises — `core/memory_kepta_bridge.py` refuses, it does not reply."""
    try:
        build()
    except BaseException as exc:  # noqa: BLE001 — the raise is the case
        return exc
    raise AssertionError("the bridge took what it promises to refuse")


#: The five refusals of the Kepta bridge. They reach the surface through the registry's error
#: sink (`core/tools/registry.py:_error_line`), which lifts the code off the exception object.
BRIDGE_CASES = (
    (
        "kepta_needs_an_instance",
        lambda mp: _bridge_error(lambda: KeptaBridgeProvider("", scope="agent")),
        ("env",),
    ),
    (
        "kepta_instance_unreachable",
        lambda mp: _bridge_error(lambda: _bridge(mp, transport=_no_route).count()),
        ("url", "error", "env"),
    ),
    (
        "kepta_writes_its_own_ids",
        lambda mp: _bridge_error(lambda: _bridge(mp).store("a fact", doc_id="given")),
        (),
    ),
    ("kepta_empty_text_is_data_loss", lambda mp: _bridge_error(lambda: _bridge(mp).update("e1", "  ")), ()),
    ("kepta_clear_needs_the_instance", lambda mp: _bridge_error(lambda: _bridge(mp).clear()), ()),
)


#: The three statements the reader route owns itself; they are emitted through
#: `server/routes/reader.py:_refused`, which names the code beside the sentence.
OWNED_BY_THE_ROUTE = ("url_not_http", "http_status_error", "no_readable_text")


def _missing_task(_mp, **kw):
    from core.tools import process_tools

    async def run():
        return await process_tools.process_manage(kw.get("action", "poll"), kw.get("task_id", ""))

    return asyncio.run(run())


def _guard(url: str, **kw) -> Reason:
    return check_url(url, **kw)[1]


def _by_name(url: str, **kw) -> Reason:
    return reach_by_name(url, **kw)[1]


def _note(case: tuple, monkeypatch) -> Reason:
    _code, emit, _params = case
    note = emit(monkeypatch)
    assert isinstance(note, Reason), f"{case[0]} reached the surface without a reason note"
    return note


def _fill(template: str, params: dict[str, object]) -> str:
    return PLACEHOLDER.sub(lambda match: str(params[match.group(1)]), template)


@pytest.mark.parametrize("case", ALL_CASES, ids=ALL_IDS)
def test_every_coded_line_carries_a_reason_and_stays_a_sentence(case, monkeypatch):
    code, _emit, param_names = case
    note = _note(case, monkeypatch)
    # str is the additive half: the tool path and the audit read this object as text.
    assert isinstance(note, str)
    assert note.code == code
    assert tuple(note.params) == param_names
    for key, value in note.params.items():
        assert value, f"{code} interpolates an empty {key}"
        assert value in str(note), f"{code} names {key} in its entry but not in its line"


def test_the_emitted_codes_are_the_documented_set():
    guards = {case[0] for case in CASES}
    tools = {case[0] for case in TOOL_CASES}
    browser = {case[0] for case in BROWSER_CASES}
    assert len(guards) == 15, "two guard sites share a wording, every other one stands alone"
    assert len(tools) == 40, "every tool line names one reason of its own"
    assert len(browser) == 5, "the browser policy has five refusals and no more"
    bridge = {case[0] for case in BRIDGE_CASES}
    assert len(bridge) == 5, "the bridge refuses five things and says which"
    named = guards | tools | browser | bridge
    assert len(named) == 65, "two surfaces share a code"
    assert (guards & tools | guards & browser | guards & bridge
            | tools & browser | tools & bridge | browser & bridge) == set(), \
        "a code names two surfaces, so the card cannot tell them apart"
    # The three entries the reader route owns itself are the only ones no emitter names.
    # Plural forms (`_one`/`_other`) are i18next's own mechanism; they collapse onto their
    # base key before the set comparison.
    plural = re.compile(r"_(?:zero|one|two|few|many|other)$")
    for lng, bundle in BUNDLES.items():
        base = {plural.sub("", key) for key in bundle}
        assert base == named | set(OWNED_BY_THE_ROUTE), f"{lng}.json/reader drifted"
        assert len(base) == 68


@pytest.mark.parametrize(("code", "build", "param_names"), BRIDGE_CASES,
                       ids=[case[0] for case in BRIDGE_CASES])
def test_a_bridge_error_carries_its_reason_on_the_exception(code, build, param_names, monkeypatch):
    """The sink of `core/tools/registry.py` reads these two attributes off whatever a tool
    raised; `core.reason.coded` sets them without touching the exception's class, so an
    existing `except ValueError` on the caller side keeps catching what it caught."""
    exc = build(monkeypatch)
    assert exc.code == code
    assert tuple(exc.params) == param_names
    assert _fill(BUNDLES["en"][code], dict(exc.params)) == str(exc)
    assert _fill(BUNDLES["de"][code], dict(exc.params)) != str(exc)


@pytest.mark.parametrize("case", ALL_CASES, ids=ALL_IDS)
def test_both_locale_entries_interpolate_exactly_the_emitted_params(case, monkeypatch):
    code = case[0]
    params = _note(case, monkeypatch).params
    for lng, bundle in BUNDLES.items():
        placeholders = set(PLACEHOLDER.findall(bundle[code]))
        assert placeholders == set(params), f"{lng}.json/reader.{code} wants {placeholders}"


@pytest.mark.parametrize("case", ALL_CASES, ids=ALL_IDS)
def test_the_server_line_is_the_english_entry_and_the_german_stays_locale(case, monkeypatch):
    """Engine-facing text is English (AGENTS.md, owner decision 2026-10-08); the
    German is the reader's surface and lives in `de.json` behind the same code.
    Before this the server line WAS the German sentence, so the two could never
    be told apart by a test — one assertion, one contract."""
    note = _note(case, monkeypatch)
    assert _fill(BUNDLES["en"][note.code], dict(note.params)) == str(note)
    german = _fill(BUNDLES["de"][note.code], dict(note.params))
    assert german != str(note), f"{note.code} has no German half — the locale entry is a copy of the line"


@pytest.fixture
def client():
    return TestClient(create_app())


def test_the_reader_payload_names_a_guard_refusal(client):
    target = "http://169.254.169.254/latest/meta-data/"
    data = client.get("/api/reader", params={"url": target}).json()
    assert data["ok"] is False
    assert data["reason_code"] == "always_blocked_class"
    assert data["reason_params"] == {
        "host": "169.254.169.254",
        "address": "169.254.169.254",
        "kind": "metadata",
    }
    # `reason` stays the guard's own line for old clients and for the log.
    assert data["reason"] == str(check_url(target, allow_private=True)[1])
    # The guard line is English (engine-facing prose, AGENTS.md); the German half is
    # the reader's surface and arrives by `reason_code`, so the two are now told apart.
    assert _fill(BUNDLES["en"]["always_blocked_class"], data["reason_params"]) == data["reason"]
    assert BUNDLES["de"]["always_blocked_class"] != data["reason"]


def test_a_fetch_fault_the_guard_does_not_name_is_the_routes_own_sentence(client, monkeypatch):
    """The guard allows this address; the fetch below it failed, and the line of that
    fault names its class. A pane reads the route's fixed sentence instead, with a null
    code — the shape the branch for every other exception already answers with."""
    import core.tools.fetch_tools as fetch_tools

    async def refused(url: str):
        raise FetchRefused("[error] ConnectError: connection refused")

    monkeypatch.setattr(fetch_tools, "_http_get", refused)
    data = client.get("/api/reader", params={"url": "https://93.184.216.34/x"}).json()

    assert data["ok"] is False
    assert data["reason_code"] is None
    assert data["reason_params"] == {}
    assert data["reason"] == "The page could not be read."
    assert "ConnectError" not in data["reason"]


@pytest.mark.parametrize(
    ("url", "code", "params"),
    [
        ("not an address at all", "url_not_http", {}),
        ("mailto:someone@example.com", "url_not_http", {}),
    ],
)
def test_the_routes_own_first_literal_is_keyed(client, url, code, params):
    data = client.get("/api/reader", params={"url": url}).json()
    assert data["reason_code"] == code
    assert data["reason_params"] == params
    assert _fill(BUNDLES["en"][code], data["reason_params"]) == data["reason"]
    assert BUNDLES["de"][code] != data["reason"]


def test_the_routes_status_and_empty_page_literals_are_keyed(client, monkeypatch):
    import core.tools.fetch_tools as fetch_tools

    async def answers(url: str):
        return 503, "<html><body>nope</body></html>"

    monkeypatch.setattr(fetch_tools, "_http_get", answers)
    data = client.get("/api/reader", params={"url": "https://example.com/x"}).json()
    assert data["reason_code"] == "http_status_error"
    assert data["reason_params"] == {"status": 503}
    assert _fill(BUNDLES["en"]["http_status_error"], data["reason_params"]) == data["reason"]

    async def empty_body(url: str):
        return 200, "<html><head><title>Empty</title></head><body>   </body></html>"

    monkeypatch.setattr(fetch_tools, "_http_get", empty_body)
    data = client.get("/api/reader", params={"url": "https://example.com/x"}).json()
    assert data["ok"] is False
    assert data["reason_code"] == "no_readable_text"
    assert _fill(BUNDLES["en"]["no_readable_text"], {}) == data["reason"]


def test_a_read_page_carries_the_two_new_keys_as_neutral_values(client, monkeypatch):
    import core.tools.fetch_tools as fetch_tools

    async def readable(url: str):
        return 200, "<html><body><p>Text the pane can show.</p></body></html>"

    monkeypatch.setattr(fetch_tools, "_http_get", readable)
    data = client.get("/api/reader", params={"url": "https://example.com/x"}).json()
    assert data["ok"] is True
    assert (data["reason"], data["reason_code"], data["reason_params"]) == ("", None, {})
