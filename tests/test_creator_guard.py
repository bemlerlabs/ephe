"""Task #26 — the three Creator privileges: what they cover, where they are held, where a call stops.

The consent dialog asks for code, files and network. Given/When/Then throughout:
GIVEN a session with a stated set of privileges WHEN a tool is judged THEN the answer
comes from the registry's own authorities — the kernel dispatch map, the family a
manifest declares, or the MCP namespace — and nothing else.

"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

from core import session_lifecycle  # noqa: E402
from core.engine_config import config_root  # noqa: E402
from core.tools import creator_guard  # noqa: E402
from core.tools import session_ctx  # noqa: E402
from core.tools.creator_tools import CREATOR_TOOL_SCHEMAS  # noqa: E402

CREATOR_NAMES = frozenset(
    str(entry["function"]["name"]) for entry in CREATOR_TOOL_SCHEMAS
)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    return tmp_path / "cfg"


@pytest.fixture
def turn(home, monkeypatch):
    """One turn: a mode, a session and a set of privileges, undone on teardown.

    The mode and the session live in ContextVars, and a ContextVar outlives the test
    that set it, so they are cleared here. The reset tokens cannot be used across the
    teardown: an async test body runs in its own Context, and `Token.reset` in another
    one raises — which is why `tests/conftest.py` clears the same two by value too.
    """

    def _wrapped(mode="creator", session_id="s1", privileges=()):
        from core.tools import registry

        if privileges:
            creator_guard.set_privileges(session_id, privileges)
        session_ctx.set_current_mode(mode)
        session_ctx.set_current_session(session_id)
        monkeypatch.setattr(registry, "_TOOL_SCHEMA_CACHE", None)

    yield _wrapped
    session_ctx.set_current_mode("")
    session_ctx.set_current_session("")


class TestPrivilegeTable:
    def test_every_kernel_tool_carries_a_creator_ruling(self):
        """GIVEN the kernel dispatch map WHEN each name is ruled THEN the map holds it."""
        from core.tools.registry import TOOL_MAP

        missing = sorted(set(TOOL_MAP) - set(creator_guard.KERNEL_PRIVILEGES))
        extra = sorted(set(creator_guard.KERNEL_PRIVILEGES) - set(TOOL_MAP))
        assert not missing, f"kernel tools with no creator ruling: {missing}"
        assert not extra, f"rulings for names the kernel map does not hold: {extra}"

    def test_every_manifest_family_carries_a_creator_ruling(self):
        """GIVEN the family vocabulary WHEN families are ruled THEN none is left out."""
        from core.plugin_manifest import KNOWN_TOOL_FAMILIES

        assert set(creator_guard.FAMILY_PRIVILEGES) == set(KNOWN_TOOL_FAMILIES)

    def test_a_ruling_is_one_of_the_three_privileges_or_none(self):
        for name, value in creator_guard.KERNEL_PRIVILEGES.items():
            assert value in creator_guard.PRIVILEGES | {""}, name
        for family, value in creator_guard.FAMILY_PRIVILEGES.items():
            assert value in creator_guard.PRIVILEGES | {""}, family

    def test_the_creator_tools_ask_files_and_code(self):
        assert creator_guard.KERNEL_PRIVILEGES["create_plugin_scaffold"] == "files"
        assert creator_guard.KERNEL_PRIVILEGES["read_plugin_source"] == "files"
        assert creator_guard.KERNEL_PRIVILEGES["write_plugin_source"] == "files"
        assert creator_guard.KERNEL_PRIVILEGES["verify_plugin_bundle"] == "files"
        assert creator_guard.KERNEL_PRIVILEGES["install_plugin_bundle"] == "code"

    def test_a_bundle_tool_is_ruled_by_the_family_its_manifest_declares(self):
        """The first-party bundles are the 47 names the family rule has to answer for."""
        from core import plugin_manifest, plugin_tools_contract

        rows = 0
        for bundle in sorted((ROOT / "plugins").iterdir()):
            if not bundle.is_dir():
                continue
            manifest, error = plugin_manifest.load_manifest(bundle)
            if error or manifest is None:
                continue
            for claim in plugin_tools_contract.tool_claims(manifest):
                privilege, basis = creator_guard.judge(claim.name)
                assert basis == "family", claim.name
                assert privilege == creator_guard.FAMILY_PRIVILEGES[claim.family], claim.name
                rows += 1
        assert rows, "no bundle tool was ruled, so this test proves nothing"

    def test_an_mcp_name_asks_for_the_code_privilege(self, home, monkeypatch):
        from core.tools import mcp_client

        monkeypatch.setattr(
            mcp_client, "_MCP_TOOLS", {"mcp_remote_do": {"schema": {"name": "mcp_remote_do"}}}
        )
        assert creator_guard.judge("mcp_remote_do") == ("code", "mcp")

    def test_a_name_nothing_can_dispatch_carries_no_ruling(self, home):
        assert creator_guard.judge("no_such_tool_anywhere") == ("", "unlisted")


class TestPrivilegeStore:
    def test_a_grant_lands_in_the_backend_store(self, home):
        """The answer is a file, so a page reload and a second process read the same state."""
        creator_guard.set_privileges("s1", {"files"})
        assert creator_guard.privileges_for("s1") == frozenset({"files"})
        raw = json.loads((config_root() / "creator-consent.json").read_text(encoding="utf-8"))
        assert "files" in raw["s1"]["privileges"]

    def test_two_sessions_hold_their_own_grants(self, home):
        creator_guard.set_privileges("s1", {"code"})
        creator_guard.set_privileges("s2", {"network"})
        assert creator_guard.privileges_for("s1") == frozenset({"code"})
        assert creator_guard.privileges_for("s2") == frozenset({"network"})

    def test_replacing_a_grant_narrows_it(self, home):
        creator_guard.set_privileges("s1", {"code", "files"})
        creator_guard.set_privileges("s1", {"files"})
        assert creator_guard.privileges_for("s1") == frozenset({"files"})

    def test_an_unknown_privilege_is_refused_and_the_store_untouched(self, home):
        with pytest.raises(creator_guard.UnknownPrivilege):
            creator_guard.set_privileges("s1", {"files", "root"})
        assert creator_guard.privileges_for("s1") == frozenset()

    def test_a_key_that_cannot_name_a_session_is_refused(self, home):
        with pytest.raises(creator_guard.UnknownSession):
            creator_guard.set_privileges("../../etc/passwd", {"files"})

    def test_a_removed_session_leaves_its_grant_behind(self, home, monkeypatch):
        """The delete path forgets the row; a write never prunes behind the user's back."""
        import core.multi_session as ms

        monkeypatch.setattr(ms, "SESSIONS_DIR", str(home / "sessions"))
        (home / "sessions").mkdir(parents=True, exist_ok=True)
        creator_guard.set_privileges("a1b2c3d4", {"code"})
        (Path(ms.SESSIONS_DIR) / "a1b2c3d4.json").write_text("[]", encoding="utf-8")
        session_lifecycle.remove_sessions(["a1b2c3d4"])
        assert creator_guard.privileges_for("a1b2c3d4") == frozenset()


class TestGuardAtTheCall:
    def test_a_creator_call_without_its_privilege_is_refused(self, turn):
        turn()
        denial = creator_guard.denial_for("write_plugin_source")
        assert denial is not None
        assert denial.code == "creator_privilege_missing"
        assert denial.params["privilege"] == "files"

    def test_the_granted_privilege_ends_the_refusal(self, turn):
        turn(privileges={"files"})
        assert creator_guard.denial_for("write_plugin_source") is None

    def test_one_of_three_is_enough_for_its_own_calls(self, turn):
        turn(privileges={"files"})
        assert creator_guard.denial_for("write_plugin_source") is None
        assert creator_guard.denial_for("create_plugin_scaffold") is None

    def test_a_code_call_still_refuses_when_only_files_is_granted(self, turn):
        turn(privileges={"files"})
        denial = creator_guard.denial_for("install_plugin_bundle")
        assert denial is not None
        assert denial.params["privilege"] == "code"

    def test_no_privilege_at_all_refuses_every_gated_call(self, turn):
        turn()
        for name in ("read_file", "run_shell", "web_search", "write_plugin_source"):
            assert creator_guard.denial_for(name) is not None, name

    def test_a_call_that_asks_no_privilege_runs_without_a_grant(self, turn):
        turn()
        for name in ("ask_user", "todo_list", "tool_search"):
            assert creator_guard.denial_for(name) is None, name

    def test_nothing_is_refused_outside_creator_mode(self, turn):
        turn(mode="operator")
        for name in ("read_file", "run_shell", "install_plugin_bundle"):
            assert creator_guard.denial_for(name) is None, name

    def test_a_turn_that_never_named_a_session_holds_nothing(self, home):
        """Fail-closed: the fallback session key is not a holder of privileges."""
        assert creator_guard.privileges_for(session_ctx.get_current_session()) == frozenset()


class TestDispatchWiring:
    def test_every_creator_name_is_a_dispatch_target_of_the_kernel_map(self):
        """Each schema the mode offers is dispatched by the handler of the same name.

        Read off the schemas rather than written out as a list of names, so a call added
        to the family is checked the moment it is offered and a call renamed in one place
        alone fails here.
        """
        from core.tools import creator_tools
        from core.tools.registry import TOOL_MAP

        for entry in creator_tools.CREATOR_TOOL_SCHEMAS:
            name = entry["function"]["name"]
            handler = getattr(creator_tools, name, None)
            assert name in TOOL_MAP, f"{name} is offered and the kernel map does not hold it"
            assert TOOL_MAP[name] is handler, f"{name} dispatches somewhere else"

    async def test_execute_tool_refuses_before_the_handler_runs(self, turn, monkeypatch):
        from core.tools.registry import execute_tool
        from tests.tool_dispatch_seam import patched_tool

        turn()
        calls: list = []

        def boom(**_kwargs):
            calls.append("ran")
            return "should not run"

        with patched_tool("write_plugin_source", boom):
            result = await execute_tool(
                "write_plugin_source", {"bundle": "x", "path": "a", "content": "b"}
            )
        assert calls == []
        assert "[TOOL-DENIED]" in result
        assert getattr(result, "code", "") == "creator_privilege_missing"

    async def test_execute_tool_runs_the_handler_when_the_privilege_is_granted(self, turn, home):
        from core.tools.registry import execute_tool
        from tests.tool_dispatch_seam import patched_tool

        turn(privileges={"files"})
        seen: list = []

        async def fake(**kwargs):
            seen.append(kwargs)
            return "granted-run"

        with patched_tool("write_plugin_source", fake):
            result = await execute_tool(
                "write_plugin_source", {"bundle": "x", "path": "a", "content": "b"}
            )
        assert seen and result == "granted-run"

    async def test_the_refusal_is_audited_under_the_gate_that_refused_it(self, turn, monkeypatch):
        from core.tools import registry

        turn()
        rows: list = []

        def record(kind, **fields):
            rows.append((kind, fields))

        monkeypatch.setattr("core.audit_log.audit_event", record)
        await registry.execute_tool("install_plugin_bundle", {"bundle": "x"})
        gated = [
            fields
            for (kind, fields) in rows
            if kind == "mode_gate" and fields.get("tool") == "install_plugin_bundle"
        ]
        assert gated, f"the refusal never reached the audit: {rows}"
        assert gated[0]["status"] == "creator_privilege_missing"
        assert gated[0]["decision"] == "denied"

    async def test_a_non_creator_mode_call_is_untouched_by_the_guard(self, turn, home):
        """GIVEN operator mode WHEN a privileged tool runs THEN the guard answers nothing."""
        from core.tools.registry import execute_tool
        from tests.tool_dispatch_seam import patched_tool

        turn(mode="operator")
        seen: list = []

        async def fake(**kwargs):
            seen.append(kwargs)
            return "operator-run"

        with patched_tool("run_shell", fake):
            result = await execute_tool("run_shell", {"command": "echo hi"})
        assert result == "operator-run"
        assert seen


class TestOfferWiring:
    def _names(self) -> set[str]:
        from core.tools.registry import get_tool_schemas

        return {str(entry["function"]["name"]) for entry in get_tool_schemas()}

    def test_the_creator_tools_are_offered_in_creator_mode_only(self, turn):
        turn(mode="operator")
        assert not CREATOR_NAMES & self._names()
        turn(mode="creator", session_id="s2", privileges={"code", "files"})
        assert CREATOR_NAMES <= self._names()

    def test_a_missing_privilege_hides_the_creator_tool_it_gates(self, turn):
        turn(privileges={"files"})
        names = self._names()
        assert "write_plugin_source" in names
        assert "install_plugin_bundle" not in names

    def test_a_missing_privilege_hides_the_kernel_tools_it_gates(self, turn):
        turn(privileges={"files"})
        names = self._names()
        assert "execute_code" not in names
        assert "bash" not in names
        assert "todo_list" in names
        assert "ask_user" in names

    def test_an_outside_mode_offer_keeps_every_privileged_name(self, turn):
        turn(mode="operator", privileges=set())
        names = self._names()
        assert {"execute_code", "bash", "todo_list"} <= names

    def test_the_filter_judges_a_family_tool_without_a_mounted_descriptor(self, turn):
        """The rule is a name question, so the offer filter works on any array."""
        turn(privileges={"files"})
        array = [
            {"type": "function", "function": {"name": "read_file"}},
            {"type": "function", "function": {"name": "run_shell"}},
            {"type": "function", "function": {"name": "web_search"}},
        ]
        kept = {
            str(entry["function"]["name"])
            for entry in creator_guard.filter_offer(array)
        }
        assert kept == {"read_file"}

    def test_the_catalog_still_lists_a_tool_the_mode_hides(self, turn):
        """A name the mode does not offer has to stay in the catalog that could offer it."""
        from core.tools.registry import get_all_tool_schemas

        turn(mode="operator")
        names = {str(entry["function"]["name"]) for entry in get_all_tool_schemas()}
        assert CREATOR_NAMES <= names


class TestModelOfferArray:
    """The array the engine is actually sent, where the mode's promise is kept or broken.

    `get_tool_schemas()` is the registry's offer, and the class above judges that. The
    model never receives it: `core.chat_context._tools_for_messages()` ships the request,
    and a session with no skill whitelist narrows the offer to the discovery kernel's
    CORE_TOOLS first. No Creator call is CORE, so that narrowing decides whether the mode
    has any tool at all — a deferred name the model was never shown is a tool it can only
    guess the spelling of.
    """

    def _shipped(self, chat_context, allowed=None) -> set[str]:
        array = chat_context._tools_for_messages(
            [{"role": "user", "content": "Build me a plugin."}], allowed_tool_names=allowed
        )
        return {str(entry["function"]["name"]) for entry in array}

    def test_creator_mode_ships_the_calls_its_grant_covers(self, turn):
        """GIVEN a Creator session holding `files` WHEN the array is shipped THEN the
        three file-covering Creator calls are in it."""
        from core import chat_context

        turn(privileges={"files"})
        assert {
            "create_plugin_scaffold",
            "write_plugin_source",
            "verify_plugin_bundle",
        } <= self._shipped(chat_context)

    def test_a_grant_covering_all_five_ships_all_five(self, turn):
        """GIVEN a Creator session holding `code` and `files` WHEN the array is shipped
        THEN every one of the five calls is in it.

        This is the offer the creation eval's bundle cases run on, and the one the
        offer probe reads back. A missing name here is the offer's own defect; a name
        the grant does not cover is not (see the test below).
        """
        from core import chat_context

        turn(privileges={"code", "files"})
        assert set(CREATOR_NAMES) <= self._shipped(chat_context)

    def test_no_grant_ships_none_of_the_five(self, turn):
        """GIVEN a Creator session holding no permission WHEN the array is shipped THEN
        none of the five calls is in it.

        The guard rule is the authority and the offer may not deviate from it: the
        call the guard would refuse is not offered, so the turn names the missing
        step and its privilege in prose instead (CREATOR_MODE_GUARD).
        """
        from core import chat_context

        turn(privileges=set())
        assert not CREATOR_NAMES & self._shipped(chat_context)

    def test_the_offer_never_deviates_from_the_refusal_rule(self, turn):
        """GIVEN any subset of the three privileges WHEN the array is shipped THEN a
        Creator call is in it exactly when the guard would not refuse it.

        The offer is a list, the guard is the authority. A name the guard refuses must
        not be offered, and a name it would run must not be missing; anything else is
        two rules where the product promises one.
        """
        from itertools import combinations

        from core import chat_context

        for size in range(len(creator_guard.PRIVILEGES) + 1):
            for held in combinations(sorted(creator_guard.PRIVILEGES), size):
                turn(privileges=set(held))
                names = self._shipped(chat_context)
                for name in sorted(CREATOR_NAMES):
                    assert (name in names) == (creator_guard.denial_for(name) is None), (
                        f"{name} with {sorted(held)}: offered={name in names}, "
                        f"refused={creator_guard.denial_for(name) is not None}"
                    )

    def test_a_call_beyond_the_grant_stays_out_of_the_shipped_array(self, turn):
        from core import chat_context

        turn(privileges={"files"})
        assert "install_plugin_bundle" not in self._shipped(chat_context)

    def test_a_session_outside_creator_mode_ships_none_of_them(self, turn):
        """The mode boundary the guard keeps at the registry has to survive shipping."""
        from core import chat_context

        turn(mode="operator", privileges={"code", "files"})
        assert not CREATOR_NAMES & self._shipped(chat_context)

    def test_the_shipped_array_is_still_the_narrow_one(self, turn):
        """Cost: the Creator calls join the kernel, they do not replace the narrowing."""
        from core import chat_context

        turn(privileges={"files"})
        names = self._shipped(chat_context)
        for deferred in ("scaffold_project", "create_qrcode"):
            assert deferred not in names, f"{deferred} shipped outside CORE_TOOLS"

    def test_a_skill_whitelist_keeps_every_creator_call_the_grant_covers(self, turn):
        """GIVEN a Creator session holding `code` and `files` with a skill whitelist
        WHEN the array is shipped THEN the five calls are still in it.

        The whitelist narrows the kernel to the skill's own tools. It was written
        before Creator mode existed, and without the Creator calls re-joining it a
        build message that fuzzy-routes to a skill ships none of the five even when
        the grant covers all of them — the paid run's class 4a, reproduced with
        `evals/creation_offer_probe.py` on creation-20's own message.
        """
        from core import chat_context

        turn(privileges={"code", "files"})
        names = self._shipped(
            chat_context, allowed=["list_directory", "read_file", "run_shell"]
        )
        assert set(CREATOR_NAMES) <= names

    def test_a_skill_whitelist_cannot_smuggle_a_call_past_the_grant(self, turn):
        """The whitelist does not outrank the guard: with `files` held, the code call
        stays out even though the five join the whitelist."""
        from core import chat_context

        turn(privileges={"files"})
        names = self._shipped(
            chat_context, allowed=["list_directory", "read_file", "run_shell"]
        )
        assert "install_plugin_bundle" not in names
        assert {
            "create_plugin_scaffold",
            "read_plugin_source",
            "verify_plugin_bundle",
            "write_plugin_source",
        } <= names

    def test_the_prompt_tool_list_names_the_same_five_a_whitelist_turn_ships(self, turn):
        """The system text and the array are one list: a name in the array that the
        prompt's tool block omits is a name the model is told does not exist."""
        from core.persona import build_tool_guidelines

        turn(privileges={"code", "files"})
        text = build_tool_guidelines(["list_directory", "read_file", "run_shell"])
        for name in sorted(CREATOR_NAMES):
            assert name in text, name

    def test_a_skill_whitelist_keeps_the_creator_call_it_declares(self, turn):
        """GIVEN a whitelist naming a Creator call WHEN the array is shipped THEN the
        session gets it — the narrowing is the non-whitelist path's problem only."""
        from core import chat_context

        turn(privileges={"files"})
        names = self._shipped(chat_context, allowed=["create_plugin_scaffold", "read_file"])
        assert "create_plugin_scaffold" in names

    def test_a_grant_that_lands_after_another_session_read_still_ships(self, turn):
        """GIVEN the array was last built for a session outside the mode WHEN this
        session's grant lands inside the builder's TTL window THEN the mode ships its
        calls anyway.

        The dialog writes the consent row and the next turn is expected to run on it; an
        offer that arrives from another session's window keeps the user's answer stuck for
        a minute, which is what `core.tools.registry._apply_plugin_filter` promises never
        to do.
        """
        from core import chat_context
        from core.tools import session_ctx

        turn(mode="operator")
        assert "write_plugin_source" not in self._shipped(chat_context)
        creator_guard.set_privileges("s1", {"files"})
        session_ctx.set_current_mode("creator")
        session_ctx.set_current_session("s1")
        assert "write_plugin_source" in self._shipped(chat_context)


class TestConsentRoute:
    @pytest.fixture
    def client(self, home):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from server.routes import creator as creator_route

        app = FastAPI()
        app.include_router(creator_route.router, prefix="/api")
        return TestClient(app)

    def test_the_route_answers_what_the_session_holds(self, client, home):
        answer = client.get("/api/creator/consent", params={"session_id": "s9"}).json()
        assert sorted(answer["privileges"]) == ["code", "files", "network"]
        assert sorted(answer["held"]) == []
        assert answer["session_id"] == "s9"
        answer = client.put(
            "/api/creator/consent", json={"session_id": "s9", "privileges": ["files"]}
        ).json()
        assert sorted(answer["held"]) == ["files"]

    def test_the_route_replaces_the_privileges_it_is_given(self, client, home):
        client.put("/api/creator/consent", json={"session_id": "s9", "privileges": ["code", "network"]})
        answer = client.put(
            "/api/creator/consent", json={"session_id": "s9", "privileges": ["code"]}
        ).json()
        assert sorted(answer["held"]) == ["code"]

    def test_the_route_refuses_a_privilege_it_does_not_know(self, client, home):
        answer = client.put(
            "/api/creator/consent", json={"session_id": "s9", "privileges": ["root"]}
        )
        assert answer.status_code == 422
        assert creator_guard.privileges_for("s9") == frozenset()
        # The 422 carries the route's own sentence and the field the caller has to fix,
        # never the exception's text: a response built from `str(exc)` is the shape
        # `py/stack-trace-exposure` reports, and the reader loses nothing without it.
        detail = answer.json()["detail"]
        assert detail["unknown"] == ["root"]
        assert detail["reason"] == "unknown privilege(s): root"

    def test_the_route_records_the_change_in_the_audit(self, client, home, monkeypatch):
        rows: list = []
        monkeypatch.setattr(
            "core.audit_log.audit_event",
            lambda kind, **fields: rows.append((kind, fields)),
        )
        client.put("/api/creator/consent", json={"session_id": "s9", "privileges": ["files"]})
        kinds = [row[0] for row in rows]
        assert "security" in kinds

    def test_a_key_that_could_not_name_a_session_is_refused_by_both_verbs(
        self, client, home
    ):
        """The read asks the shape question the write asks, and answers it in one sentence.

        A dotted path would otherwise return a well-formed "holds nothing" for a holder
        the store can never have, and a dialog built on that answer would offer to grant
        what the guard refuses to record. An empty key is the app's own spelling of "no
        session was named", which the guard answers with nothing held.
        """
        bad = "../etc/passwd"
        read = client.get("/api/creator/consent", params={"session_id": bad})
        write = client.put(
            "/api/creator/consent", json={"session_id": bad, "privileges": ["files"]}
        )
        assert read.status_code == 422
        assert write.status_code == 422
        assert read.json()["detail"] == write.json()["detail"]
        blank = client.get("/api/creator/consent", params={"session_id": ""}).json()
        assert sorted(blank["held"]) == []


def test_creator_mode_names_its_path_in_the_prompt_the_engine_is_given():
    """GIVEN a turn that resolves to Creator mode WHEN the route composes its system prompt
    THEN the prompt says what the mode builds and with which calls.

    The offer is only half of a mode. Live evidence: `deepseek-v4-pro` was handed all four
    creator names in a 36-entry array, was never told what a bundle is, searched the
    landscape for a shell, and delivered `floating_countdown.py` with `write_file` — a file
    the dock cannot mount, so the eval staged nothing (/private/tmp/ephe-creation-eval/run1).
    Architect answers with a plan block because `ARCHITECT_MODE_GUARD` says so in the prompt;
    Creator had no such sentence, only a name in an array.
    """
    from server.routes.chat import _mode_context

    extra, _allowed, flags = _mode_context(
        "creator", skill=None, message="Build me a floating countdown window."
    )
    assert flags["creator"] is True
    assert "CREATOR-MODE" in extra
    for name in sorted(CREATOR_NAMES):
        assert name in extra, f"the guard does not name {name}"
    assert "write_file" in extra, "the guard never says what the loose-file answer is"


def test_a_mode_that_is_not_creator_stays_out_of_the_bundle_guard():
    """The guard belongs to one mode: an operator or agent turn keeps its own file tools."""
    from server.routes.chat import _mode_context

    for mode in ("operator", "agent", "analyst", ""):
        extra, _allowed, flags = _mode_context(mode, skill=None, message="Count my files.")
        assert not flags["creator"], mode
        assert "CREATOR-MODE" not in (extra or ""), mode


def test_the_guard_runs_the_calls_it_has_when_one_is_missing():
    """GIVEN a Creator turn whose grant withholds one of the four calls WHEN the guard is read
    THEN it says to run the calls in hand and name the step that is blocked.

    Live evidence, the turn after the mode instruction shipped
    (/private/tmp/ephe-creation-eval/run3/transcripts.json): the `files` grant keeps scaffold,
    write and verify in the array and withholds install, because
    `creator_guard.KERNEL_PRIVILEGES` maps `install_plugin_bundle` to `code`. The guard's
    stop-clause was read as "stop before building": the turn answered with a plan and staged
    nothing, refusing three calls that would have worked.
    """
    from core.persona import CREATOR_MODE_GUARD

    text = " ".join(CREATOR_MODE_GUARD.split())
    assert "run the ones you have" in text, "the guard throws away the available calls"
    assert "name the step" in text, "the blocked half of the job is never reported"
    assert "stop there" not in text, "the guard still asks for a full stop"


def test_the_guard_names_the_state_path_the_eval_grades():
    """GIVEN a Creator turn whose plugin must remember something WHEN the guard is read
    THEN the graded state path is stated, so a page-storage bundle is not failed for a
    rule the turn never read.

    The class-2 register row names the gap: `creation-01`, `-05` and `-08` wrote
    `localStorage` and lost the `state_bridge_used` row, and nothing in the turn's
    prompt named `ephe.storage`. The mount's shim now keeps those bundles working, so
    the guard has to state which of the two paths the definition of done grades.
    """
    from core.persona import CREATOR_MODE_GUARD

    text = " ".join(CREATOR_MODE_GUARD.split())
    assert "ephe.storage" in text, "the graded state path is never named"
    assert "ephe.js" in text, "the script that carries the SDK is never named"
    assert "localStorage" in text, "the shimmed path is not distinguished from the graded one"
