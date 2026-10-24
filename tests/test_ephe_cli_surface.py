"""In-process command-surface tests for ephe_cli.py.

The CLI behaviour is pinned by subprocess tests (test_cli_dx/session/ux); those
child processes are invisible to coverage. These tests drive the cmd_* functions
and helpers in-process so the branches the CLI surface actually has are exercised
and traced: session, plugin, import, tool, bench, update, desktop, serve, start,
doctor, voice, code/goal and the completion/main dispatch.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

import ephe_cli


async def _async_ok(*_a, **_k) -> list:
    return []


def _patch_run_record(monkeypatch) -> None:
    """cmd_code/goal emit a validated run record; keep the schema out of scope here."""
    import core.run_record as rr

    monkeypatch.setattr(rr, "dump_record", lambda record: json.dumps(record))


class _FakeChoice:
    """Minimal EngineChoice stand-in: provider/model/api_url + a no-op apply_env."""

    def __init__(self, provider: str, model: str, api_url: str | None = None) -> None:
        self.provider = provider
        self.model = model
        self.api_url = api_url

    def apply_env(self) -> None:  # noqa: D401 - matches the real surface
        return None


class _Rec:
    turn_id = "turn"

    def on_phase(self, *_a, **_k) -> None:
        return None

    def build(self, **kw) -> dict:
        return {"answer": kw.get("answer", ""), "solved": kw.get("solved")}


def _parser() -> argparse.ArgumentParser:
    return ephe_cli.build_parser()


def _patch_ephemeris(monkeypatch) -> None:
    """cmd_start records one orbit; keep the write out of the real ~/.ephe."""
    import core.ephemeris as eph

    monkeypatch.setattr(eph, "record", lambda *_a, **_k: None)


# completion (script builder + command)


def test_completion_script_variants():
    cmds = ["start", "doctor"]
    assert "complete -F _ephe_complete ephe" in ephe_cli._completion_script("bash", cmds)
    assert "compdef _ephe ephe" in ephe_cli._completion_script("zsh", cmds)
    fish = ephe_cli._completion_script("fish", cmds)
    assert "complete -c ephe" in fish


def test_cmd_completion_without_shell_is_usage_error(capsys):
    args = _parser().parse_args(["completion"])
    assert ephe_cli.cmd_completion(args) == 2
    capsys.readouterr()


def test_cmd_completion_bash(capsys):
    args = _parser().parse_args(["completion", "bash"])
    assert ephe_cli.cmd_completion(args) == 0
    assert "complete -F" in capsys.readouterr().out


# update


def test_cmd_update_missing_installer(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(ephe_cli, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(ephe_cli, "_run", lambda *_a, **_k: types.SimpleNamespace(returncode=0))
    assert ephe_cli.cmd_update(_parser().parse_args(["update", "--json"])) == 1
    capsys.readouterr()


def test_cmd_update_runs_git_and_installer(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(ephe_cli, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".git").mkdir()
    (tmp_path / "install.sh").write_text("echo hi")
    calls: list[list[str]] = []

    def fake_run(cmd, *_a, **_k):
        calls.append(cmd)
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(ephe_cli, "_run", fake_run)
    assert ephe_cli.cmd_update(_parser().parse_args(["update", "--json", "--model", "m1"])) == 0
    assert calls[0] == ["git", "pull", "--ff-only"]
    assert calls[1][0] == "bash" and calls[1][-1] == "--no-start"
    capsys.readouterr()


def test_cmd_update_reports_failure_exit_code(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(ephe_cli, "PROJECT_ROOT", tmp_path)
    (tmp_path / "install.sh").write_text("x")
    monkeypatch.setattr(ephe_cli, "_run", lambda *_a, **_k: types.SimpleNamespace(returncode=3))
    assert ephe_cli.cmd_update(_parser().parse_args(["update"])) == 3
    capsys.readouterr()


# bench


def test_cmd_bench_verify_gate(monkeypatch, capsys, tmp_path):
    import core.plugin_golden as pg

    monkeypatch.setattr(ephe_cli, "PROJECT_ROOT", tmp_path)
    (tmp_path / "plugins").mkdir()
    report = [
        {"plugin": "a", "cases": 6, "issues": []},
        {"plugin": "b", "cases": 3, "issues": ["only 3 cases (< 6)"]},
    ]
    monkeypatch.setattr(pg, "verify_all", lambda _d: report)
    assert ephe_cli.cmd_bench(_parser().parse_args(["bench"])) == 1
    out = capsys.readouterr().out
    assert "only 3 cases" in out
    monkeypatch.setattr(pg, "verify_all", lambda _d: report[:1])
    assert ephe_cli.cmd_bench(_parser().parse_args(["bench"])) == 0


def test_cmd_bench_run_gate(monkeypatch, capsys, tmp_path):
    import core.plugin_golden as pg

    monkeypatch.setattr(ephe_cli, "PROJECT_ROOT", tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    (plugins / "good").mkdir()
    (plugins / "good" / "ephe-plugin.json").write_text("{}")

    monkeypatch.setattr(
        pg, "pass3_matrix",
        lambda _pdir, runs, report=None: [{"id": "c1", "passes": 3, "pass3": True}],
    )
    assert ephe_cli.cmd_bench(_parser().parse_args(["bench", "--run", "good"])) == 0
    assert "Gate passed" in capsys.readouterr().out

    # an explicitly named non-plugin dir is a gate failure
    (plugins / "junk").mkdir()
    assert ephe_cli.cmd_bench(_parser().parse_args(["bench", "--run", "junk"])) == 1
    assert "not a product plugin" in capsys.readouterr().out

    # the default (no names) picks up only real plugin dirs
    assert ephe_cli.cmd_bench(_parser().parse_args(["bench", "--run"])) == 0
    capsys.readouterr()

    monkeypatch.setattr(
        pg, "pass3_matrix",
        lambda _pdir, runs, report=None: [{"id": "c1", "passes": 2, "pass3": False}],
    )
    assert ephe_cli.cmd_bench(_parser().parse_args(["bench", "--run", "good"])) == 1
    assert "Gate FAILED" in capsys.readouterr().out


# session


def _patch_sessions(monkeypatch, tmp_path):
    from core import multi_session as ms

    d = tmp_path / "sessions"
    d.mkdir()
    monkeypatch.setattr(ms, "SESSIONS_DIR", d)
    monkeypatch.setattr(ms, "REGISTRY_FILE", d / "registry.json")
    monkeypatch.setattr(ms, "LEGACY_FILE", d / "default.json")
    return ms


def test_cmd_session_full_cycle(monkeypatch, capsys, tmp_path):
    ms = _patch_sessions(monkeypatch, tmp_path)
    p = _parser()

    assert ephe_cli.cmd_session(p.parse_args(["session", "list"])) == 0
    assert "No sessions" in capsys.readouterr().out
    assert ephe_cli.cmd_session(p.parse_args(["session", "list", "--json"])) == 0
    assert json.loads(capsys.readouterr().out) == []

    assert ephe_cli.cmd_session(p.parse_args(["session", "new"])) == 2
    capsys.readouterr()
    assert ephe_cli.cmd_session(p.parse_args(["session", "new", "--title", "A", "--json"])) == 0
    a = json.loads(capsys.readouterr().out)
    assert ephe_cli.cmd_session(p.parse_args(["session", "new", "--title", "B"])) == 0
    capsys.readouterr()

    assert len(ms.list_sessions()) == 2
    assert ephe_cli.cmd_session(p.parse_args(["session", "list"])) == 0
    assert "Sessions (newest first)" in capsys.readouterr().out

    assert ephe_cli.cmd_session(p.parse_args(["session", "switch"])) == 2
    capsys.readouterr()
    assert ephe_cli.cmd_session(p.parse_args(["session", "switch", "--id", "deadbeef"])) == 2
    capsys.readouterr()
    assert ephe_cli.cmd_session(p.parse_args(["session", "switch", "--id", a["id"], "--json"])) == 0
    assert json.loads(capsys.readouterr().out)["active_id"] == a["id"]
    assert ephe_cli.cmd_session(p.parse_args(["session", "switch", "--id", a["id"]])) == 0
    capsys.readouterr()

    assert ephe_cli.cmd_session(p.parse_args(["session", "rm"])) == 2
    capsys.readouterr()
    assert ephe_cli.cmd_session(p.parse_args(["session", "rm", "--id", "deadbeef"])) == 2
    capsys.readouterr()
    assert ephe_cli.cmd_session(p.parse_args(["session", "rm", "--id", a["id"], "--json"])) == 0
    assert json.loads(capsys.readouterr().out)["deleted"] == a["id"]

    assert ephe_cli.cmd_session(p.parse_args(["session", "rename"])) == 2
    capsys.readouterr()
    assert ephe_cli.cmd_session(p.parse_args(["session", "rename", "--id", "deadbeef", "--title", "x"])) == 2
    capsys.readouterr()
    assert ephe_cli.cmd_session(p.parse_args(["session", "rename", "--id", a["id"], "--title", "x"])) == 2
    capsys.readouterr()


def test_cmd_session_rename_ok(monkeypatch, capsys, tmp_path):
    _patch_sessions(monkeypatch, tmp_path)
    p = _parser()
    sid = _capture(p, ["session", "new", "--title", "Before", "--json"], capsys)["id"]
    entry = _capture(p, ["session", "rename", "--id", sid, "--title", "After", "--json"], capsys)
    assert entry["title"] == "After"
    assert ephe_cli.cmd_session(p.parse_args(["session", "rename", "--id", sid, "--title", "Z"])) == 0
    # human rm output
    assert ephe_cli.cmd_session(p.parse_args(["session", "rm", "--id", sid])) == 0
    assert "deleted" in capsys.readouterr().out


def test_cmd_session_unknown_action(monkeypatch, capsys, tmp_path):
    _patch_sessions(monkeypatch, tmp_path)
    assert ephe_cli.cmd_session(argparse.Namespace(session_action="bogus", json=False)) == 2
    capsys.readouterr()


def _capture(p, argv, capsys):
    rc = ephe_cli.cmd_session(p.parse_args(argv))
    out = capsys.readouterr().out
    assert rc == 0
    return json.loads(out)


def test_cmd_session_import_error(monkeypatch, capsys):
    import core

    monkeypatch.delitem(sys.modules, "core.multi_session", raising=False)
    monkeypatch.delattr(core, "multi_session", raising=False)
    monkeypatch.setitem(sys.modules, "core.multi_session", None)
    assert ephe_cli.cmd_session(_parser().parse_args(["session", "list"])) == 1
    capsys.readouterr()


# plugin


def test_cmd_plugin_list(monkeypatch, capsys):
    import core.plugin_store as ps

    monkeypatch.setattr(
        ps, "load_catalog",
        lambda *a, **k: {"public": [{"name": "alpha", "version": "1.0", "enabled": True}],
                         "personal": [{"name": "beta", "enabled": False}]},
    )
    monkeypatch.setattr(ps, "load_registry", lambda *a, **k: [{"name": "alpha", "enabled": False}])
    assert ephe_cli.cmd_plugin(_parser().parse_args(["plugin", "list"])) == 0
    out = capsys.readouterr().out
    assert "PLUGIN" in out and "alpha" in out and "beta" in out


def test_cmd_plugin_toggle(monkeypatch, capsys):
    import core.plugin_lifecycle as lifecycle_module
    import core.plugin_runtime as runtime
    import core.skills as skills

    seen: dict = {}

    class FakeLifecycle:
        def set_enabled(self, pid, enabled, **kwargs):
            seen.update(pid=pid, enabled=enabled, **kwargs)
            state = "enabled" if enabled else "disabled"
            return type("Snapshot", (), {"state": type("State", (), {"value": state})()})()

    monkeypatch.setattr(runtime, "lifecycle", lambda *args, **kwargs: FakeLifecycle())
    monkeypatch.setattr(skills, "invalidate_skill_cache", lambda: seen.update(invalidated=True))
    p = _parser()
    assert ephe_cli.cmd_plugin(p.parse_args(["plugin", "enable", "alpha"])) == 0
    assert seen["enabled"] is True and seen["invalidated"] is True
    capsys.readouterr()
    assert ephe_cli.cmd_plugin(p.parse_args(["plugin", "disable", "alpha"])) == 0
    assert seen["enabled"] is False
    capsys.readouterr()

    def refuse(*args, **kwargs):
        raise lifecycle_module.LifecycleError("unknown_plugin", 404, "not installed")

    monkeypatch.setattr(runtime, "lifecycle", lambda *args, **kwargs: type("L", (), {"set_enabled": refuse})())
    assert ephe_cli.cmd_plugin(p.parse_args(["plugin", "enable", "alpha"])) == 1
    capsys.readouterr()


def test_cmd_plugin_install(monkeypatch, capsys):
    import core.plugin_market as pm

    monkeypatch.setattr(
        pm,
        "install_from_marketplace",
        lambda pid, **kwargs: {"status": "extracted", "version": "2.1"},
    )
    assert ephe_cli.cmd_plugin(_parser().parse_args(["plugin", "install", "alpha"])) == 0
    assert "installed: alpha" in capsys.readouterr().out
    monkeypatch.setattr(
        pm,
        "install_from_marketplace",
        lambda pid, **kwargs: {"status": "quarantined", "error": "sha"},
    )
    assert ephe_cli.cmd_plugin(_parser().parse_args(["plugin", "install", "alpha"])) == 1
    capsys.readouterr()


def test_cmd_plugin_unknown_action(capsys):
    assert ephe_cli.cmd_plugin(argparse.Namespace(action="frob", plugin_id="x")) == 2
    capsys.readouterr()


# import


def test_cmd_import_plan_and_apply(monkeypatch, capsys, tmp_path):
    import core.importer as imp

    src = tmp_path / "src"
    src.mkdir()
    p = _parser()
    assert ephe_cli.cmd_import(p.parse_args(["import", str(tmp_path / "nope")])) == 2
    capsys.readouterr()

    plan = {
        "persona": {"found": True, "source_file": ".cursorrules"},
        "skills": [{"name": "s1"}],
        "mcp": {"servers": ["fetch"]},
        "settings": {"mapped": ["theme"], "unmapped_keys": ["legacy"]},
    }
    monkeypatch.setattr(imp, "build_import_plan", lambda _s: plan)
    assert ephe_cli.cmd_import(p.parse_args(["import", str(src)])) == 0
    out = capsys.readouterr().out
    assert "Import plan" in out and "s1" in out and "legacy" in out

    empty = {
        "persona": {"found": False, "source_file": ""},
        "skills": [],
        "mcp": {"servers": []},
        "settings": {"mapped": [], "unmapped_keys": []},
    }
    monkeypatch.setattr(imp, "build_import_plan", lambda _s: empty)
    assert ephe_cli.cmd_import(p.parse_args(["import", str(src)])) == 0
    assert "not found" in capsys.readouterr().out

    result = {"persona": True, "skills": ["s1"], "mcp_servers": ["fetch"], "settings": ["theme"]}
    monkeypatch.setattr(imp, "apply_import", lambda _s: result)
    assert ephe_cli.cmd_import(p.parse_args(["import", str(src), "--apply"])) == 0
    assert "Applied" in capsys.readouterr().out


# tool


def test_cmd_tool_bad_arg(capsys):
    assert ephe_cli.cmd_tool(_parser().parse_args(["tool", "read_file", "--arg", "noequals"])) == 2
    capsys.readouterr()


def test_cmd_tool_unknown_tool(monkeypatch, capsys):
    import core.tools.registry as reg

    monkeypatch.setattr(ephe_cli, "_init_cli_mcp", _async_ok)
    monkeypatch.setattr(reg, "get_tool_schemas", lambda: [])
    assert ephe_cli.cmd_tool(_parser().parse_args(["tool", "ghost"])) == 1
    capsys.readouterr()


def test_cmd_tool_executes_then_denies(monkeypatch, capsys):
    import core.tools.registry as reg

    monkeypatch.setattr(ephe_cli, "_init_cli_mcp", _async_ok)
    monkeypatch.setattr(reg, "get_tool_schemas", lambda: [{"function": {"name": "read_file"}}])

    async def ok(_name, _targs, policy=None):
        return "tool output"

    monkeypatch.setattr(reg, "execute_tool", ok)
    assert ephe_cli.cmd_tool(_parser().parse_args(["tool", "read_file", "--json"])) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["tool"] == "read_file" and data["result"] == "tool output"

    async def denied(_name, _targs, policy=None):
        return "[Denied] needs approval"

    monkeypatch.setattr(reg, "execute_tool", denied)
    assert ephe_cli.cmd_tool(_parser().parse_args(["tool", "read_file", "--yes"])) == 1
    capsys.readouterr()


def test_cmd_tool_exception(monkeypatch, capsys):
    import core.tools.registry as reg

    monkeypatch.setattr(ephe_cli, "_init_cli_mcp", _async_ok)
    monkeypatch.setattr(reg, "get_tool_schemas", lambda: [{"function": {"name": "read_file"}}])

    async def boom(_name, _targs, policy=None):
        raise RuntimeError("tool blew up")

    monkeypatch.setattr(reg, "execute_tool", boom)
    assert ephe_cli.cmd_tool(_parser().parse_args(["tool", "read_file"])) == 1
    capsys.readouterr()


def test_cmd_tool_systemexit_is_reraised(monkeypatch):
    import core.tools.registry as reg

    monkeypatch.setattr(ephe_cli, "_init_cli_mcp", _async_ok)
    monkeypatch.setattr(reg, "get_tool_schemas", lambda: [{"function": {"name": "read_file"}}])

    async def stop(_name, _targs, policy=None):
        raise SystemExit(4)

    monkeypatch.setattr(reg, "execute_tool", stop)
    with pytest.raises(SystemExit) as exc:
        ephe_cli.cmd_tool(_parser().parse_args(["tool", "read_file"]))
    assert exc.value.code == 4


# serve


def test_cmd_serve_lan_generates_token(monkeypatch, capsys):
    import uvicorn

    import server.openai as so

    monkeypatch.delenv("EPHE_SERVE_TOKEN", raising=False)
    monkeypatch.setattr(ephe_cli, "engine_for_headless_run", lambda _a, _m: _FakeChoice(ephe_cli.LOCAL_OLLAMA, "m"))
    monkeypatch.setattr(so, "create_openai_app", lambda api_token=None: types.SimpleNamespace(docs_url="/docs", openapi_url="/openapi.json"))
    monkeypatch.setattr(uvicorn, "run", lambda *_a, **_k: None)
    assert ephe_cli.cmd_serve(_parser().parse_args(["serve", "--lan"])) == 0
    out = capsys.readouterr().out
    assert "X-Auth-Token" in out and "0.0.0.0" in out


# desktop


def _patch_desktop_app(monkeypatch, tmp_path):
    app = tmp_path / "app" / "src-tauri"
    app.mkdir(parents=True)
    (app / "tauri.conf.json").write_text("{}")
    monkeypatch.setattr(ephe_cli, "PROJECT_ROOT", tmp_path)


def test_cmd_desktop_no_npm(monkeypatch, capsys):
    monkeypatch.setattr(ephe_cli.shutil, "which", lambda _n: None)
    assert ephe_cli.cmd_desktop(_parser().parse_args(["desktop"])) == 1
    assert "npm not found" in capsys.readouterr().out


def test_cmd_desktop_no_tauri_conf(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(ephe_cli.shutil, "which", lambda n: f"/usr/bin/{n}")
    monkeypatch.setattr(ephe_cli, "PROJECT_ROOT", tmp_path)
    assert ephe_cli.cmd_desktop(_parser().parse_args(["desktop"])) == 1
    assert "tauri.conf.json missing" in capsys.readouterr().out


def test_cmd_desktop_dev(monkeypatch, capsys, tmp_path):
    _patch_desktop_app(monkeypatch, tmp_path)
    monkeypatch.setattr(ephe_cli.shutil, "which", lambda n: f"/usr/bin/{n}")
    monkeypatch.setattr(ephe_cli, "_run", lambda *_a, **_k: types.SimpleNamespace(returncode=0))
    monkeypatch.setattr(ephe_cli, "_ensure_backend", lambda: True)
    assert ephe_cli.cmd_desktop(_parser().parse_args(["desktop", "--dev"])) == 0
    assert "Backend ready" in capsys.readouterr().out
    monkeypatch.setattr(ephe_cli, "_ensure_backend", lambda: False)
    assert ephe_cli.cmd_desktop(_parser().parse_args(["desktop", "--dev"])) == 0
    assert "unreachable" in capsys.readouterr().out


def test_cmd_desktop_cargo_missing(monkeypatch, capsys, tmp_path):
    _patch_desktop_app(monkeypatch, tmp_path)
    monkeypatch.setattr(ephe_cli.shutil, "which", lambda n: "/usr/bin/npm" if n == "npm" else None)
    assert ephe_cli.cmd_desktop(_parser().parse_args(["desktop"])) == 1
    assert "cargo not found" in capsys.readouterr().out


def test_cmd_desktop_build_no_bundle(monkeypatch, capsys, tmp_path):
    _patch_desktop_app(monkeypatch, tmp_path)
    monkeypatch.setattr(ephe_cli.shutil, "which", lambda n: f"/usr/bin/{n}")
    monkeypatch.setattr(ephe_cli, "_run", lambda *_a, **_k: types.SimpleNamespace(returncode=0))
    monkeypatch.setattr(ephe_cli, "_desktop_bundle_path", lambda _d: None)
    monkeypatch.setattr(ephe_cli.sys, "platform", "linux")
    assert ephe_cli.cmd_desktop(_parser().parse_args(["desktop"])) == 0
    assert "no bundle found" in capsys.readouterr().out


def test_cmd_desktop_build_fails(monkeypatch, capsys, tmp_path):
    _patch_desktop_app(monkeypatch, tmp_path)
    monkeypatch.setattr(ephe_cli.shutil, "which", lambda n: f"/usr/bin/{n}")
    monkeypatch.setattr(ephe_cli, "_run", lambda *_a, **_k: types.SimpleNamespace(returncode=2))
    monkeypatch.setattr(ephe_cli.sys, "platform", "linux")
    assert ephe_cli.cmd_desktop(_parser().parse_args(["desktop"])) == 2
    capsys.readouterr()


def test_cmd_desktop_darwin_install(monkeypatch, capsys, tmp_path):
    _patch_desktop_app(monkeypatch, tmp_path)
    bundle = tmp_path / "Ephe.app"
    installed = tmp_path / "Applications" / "Ephe.app"
    monkeypatch.setattr(ephe_cli.shutil, "which", lambda n: f"/usr/bin/{n}")
    monkeypatch.setattr(ephe_cli, "_run", lambda *_a, **_k: types.SimpleNamespace(returncode=0))
    monkeypatch.setattr(ephe_cli.sys, "platform", "darwin")
    monkeypatch.setattr(ephe_cli, "_desktop_bundle_path", lambda _d: bundle)
    monkeypatch.setattr(ephe_cli, "_schreibe_desktop_konfig", lambda *_a, **_k: None)
    monkeypatch.setattr(ephe_cli, "_install_desktop_bundle", lambda *_a, **_k: installed)
    monkeypatch.setattr(ephe_cli, "_ensure_backend", lambda: True)
    monkeypatch.setattr(ephe_cli.subprocess, "run", lambda *_a, **_k: types.SimpleNamespace(returncode=0))
    assert ephe_cli.cmd_desktop(_parser().parse_args(["desktop"])) == 0
    assert "installed to" in capsys.readouterr().out

    def boom(*_a, **_k):
        raise OSError("no permission")

    monkeypatch.setattr(ephe_cli, "_install_desktop_bundle", boom)
    monkeypatch.setattr(ephe_cli, "_ensure_backend", lambda: False)
    assert ephe_cli.cmd_desktop(_parser().parse_args(["desktop"])) == 0
    out = capsys.readouterr().out
    assert "Could not install" in out and "unreachable" in out


# backend helpers


def test_backend_listening_closed_port():
    assert ephe_cli._backend_listening(port=1, host="127.0.0.1") is False


def test_backend_listening_oserror(monkeypatch):
    import socket as _socket

    class BadSocket:
        def __enter__(self):
            raise OSError("nope")

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(_socket, "socket", lambda *_a, **_k: BadSocket())
    assert ephe_cli._backend_listening() is False


def test_spawn_backend_writes_log(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(ephe_cli, "PROJECT_ROOT", tmp_path)
    calls: list[list[str]] = []
    monkeypatch.setattr(ephe_cli.subprocess, "Popen", lambda cmd, **_k: calls.append(cmd))
    ephe_cli._spawn_backend(9100)
    assert calls and calls[0][-1] == "9100"
    assert (tmp_path / ".ephe" / "logs" / "desktop-backend.log").exists()


def test_ensure_backend_ready(monkeypatch):
    monkeypatch.setattr(ephe_cli, "_backend_listening", lambda *_a, **_k: True)
    assert ephe_cli._ensure_backend() is True


def test_ensure_backend_spawn_oserror(monkeypatch):
    monkeypatch.setattr(ephe_cli, "_backend_listening", lambda *_a, **_k: False)

    def boom(port=8765):
        raise OSError("spawn failed")

    monkeypatch.setattr(ephe_cli, "_spawn_backend", boom)
    assert ephe_cli._ensure_backend() is False


def test_ensure_backend_waits_then_ready(monkeypatch):
    seq = iter([False, False, True])
    monkeypatch.setattr(ephe_cli, "_backend_listening", lambda *_a, **_k: next(seq))
    monkeypatch.setattr(ephe_cli, "_spawn_backend", lambda port=8765: None)
    monkeypatch.setattr(ephe_cli.time, "sleep", lambda *_a: None)
    assert ephe_cli._ensure_backend(timeout_s=5.0) is True


def test_ensure_backend_timeout(monkeypatch):
    monkeypatch.setattr(ephe_cli, "_backend_listening", lambda *_a, **_k: False)
    monkeypatch.setattr(ephe_cli, "_spawn_backend", lambda port=8765: None)
    assert ephe_cli._ensure_backend(timeout_s=0.0) is False


def test_app_stempel_variants(tmp_path):
    assert ephe_cli._app_stempel(tmp_path / "nope") == ""
    empty = tmp_path / "E.app" / "Contents" / "MacOS"
    empty.mkdir(parents=True)
    assert ephe_cli._app_stempel(tmp_path / "E.app") == ""
    (empty / "Ephe").write_bytes(b"abc")
    assert len(ephe_cli._app_stempel(tmp_path / "E.app")) == 64


# small helpers


def test_version_tuple():
    assert ephe_cli._version_tuple("1.2.3") == (1, 2, 3)
    assert ephe_cli._version_tuple("2.0") == (2, 0, 0)
    assert ephe_cli._version_tuple("1.0.0-rc1") == (1, 0, 0)
    assert ephe_cli._version_tuple("") == (0, 0, 0)


def test_cell_pinned_ceiling(monkeypatch):
    import importlib.metadata as im

    class Meta:
        def get_all(self, _key):
            return ["ephemora-cell>=0.2,<0.4"]

    monkeypatch.setattr(im, "metadata", lambda _name: Meta())
    assert ephe_cli._cell_pinned_ceiling() == "0.4"

    class MetaNoPin:
        def get_all(self, _key):
            return ["ephemora-cell>=0.2", "other>=1"]

    monkeypatch.setattr(im, "metadata", lambda _name: MetaNoPin())
    assert ephe_cli._cell_pinned_ceiling() is None


def test_local_chosen_tag_remote_engine(monkeypatch):
    import core.engine_config as ec

    monkeypatch.setattr(ec, "resolve_engine_choice", lambda **_k: _FakeChoice(ephe_cli.OPENAI_COMPAT, "gpt"))
    assert ephe_cli._local_chosen_tag() == ""


def test_doctor_image_endpoint_without_base(monkeypatch):
    import core.image_config as ic
    import core.tools.image_tools as it

    monkeypatch.delenv("EPHE_IMAGE_BASE_URL", raising=False)
    monkeypatch.setattr(ic, "load_image_config", lambda: types.SimpleNamespace(base_url=""))
    monkeypatch.setattr(it, "_image_endpoint", lambda: ("", "", ""))
    ok, detail = ephe_cli._doctor_image_endpoint()
    assert ok is False and "no endpoint" in detail


def test_init_cli_mcp_normal_and_fallback(monkeypatch):
    import asyncio
    import core.mcp_config as mc

    async def ok():
        return ["srv"]

    monkeypatch.setattr(mc, "init_mcp_from_config", ok)
    assert asyncio.run(ephe_cli._init_cli_mcp()) == ["srv"]

    async def boom():
        raise RuntimeError("no mcp")

    monkeypatch.setattr(mc, "init_mcp_from_config", boom)
    assert asyncio.run(ephe_cli._init_cli_mcp()) == []


def test_run_doctor_repairs(monkeypatch):
    monkeypatch.setenv("OLLAMA_HOST", "http://weird.example:1")
    monkeypatch.setattr(ephe_cli, "_repair_repo", lambda: (True, "ok"))
    monkeypatch.setattr(ephe_cli, "_repair_dependencies", lambda: (True, "ok"))
    monkeypatch.setattr(ephe_cli, "ensure_pwa_built", lambda: True)
    reps = ephe_cli._run_doctor_repairs(_parser().parse_args(["doctor"]))
    names = [r[0] for r in reps]
    assert "Normalize OLLAMA_HOST" in names
    assert "Repair model" in names  # no --model -> reported as missing


def test_run_doctor_repairs_with_model(monkeypatch):
    monkeypatch.setattr(ephe_cli, "_repair_repo", lambda: (True, "ok"))
    monkeypatch.setattr(ephe_cli, "_repair_dependencies", lambda: (True, "ok"))
    monkeypatch.setattr(ephe_cli, "_ensure_model_ready_for_start", lambda _m: (True, "ready"))
    monkeypatch.setattr(ephe_cli, "ensure_pwa_built", lambda: True)
    reps = ephe_cli._run_doctor_repairs(_parser().parse_args(["doctor", "--model", "m"]))
    assert any(n == "Repair model m" for n, _ok, _d in reps)


# voice


def test_cmd_voice_list_install_usage(monkeypatch, capsys):
    import core.voice_config as vc

    p = _parser()
    monkeypatch.setattr(vc, "piper_binary_available", lambda: True)
    monkeypatch.setattr(vc, "list_installed_piper_voices", lambda: ["de_DE-thorsten-medium"])
    assert ephe_cli.cmd_voice(p.parse_args(["voice", "list"])) == 0
    assert "Installed voices" in capsys.readouterr().out

    monkeypatch.setattr(vc, "list_installed_piper_voices", lambda: [])
    assert ephe_cli.cmd_voice(p.parse_args(["voice", "list"])) == 0
    assert "No voices" in capsys.readouterr().out

    monkeypatch.setattr(ephe_cli, "_download_piper_voice", lambda _name: None)
    assert ephe_cli.cmd_voice(p.parse_args(["voice", "install", "en_US-amy-medium"])) == 0
    assert "OK: en_US-amy-medium" in capsys.readouterr().out

    def boom(_name):
        raise RuntimeError("net down")

    monkeypatch.setattr(ephe_cli, "_download_piper_voice", boom)
    assert ephe_cli.cmd_voice(p.parse_args(["voice", "install", "x"])) == 1
    capsys.readouterr()

    assert ephe_cli.cmd_voice(argparse.Namespace(voice_command="weird", voices=[])) == 2
    capsys.readouterr()


# code / goal


def test_cmd_code_empty_task(capsys):
    assert ephe_cli.cmd_code(argparse.Namespace(task=[], model=None)) == 2
    capsys.readouterr()


def test_cmd_code_success(monkeypatch, capsys):
    import core.react as react

    _patch_run_record(monkeypatch)
    monkeypatch.setattr(ephe_cli, "engine_for_headless_run", lambda _a, _m: _FakeChoice(ephe_cli.LOCAL_OLLAMA, "m"))
    monkeypatch.setattr(ephe_cli, "_make_recorder", lambda *_a, **_k: _Rec())
    monkeypatch.setattr(ephe_cli, "_init_cli_mcp", _async_ok)

    async def fake_loop(**_k):
        return "answer text"

    monkeypatch.setattr(react, "react_loop", fake_loop)
    assert ephe_cli.cmd_code(_parser().parse_args(["code", "do", "it", "--json"])) == 0
    assert json.loads(capsys.readouterr().out)["answer"] == "answer text"


def test_cmd_code_loop_raises(monkeypatch, capsys):
    import core.react as react

    _patch_run_record(monkeypatch)
    monkeypatch.setattr(ephe_cli, "engine_for_headless_run", lambda _a, _m: _FakeChoice(ephe_cli.LOCAL_OLLAMA, "m"))
    monkeypatch.setattr(ephe_cli, "_make_recorder", lambda *_a, **_k: _Rec())
    monkeypatch.setattr(ephe_cli, "_init_cli_mcp", _async_ok)

    async def boom(**_k):
        raise RuntimeError("loop died")

    monkeypatch.setattr(react, "react_loop", boom)
    with pytest.raises(RuntimeError):
        ephe_cli.cmd_code(_parser().parse_args(["code", "x", "--json"]))
    capsys.readouterr()


def test_cmd_goal_empty(capsys):
    assert ephe_cli.cmd_goal(argparse.Namespace(goal_task=[], check=None, max_turns=10)) == 2
    capsys.readouterr()


def _patch_goal(monkeypatch, outcome=None, raises=False):
    import core.goal_loop as gl

    _patch_run_record(monkeypatch)
    monkeypatch.setattr(ephe_cli, "GoalRunner", None)  # force the core.goal_loop import path
    monkeypatch.setattr(ephe_cli, "engine_for_headless_run", lambda _a, _m: _FakeChoice(ephe_cli.LOCAL_OLLAMA, "m"))
    monkeypatch.setattr(ephe_cli, "_make_recorder", lambda *_a, **_k: _Rec())
    monkeypatch.setattr(ephe_cli, "_init_cli_mcp", _async_ok)

    class Runner:
        def __init__(self, **_k):
            pass

        async def run(self, _task):
            if raises:
                raise RuntimeError("goal died")
            return outcome

    monkeypatch.setattr(gl, "GoalRunner", Runner)


def test_cmd_goal_success_and_failure(monkeypatch, capsys):
    ok = types.SimpleNamespace(answer="done", success=True, turns=2, check_output="all green")
    _patch_goal(monkeypatch, outcome=ok)
    assert ephe_cli.cmd_goal(_parser().parse_args(["goal", "win", "--json"])) == 0
    capsys.readouterr()

    bad = types.SimpleNamespace(answer="", success=False, turns=3, check_output="1 failed")
    _patch_goal(monkeypatch, outcome=bad)
    assert ephe_cli.cmd_goal(_parser().parse_args(["goal", "win", "--json"])) == 1
    capsys.readouterr()


def test_cmd_goal_run_raises(monkeypatch, capsys):
    _patch_goal(monkeypatch, raises=True)
    with pytest.raises(RuntimeError):
        ephe_cli.cmd_goal(_parser().parse_args(["goal", "x", "--json"]))
    capsys.readouterr()


# start


def _patch_start_common(monkeypatch, tmp_path):
    _patch_ephemeris(monkeypatch)
    monkeypatch.setattr(ephe_cli, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(ephe_cli, "ensure_pwa_built", lambda: True)


def test_cmd_start_reload_and_run(monkeypatch, tmp_path, capsys):
    _patch_start_common(monkeypatch, tmp_path)
    monkeypatch.setattr(ephe_cli, "resolve_engine_choice", lambda **_k: None)
    seen: list[list[str]] = []
    monkeypatch.setattr(
        ephe_cli, "_run",
        lambda cmd, **_k: (seen.append(cmd), types.SimpleNamespace(returncode=0))[1],
    )
    assert ephe_cli.cmd_start(_parser().parse_args(["start", "--reload", "--port", "9111"])) == 0
    assert "--reload" in seen[0]
    capsys.readouterr()


def test_cmd_start_engine_not_configured(monkeypatch, tmp_path, capsys):
    _patch_start_common(monkeypatch, tmp_path)

    def raise_unconfigured(**_k):
        raise SystemExit()

    monkeypatch.setattr(ephe_cli, "resolve_engine_choice", raise_unconfigured)
    monkeypatch.setattr(ephe_cli, "_run", lambda *_a, **_k: types.SimpleNamespace(returncode=0))
    assert ephe_cli.cmd_start(_parser().parse_args(["start"])) == 0
    assert "No engine configured" in capsys.readouterr().out


def test_cmd_start_incomplete_engine_falls_back_to_setup(monkeypatch, tmp_path, capsys):
    """A persisted openai_compatible choice without api_url reaches setup.

    The choice is real, so `apply_env` raises the same EngineNotConfigured the start path
    sees on a half-written engine.json. The CLI has to name the missing field and keep
    going; the server then resolves the same incomplete choice and enters setup mode.
    """
    from core.engine_config import EngineChoice

    _patch_start_common(monkeypatch, tmp_path)
    choice = EngineChoice(provider=ephe_cli.OPENAI_COMPAT, model="m", api_url=None)
    monkeypatch.setattr(ephe_cli, "resolve_engine_choice", lambda **_k: choice)
    probed: list[tuple] = []
    monkeypatch.setattr(
        ephe_cli, "_probe_active_remote_engine",
        lambda *args, **kwargs: probed.append((args, kwargs)),
    )
    seen: dict = {}
    monkeypatch.setattr(
        ephe_cli, "_run",
        lambda cmd, env=None, **_k: (seen.update(env=env), types.SimpleNamespace(returncode=0))[1],
    )

    assert ephe_cli.cmd_start(_parser().parse_args(["start"])) == 0
    out = capsys.readouterr().out
    assert "✗" in out
    assert "api_url" in out
    assert "Fix:" in out
    # The readiness probe belongs to a complete choice; the fallback must not reach it.
    assert probed == []
    assert seen["env"].get("EPHE_OPENAI_COMPAT_BASE_URL") is None


def test_cmd_start_refuses_an_unbound_engine_key(monkeypatch, tmp_path, capsys):
    """A mismatched binding ends the start before the server is spawned."""
    from core import engine_config

    _patch_start_common(monkeypatch, tmp_path)
    choice = _FakeChoice(ephe_cli.OPENAI_COMPAT, "gpt", api_url="http://remote/v1")
    monkeypatch.setattr(ephe_cli, "resolve_engine_choice", lambda **_k: choice)

    def refuse(_choice):
        raise engine_config.EngineKeyMismatch("the stored engine key is bound to another engine")

    monkeypatch.setattr(engine_config, "assert_engine_key_binding", refuse)
    started: list[tuple] = []
    monkeypatch.setattr(
        ephe_cli, "_run",
        lambda *a, **k: (started.append(a), types.SimpleNamespace(returncode=0))[1],
    )

    assert ephe_cli.cmd_start(_parser().parse_args(["start"])) == 1
    out = capsys.readouterr().out
    assert "bound to another engine" in out
    assert "Fix: Re-enter the key" in out
    assert started == []


def test_cmd_start_remote_probe(monkeypatch, tmp_path, capsys):
    _patch_start_common(monkeypatch, tmp_path)
    monkeypatch.setattr(
        ephe_cli, "resolve_engine_choice",
        lambda **_k: _FakeChoice(ephe_cli.OPENAI_COMPAT, "gpt", api_url="http://remote/v1"),
    )
    monkeypatch.setattr(ephe_cli, "_run", lambda *_a, **_k: types.SimpleNamespace(returncode=0))
    monkeypatch.setattr(ephe_cli, "_probe_remote_engine", lambda _u, _m: (True, "reachable"))
    assert ephe_cli.cmd_start(_parser().parse_args(["start"])) == 0
    assert "reachable" in capsys.readouterr().out
    monkeypatch.setattr(ephe_cli, "_probe_remote_engine", lambda _u, _m: (False, "unreachable"))
    assert ephe_cli.cmd_start(_parser().parse_args(["start"])) == 0
    assert "starts anyway" in capsys.readouterr().out


def test_cmd_start_local_ollama_service_states(monkeypatch, tmp_path, capsys):
    _patch_start_common(monkeypatch, tmp_path)
    monkeypatch.setattr(ephe_cli, "resolve_engine_choice", lambda **_k: _FakeChoice(ephe_cli.LOCAL_OLLAMA, "m"))
    monkeypatch.setattr(ephe_cli, "_run", lambda *_a, **_k: types.SimpleNamespace(returncode=0))
    p = _parser()

    monkeypatch.setattr(ephe_cli, "_ensure_ollama_service", lambda: (True, "ok"))
    monkeypatch.setattr(ephe_cli, "_model_installed", lambda _m: True)
    monkeypatch.setattr(ephe_cli, "_model_loadable", lambda _m: (True, "loads"))
    assert ephe_cli.cmd_start(p.parse_args(["start"])) == 0
    capsys.readouterr()

    monkeypatch.setattr(ephe_cli, "_model_installed", lambda _m: False)
    assert ephe_cli.cmd_start(p.parse_args(["start"])) == 0
    assert "not installed" in capsys.readouterr().out

    monkeypatch.setattr(ephe_cli, "_ensure_ollama_service", lambda: (False, "not running"))
    assert ephe_cli.cmd_start(p.parse_args(["start"])) == 0
    assert "Ollama Service" in capsys.readouterr().out


def test_cmd_start_open_waits_for_health(monkeypatch, tmp_path, capsys):
    _patch_start_common(monkeypatch, tmp_path)
    monkeypatch.setattr(ephe_cli, "resolve_engine_choice", lambda **_k: None)
    monkeypatch.setattr(ephe_cli.subprocess, "Popen", lambda *_a, **_k: types.SimpleNamespace(wait=lambda: 0))
    monkeypatch.setattr(ephe_cli.time, "sleep", lambda *_a: None)
    opened: list[str] = []
    monkeypatch.setattr(ephe_cli.webbrowser, "open", lambda url: opened.append(url))

    monkeypatch.setattr(ephe_cli, "_json_get", lambda _u, **_k: {"ok": True})
    assert ephe_cli.cmd_start(_parser().parse_args(["start", "--open", "--port", "9111"])) == 0
    assert opened

    # health never answers -> the loop exhausts its 30 tries without opening
    opened.clear()
    monkeypatch.setattr(ephe_cli, "_json_get", lambda _u, **_k: None)
    assert ephe_cli.cmd_start(_parser().parse_args(["start", "--open", "--port", "9111"])) == 0
    assert opened == []
    capsys.readouterr()


# doctor (optional checks + json/fix output)


def _patch_doctor_base(monkeypatch, tmp_path, *, installed=True, loadable=(True, "ok"), skills_lock=True):
    monkeypatch.setattr(ephe_cli, "PROJECT_ROOT", tmp_path)
    (tmp_path / "app").mkdir(exist_ok=True)
    (tmp_path / "app" / "index.html").write_text("x")
    if skills_lock:
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "generate_skills_lock.py").write_text("def verify(root):\n    return True, []\n")
    monkeypatch.setattr(ephe_cli, "_ollama_binary", lambda: "/usr/local/bin/ollama")
    monkeypatch.setattr(ephe_cli, "_local_chosen_tag", lambda: "")
    # The local world is faked above, so the engine seam is pinned too: a machine
    # with an engine.json would otherwise send doctor down its remote path.
    monkeypatch.setattr(ephe_cli, "_active_engine_choice", lambda: None)
    monkeypatch.setattr(ephe_cli, "_doctor_image_endpoint", lambda: (True, "ok"))
    monkeypatch.setattr(ephe_cli, "_doctor_voice", lambda: (True, "ok"))
    monkeypatch.setattr(ephe_cli, "_json_get", lambda _u, **_k: {"models": [{"name": "m"}]})
    monkeypatch.setattr(ephe_cli, "_model_installed", lambda _m: installed)
    monkeypatch.setattr(ephe_cli, "_model_loadable", lambda _m: loadable)
    monkeypatch.setattr(ephe_cli, "_cell_pinned_ceiling", lambda: None)
    # keep the PyPI watch off the network
    import importlib.metadata as im
    import urllib.request as ur

    monkeypatch.setattr(im, "version", lambda _n: "0.2.0")
    monkeypatch.setattr(ur, "urlopen", _raise_urlopen)


def _raise_urlopen(*_a, **_k):
    raise OSError("offline")


class _Resp:
    def __init__(self, payload: dict) -> None:
        self._b = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def read(self) -> bytes:
        return self._b


def test_cmd_doctor_model_installed_service_down(monkeypatch, capsys, tmp_path):
    _patch_doctor_base(monkeypatch, tmp_path, installed=True)
    monkeypatch.setattr(ephe_cli, "_json_get", lambda _u, **_k: None)
    assert ephe_cli.cmd_doctor(_parser().parse_args(["doctor", "--model", "gemma:2b"])) == 1
    assert "start Ollama to verify" in capsys.readouterr().out


def test_cmd_doctor_cell_watch_branches(monkeypatch, capsys, tmp_path):
    import urllib.request as ur

    _patch_doctor_base(monkeypatch, tmp_path)
    p = _parser()

    # installed == latest
    monkeypatch.setattr(ur, "urlopen", lambda *_a, **_k: _Resp({"info": {"version": "0.2.0", "license": "BUSL"}}))
    assert ephe_cli.cmd_doctor(p.parse_args(["doctor", "--model", "m"])) == 0
    assert "PyPI current" in capsys.readouterr().out

    # latest above the pinned ceiling
    import importlib.metadata as im

    monkeypatch.setattr(im, "version", lambda _n: "0.2.0")
    monkeypatch.setattr(ephe_cli, "_cell_pinned_ceiling", lambda: "0.4")
    monkeypatch.setattr(ur, "urlopen", lambda *_a, **_k: _Resp({"info": {"version": "0.5.0", "license": "BUSL"}}))
    assert ephe_cli.cmd_doctor(p.parse_args(["doctor", "--model", "m"])) == 0
    assert "above the pinned" in capsys.readouterr().out

    # an older install is informational only
    monkeypatch.setattr(im, "version", lambda _n: "0.1.0")
    monkeypatch.setattr(ur, "urlopen", lambda *_a, **_k: _Resp({"info": {"version": "0.2.0"}}))
    ephe_cli.cmd_doctor(p.parse_args(["doctor", "--model", "m"]))
    capsys.readouterr()


def test_cmd_doctor_optional_check_exceptions(monkeypatch, capsys, tmp_path):
    import core.cell_policy as cp
    import core.environment_mirror as em

    _patch_doctor_base(monkeypatch, tmp_path, skills_lock=False)

    def boom(*_a, **_k):
        raise RuntimeError("broken")

    monkeypatch.setattr(cp, "doctor_snapshot", boom)
    monkeypatch.setattr(em, "installed_tools", boom)
    # PROJECT_ROOT has no scripts/generate_skills_lock.py -> the lock check also fails soft
    assert ephe_cli.cmd_doctor(_parser().parse_args(["doctor", "--model", "m"])) in (0, 1)
    out = capsys.readouterr().out
    assert "cell check skipped" in out and "mirror skipped" in out and "skills_lock_mismatch" in out


def test_cmd_doctor_json_and_fix(monkeypatch, capsys, tmp_path):
    _patch_doctor_base(monkeypatch, tmp_path)
    monkeypatch.setattr(ephe_cli, "_run_doctor_repairs", lambda _a: [("Repair repo", True, "clean")])
    p = _parser()

    ephe_cli.cmd_doctor(p.parse_args(["doctor", "--model", "m", "--json", "--fix"]))
    data = json.loads(capsys.readouterr().out)
    assert data["repairs"][0]["name"] == "Repair repo"

    ephe_cli.cmd_doctor(p.parse_args(["doctor", "--model", "m", "--fix"]))
    out = capsys.readouterr().out
    assert "Repair repo" in out and "Summary:" in out


# main dispatch


def test_main_reraises_systemexit_from_command(monkeypatch):
    def stop(_args):
        raise SystemExit(7)

    monkeypatch.setattr(ephe_cli, "cmd_doctor", stop)
    monkeypatch.setattr(sys, "argv", ["ephe", "doctor"])
    with pytest.raises(SystemExit) as exc:
        ephe_cli.main()
    assert exc.value.code == 7


# doctor: image-endpoint + voice probes (the branches the base fixture stubs out)


def test_doctor_image_endpoint_probe_cases(monkeypatch):
    import httpx

    import core.image_config as ic
    import core.tools.image_tools as it

    monkeypatch.setattr(ic, "load_image_config", lambda: types.SimpleNamespace(base_url=""))
    seen: dict = {}

    def get(url, headers=None, timeout=None):
        seen["url"] = url
        seen["headers"] = headers
        return types.SimpleNamespace(status_code=200)

    # (a) explicitly configured (env) with a key -> bearer header, reachable
    monkeypatch.setenv("EPHE_IMAGE_BASE_URL", "http://img.local/v1")
    monkeypatch.setattr(it, "_image_endpoint", lambda: ("http://img.local/v1", "sekret", "m"))
    monkeypatch.setattr(httpx, "get", get)
    ok, detail = ephe_cli._doctor_image_endpoint()
    assert ok is True and "explicitly configured" in detail
    assert seen["headers"] == {"Authorization": "Bearer sekret"}

    # (b) nothing explicit, chat-engine fallback still answers -> fallback source, no auth header
    monkeypatch.delenv("EPHE_IMAGE_BASE_URL", raising=False)
    monkeypatch.setattr(it, "_image_endpoint", lambda: ("http://chat.local/v1", "", "m"))
    ok, detail = ephe_cli._doctor_image_endpoint()
    assert ok is True and "fallback: active chat engine" in detail
    assert seen["headers"] == {}


def test_doctor_image_endpoint_not_reachable_and_suggestion(monkeypatch):
    import httpx

    import core.image_config as ic
    import core.tools.image_tools as it

    monkeypatch.setattr(ic, "load_image_config", lambda: types.SimpleNamespace(base_url=""))
    monkeypatch.delenv("EPHE_IMAGE_BASE_URL", raising=False)
    monkeypatch.setattr(it, "_image_endpoint", lambda: ("http://chat.local/v1", "", "m"))

    # not explicit, base dead, LocalAI detected on the default port -> suggestion
    def get_localai(url, headers=None, timeout=None):
        return types.SimpleNamespace(status_code=200 if url.startswith("http://127.0.0.1:8080") else 404)

    monkeypatch.setattr(httpx, "get", get_localai)
    ok, detail = ephe_cli._doctor_image_endpoint()
    assert ok is False and "LocalAI detected" in detail

    # explicitly configured but unreachable -> honest error (and the probe's exception path)
    monkeypatch.setenv("EPHE_IMAGE_BASE_URL", "http://img.local/v1")

    def boom(*_a, **_k):
        raise OSError("connection refused")

    monkeypatch.setattr(httpx, "get", boom)
    ok, detail = ephe_cli._doctor_image_endpoint()
    assert ok is False and "not reachable" in detail


def test_doctor_voice_engine_branches(monkeypatch):
    import core.transcribe as tr
    import core.voice_config as vc

    monkeypatch.setattr(tr, "is_whisper_available", lambda: True)
    monkeypatch.setattr(
        vc, "load_voice_config",
        lambda: types.SimpleNamespace(stt_model="small", stt_language="auto", piper_voice="de_DE-thorsten-medium", tts_engine="piper"),
    )
    monkeypatch.setattr(vc, "resolve_tts_engine", lambda: "piper")
    ok, detail = ephe_cli._doctor_voice()
    assert ok is True and detail.startswith("piper local")
    assert "whisper small/auto OK" in detail

    # edge fallback, explicit stt_language, whisper missing
    monkeypatch.setattr(
        vc, "load_voice_config",
        lambda: types.SimpleNamespace(stt_model="small", stt_language="de", piper_voice="v", tts_engine="auto"),
    )
    monkeypatch.setattr(vc, "resolve_tts_engine", lambda: "edge")
    monkeypatch.setattr(tr, "is_whisper_available", lambda: False)
    ok, detail = ephe_cli._doctor_voice()
    assert ok is True and "auto fallback" in detail and "whisper small/de missing" in detail

    # edge, opted-in (not auto)
    monkeypatch.setattr(
        vc, "load_voice_config",
        lambda: types.SimpleNamespace(stt_model="small", stt_language="auto", piper_voice="v", tts_engine="edge"),
    )
    ok, detail = ephe_cli._doctor_voice()
    assert ok is True and "Edge cloud fallback (opt-in)" in detail

    # no engine at all -> the RuntimeError is surfaced
    def no_engine():
        raise RuntimeError("no TTS engine")

    monkeypatch.setattr(vc, "resolve_tts_engine", no_engine)
    ok, detail = ephe_cli._doctor_voice()
    assert ok is False and detail == "no TTS engine"


# run records + coding human output


def test_make_recorder_reads_choice(monkeypatch):
    import core.run_evidence as re

    captured: dict = {}

    class Rec:
        def __init__(self, **kw):
            captured.update(kw)

    monkeypatch.setattr(re, "RunRecorder", Rec)
    monkeypatch.setattr(re, "new_turn_id", lambda ep: f"turn-{ep}")
    choice = _FakeChoice(ephe_cli.LOCAL_OLLAMA, "m", api_url="http://x/v1")
    rec = ephe_cli._make_recorder("code", task="do", choice=choice, gate_posture="g", rep=2)
    assert isinstance(rec, Rec)
    assert captured["provider"] == ephe_cli.LOCAL_OLLAMA and captured["model"] == "m"
    assert captured["api_url"] == "http://x/v1" and captured["entrypoint"] == "code"
    assert captured["turn_id"] == "turn-code" and captured["rep"] == 2 and captured["task"] == "do"


def test_emit_run_record_writes_file_human_silent(monkeypatch, capsys, tmp_path):
    import core.run_record as rr

    written: dict = {}
    monkeypatch.setattr(rr, "write_record", lambda record, path: written.update({"record": record, "path": path}))
    monkeypatch.setattr(rr, "dump_record", lambda record: json.dumps(record))
    target = str(tmp_path / "r.json")
    ephe_cli._emit_run_record({"a": 1}, as_json=False, record_path=target)
    assert written["path"] == target and written["record"] == {"a": 1}
    assert capsys.readouterr().out == ""  # human mode prints nothing here


def test_cmd_code_human_mode_prints_answer(monkeypatch, capsys):
    from core import react

    _patch_run_record(monkeypatch)
    monkeypatch.setattr(ephe_cli, "engine_for_headless_run", lambda _a, _m: _FakeChoice(ephe_cli.LOCAL_OLLAMA, "m"))
    monkeypatch.setattr(ephe_cli, "_make_recorder", lambda *_a, **_k: _Rec())
    monkeypatch.setattr(ephe_cli, "_init_cli_mcp", _async_ok)

    async def fake_loop(**_k):
        return "the answer"

    monkeypatch.setattr(react, "react_loop", fake_loop)
    assert ephe_cli.cmd_code(_parser().parse_args(["code", "do", "it"])) == 0
    assert "the answer" in capsys.readouterr().out


def test_local_chosen_tag_raises_and_local(monkeypatch):
    import core.engine_config as ec

    def boom(**_k):
        raise RuntimeError("no engine")

    monkeypatch.setattr(ec, "resolve_engine_choice", boom)
    assert ephe_cli._local_chosen_tag() == ""

    monkeypatch.setattr(ec, "resolve_engine_choice", lambda **_k: _FakeChoice(ephe_cli.LOCAL_OLLAMA, "  llama3  "))
    assert ephe_cli._local_chosen_tag() == "llama3"

    monkeypatch.setattr(ec, "resolve_engine_choice", lambda **_k: None)
    assert ephe_cli._local_chosen_tag() == ""


def test_cmd_doctor_repair_hint_and_no_model(monkeypatch, capsys, tmp_path):
    # installed + service up + load test failing -> the pull hint is appended
    _patch_doctor_base(monkeypatch, tmp_path, loadable=(False, "cannot load"))
    assert ephe_cli.cmd_doctor(_parser().parse_args(["doctor", "--model", "m"])) == 1
    assert "repair: ollama pull m" in capsys.readouterr().out

    # no --model and no chosen tag -> the "no model chosen" note
    assert ephe_cli.cmd_doctor(_parser().parse_args(["doctor"])) in (0, 1)
    assert "no model chosen" in capsys.readouterr().out


# start: explicit model + ephemeris failures


def test_cmd_start_ephemeris_record_failure(monkeypatch, tmp_path, capsys):
    import core.ephemeris as eph

    def boom(*_a, **_k):
        raise RuntimeError("sky down")

    monkeypatch.setattr(eph, "record", boom)
    monkeypatch.setattr(ephe_cli, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(ephe_cli, "ensure_pwa_built", lambda: True)
    monkeypatch.setattr(ephe_cli, "resolve_engine_choice", lambda **_k: None)
    monkeypatch.setattr(ephe_cli, "_run", lambda *_a, **_k: types.SimpleNamespace(returncode=0))
    assert ephe_cli.cmd_start(_parser().parse_args(["start"])) == 0
    assert "Ephe" in capsys.readouterr().out  # the banner printed, the sky error was swallowed


def test_cmd_start_explicit_model_choice(monkeypatch, tmp_path, capsys):
    _patch_start_common(monkeypatch, tmp_path)

    from core.engine_config import EngineChoice as RealEngineChoice

    resolved: dict = {}

    def fake_resolve(config_path=None, configure=False, args=None):
        # The engine is resolved first; --model overrides only the model inside it.
        resolved["called"] = True
        resolved["configure"] = configure
        return RealEngineChoice(provider=ephe_cli.LOCAL_OLLAMA, model="engine-default")

    monkeypatch.setattr(ephe_cli, "resolve_engine_choice", fake_resolve)
    monkeypatch.setattr(ephe_cli, "_ensure_ollama_service", lambda: (True, "ok"))
    monkeypatch.setattr(ephe_cli, "_model_installed", lambda _m: True)
    monkeypatch.setattr(ephe_cli, "_model_loadable", lambda _m: (True, "loads"))
    captured: dict = {}

    def fake_run(cmd, **_k):
        captured["cmd"] = cmd
        captured["env"] = _k.get("env")
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(ephe_cli, "_run", fake_run)
    assert ephe_cli.cmd_start(_parser().parse_args(["start", "--model", "m"])) == 0
    # The engine resolution ran despite --model (it is NOT short-circuited)…
    assert resolved.get("called") is True
    assert resolved["configure"] is False
    # …and the tag changed only the model inside that engine.
    assert captured["env"]["EPHE_MODEL"] == "m"
    capsys.readouterr()


# desktop bundle helpers (path discovery, install, konfig)


def test_desktop_bundle_path_variants(tmp_path):
    target = tmp_path / "target"
    (target / "bundle" / "macos").mkdir(parents=True)
    app = target / "bundle" / "macos" / "Ephe.app"
    app.mkdir()
    assert ephe_cli._desktop_bundle_path(target) == app

    # profile-less / foreign layout under a cargo profile dir
    target2 = tmp_path / "t2"
    (target2 / "release" / "bundle" / "deb").mkdir(parents=True)
    deb = target2 / "release" / "bundle" / "deb" / "ephe.deb"
    deb.write_text("x")
    assert ephe_cli._desktop_bundle_path(target2) == deb

    assert ephe_cli._desktop_bundle_path(tmp_path / "empty") is None


def test_install_desktop_bundle_replaces_then_dedupes(tmp_path):
    dest = tmp_path / "Applications"
    dest.mkdir()
    trash = tmp_path / "Trash"
    build = tmp_path / "src-tauri" / "target" / "bundle" / "macos" / "Ephe.app"
    (build / "Contents" / "MacOS").mkdir(parents=True)
    (build / "Contents" / "MacOS" / "Ephe").write_bytes(b"NEW")

    # a different already-installed bundle -> moved to the trash, leftover removed
    old = dest / "Ephe.app"
    (old / "Contents" / "MacOS").mkdir(parents=True)
    (old / "Contents" / "MacOS" / "Ephe").write_bytes(b"OLD")
    result = ephe_cli._install_desktop_bundle(build, dest, trash)
    assert result == dest / "Ephe.app"
    assert (dest / "Ephe.app" / "Contents" / "MacOS" / "Ephe").read_bytes() == b"NEW"
    assert list(trash.glob("Ephe-vor-*.app"))
    assert not build.exists()

    # identical content -> not trashed again, leftover still removed
    build2 = tmp_path / "b2" / "Ephe.app"
    (build2 / "Contents" / "MacOS").mkdir(parents=True)
    (build2 / "Contents" / "MacOS" / "Ephe").write_bytes(b"NEW")
    before = sorted(p.name for p in trash.iterdir())
    ephe_cli._install_desktop_bundle(build2, dest, trash)
    assert sorted(p.name for p in trash.iterdir()) == before
    assert not build2.exists()


def test_schreibe_desktop_konfig(tmp_path):
    pfad = ephe_cli._schreibe_desktop_konfig(tmp_path / "proj", "/usr/bin/python3", port=9999, home=tmp_path)
    assert pfad == tmp_path / ".ephe" / "desktop.json"
    assert json.loads(pfad.read_text()) == {
        "python": "/usr/bin/python3",
        "project_root": str(tmp_path / "proj"),
        "port": 9999,
    }


# sky / amber


def test_cmd_sky_prints_chart(monkeypatch, capsys):
    import core.ephemeris as eph

    monkeypatch.setattr(eph, "default_store", lambda: Path("/nope"))
    monkeypatch.setattr(eph, "load", lambda _store: [{"d": "x"}])
    monkeypatch.setattr(eph, "chart", lambda events, days=7: f"chart days={days} events={len(events)}")
    assert ephe_cli.cmd_sky(_parser().parse_args(["sky", "--days", "3"])) == 0
    assert "chart days=3 events=1" in capsys.readouterr().out


def test_cmd_amber_explicit_and_default_month(monkeypatch, capsys):
    import core.ephemeris as eph

    monkeypatch.setattr(eph, "default_store", lambda: Path("/nope"))
    monkeypatch.setattr(eph, "load", lambda _store: [])
    captured: dict = {}

    def crystallize(events, *, month, amber_dir):
        captured["month"] = month
        captured["amber_dir"] = amber_dir
        return {"sitzungen": 1, "werkzeuge": 2, "artefakte": 3, "bahnen": 4, "tage_aktiv": 5, "spitzstunde": None}

    monkeypatch.setattr(eph, "crystallize", crystallize)
    assert ephe_cli.cmd_amber(_parser().parse_args(["amber", "--month", "2026-05"])) == 0
    out = capsys.readouterr().out
    assert "2026-05" in out and "sitzungen  1" in out and "spitzstunde —" in out
    assert captured["month"] == "2026-05"
    assert captured["amber_dir"] == Path.home() / ".ephe" / "amber"

    # no --month -> the current month is crystallised
    import time

    assert ephe_cli.cmd_amber(_parser().parse_args(["amber"])) == 0
    assert captured["month"] == time.strftime("%Y-%m")
    assert time.strftime("%Y-%m") in capsys.readouterr().out


# serve without a token (localhost-only banner)


def test_cmd_serve_local_no_token(monkeypatch, capsys):
    import uvicorn

    import server.openai as so

    monkeypatch.delenv("EPHE_SERVE_TOKEN", raising=False)
    monkeypatch.setattr(ephe_cli, "engine_for_headless_run", lambda _a, _m: _FakeChoice(ephe_cli.LOCAL_OLLAMA, "m"))
    monkeypatch.setattr(
        so, "create_openai_app",
        lambda api_token=None: types.SimpleNamespace(docs_url="/docs", openapi_url="/openapi.json"),
    )
    monkeypatch.setattr(uvicorn, "run", lambda *_a, **_k: None)
    assert ephe_cli.cmd_serve(_parser().parse_args(["serve"])) == 0
    out = capsys.readouterr().out
    assert "Auth:    none" in out and "127.0.0.1" in out


# memory-mcp flag forwarding


def test_cmd_memory_mcp_forwards_flags(monkeypatch):
    import core.memory_mcp_server as mms

    seen: list[list[str]] = []
    monkeypatch.setattr(mms, "main", lambda argv: (seen.append(argv), 0)[1])
    p = _parser()

    assert ephe_cli.cmd_memory_mcp(p.parse_args(["memory-mcp"])) == 0
    assert seen[-1] == []
    ephe_cli.cmd_memory_mcp(p.parse_args(["memory-mcp", "--allow-write"]))
    assert seen[-1] == ["--allow-write"]
    ephe_cli.cmd_memory_mcp(p.parse_args(["memory-mcp", "--read-only"]))
    assert seen[-1] == ["--read-only"]
    ephe_cli.cmd_memory_mcp(p.parse_args(["memory-mcp", "--scope", "ws1"]))
    assert seen[-1] == ["--scope", "ws1"]
    ephe_cli.cmd_memory_mcp(p.parse_args(["memory-mcp", "--allow-write", "--scope", "ws1"]))
    assert seen[-1] == ["--allow-write", "--scope", "ws1"]


# main: unexpected exceptions are wrapped into exit code 1


def test_main_wraps_unexpected_exception(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        ephe_cli, "_emit_error",
        lambda args, code, msg, hint, **kw: captured.update({"code": code, "msg": msg, "hint": hint}),
    )

    def boom(_args):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(ephe_cli, "cmd_doctor", boom)
    monkeypatch.setattr(sys, "argv", ["ephe", "doctor"])
    with pytest.raises(SystemExit) as exc:
        ephe_cli.main()
    assert exc.value.code == 1
    assert captured["code"] == 1 and captured["msg"] == "kaboom"


def test_main_error_fallback_message_on_empty_exc(monkeypatch):
    captured: dict = {}
    monkeypatch.setattr(
        ephe_cli, "_emit_error",
        lambda args, code, msg, hint, **kw: captured.update({"msg": msg}),
    )

    def boom(_args):
        raise RuntimeError("")

    monkeypatch.setattr(ephe_cli, "cmd_doctor", boom)
    monkeypatch.setattr(sys, "argv", ["ephe", "doctor"])
    with pytest.raises(SystemExit):
        ephe_cli.main()
    assert captured["msg"] == "unexpected error"


# The remote-engine probe used to read `{base}/models` with no credential, so a hosted
# OpenAI-compatible endpoint answered 401 and a working setup read as "not reachable"
# (measured against this repository's own engine.json endpoint, 2026-10-13). The shared
# helper now sends the same bearer token the chat path uses; `ephe_cli._probe_active_remote_engine`
# delegates to it, so doctor and `ephe start` share one key-aware implementation.


class _AuthModelsHandler(BaseHTTPRequestHandler):
    """`/v1/models` behind a bearer check: 401 without the token, 200 with it."""

    token = "s3cret"

    def do_GET(self):  # noqa: N802 — the stdlib name
        if self.headers.get("Authorization") != f"Bearer {self.token}":
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"{}")
            return
        body = json.dumps({"data": [{"id": "hosted-model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        pass


def _start_auth_models_server() -> tuple[HTTPServer, int]:
    server = HTTPServer(("127.0.0.1", 0), _AuthModelsHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def test_probe_remote_engine_sends_the_bearer_token(monkeypatch):
    """
    GIVEN a hosted OpenAI-compatible endpoint that answers 401 without a credential
    WHEN `_probe_remote_engine` probes `GET {base}/models`
    THEN the keyless probe reads unreachable (the 401), the keyed probe reads reachable —
         a valid hosted engine is never reported as broken.
    """
    import core.engine_config as engine_config
    from core._cli_common import _probe_remote_engine

    # The only key source this test drives is the env: the keyring and the key file are
    # neutralized so a developer machine's stored token cannot leak into the assertion.
    monkeypatch.setattr(engine_config, "_load_engine_keyring", lambda: "")
    monkeypatch.setattr(engine_config, "_key_file", lambda home=None: "")
    monkeypatch.delenv("EPHE_OPENAI_COMPAT_API_KEY", raising=False)

    server, port = _start_auth_models_server()
    base = f"http://127.0.0.1:{port}/v1"
    try:
        assert _probe_remote_engine(base, "hosted-model")[0] is False

        monkeypatch.setenv("EPHE_OPENAI_COMPAT_API_KEY", "s3cret")
        reachable, detail = _probe_remote_engine(base, "hosted-model")
        assert reachable is True, detail
        assert "hosted-model" in detail
    finally:
        server.shutdown()


def test_probe_active_remote_engine_delegates_to_the_shared_probe(monkeypatch):
    """The CLI wrapper (doctor and `ephe start`) reports the same keyed reachability."""
    import core.engine_config as engine_config

    monkeypatch.setattr(engine_config, "_load_engine_keyring", lambda: "")
    monkeypatch.setattr(engine_config, "_key_file", lambda home=None: "")
    monkeypatch.setenv("EPHE_OPENAI_COMPAT_API_KEY", "s3cret")

    server, port = _start_auth_models_server()
    try:
        reachable, detail = ephe_cli._probe_active_remote_engine(f"http://127.0.0.1:{port}/v1", "hosted-model")
        assert reachable is True, detail
    finally:
        server.shutdown()


def test_probe_active_remote_engine_refuses_an_unbound_key(monkeypatch):
    """A refusal is reported and no request is sent with the mismatched key."""
    from core import engine_config

    def refuse(_choice):
        raise engine_config.EngineKeyMismatch("the stored engine key is bound to another engine")

    monkeypatch.setattr(engine_config, "assert_engine_key_binding", refuse)
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        ephe_cli, "_probe_remote_engine",
        lambda url, model: (sent.append((url, model)), (True, "reachable"))[1],
    )

    reachable, detail = ephe_cli._probe_active_remote_engine(
        "http://127.0.0.1:9/v1", "hosted-model"
    )

    assert reachable is False
    assert "bound to another engine" in detail
    assert "Re-enter the key" in detail
    assert sent == []


# Welle 1 "Isolation" — the verbs an operator runs a wave and reads its gate with.
#
# Frozen surface: every verb reaches a cmd_* function (no help-only stub), it carries the
# flags the isolation contract needs, and its own description still names the store it
# reads. Behaviour is pinned in tests/test_ephe_cli_isolation.py; a verb renamed here
# without its rename in core/_cli_isolation.py is a defect, not a wording change.

ISOLATION_FLAGS = {
    "agents": ("--json",),
    "changes": ("--json",),
    "show": ("--json",),
    "review": ("--reviewer", "--reason", "--json"),
    "publish": ("--dry-run", "--target", "--json"),
    "reap": ("--older-than", "--json"),
}

ISOLATION_CALLS = {
    "agents": ["agents"],
    "changes": ["changes", "ws"],
    "show": ["show", "cs-1"],
    "review": ["review", "cs-1", "approve", "--reviewer", "r", "--reason", "a.txt:1:why"],
    "publish": ["publish", "cs-1"],
    "reap": ["reap"],
}

ISOLATION_READS = {
    "agents": "worktree register",
    "changes": "newest first",
    "show": "unified diff",
    "review": "PATH:LINE:WHY",
    "publish": "review gate decides first",
    "reap": "grace period",
}


def _subparser(verb: str) -> argparse.ArgumentParser:
    """The parser a verb was registered with, so its own description can be read back."""
    for action in _parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices[verb]
    raise AssertionError("build_parser() registers no subparsers")


@pytest.mark.parametrize("verb", sorted(ISOLATION_CALLS))
def test_isolation_verb_reaches_a_command_function(verb):
    """
    GIVEN the CLI parser
    WHEN an isolation verb is parsed with the arguments it needs
    THEN it dispatches to the cmd_* function that serves it.
    """
    args = _parser().parse_args(ISOLATION_CALLS[verb])

    assert args.func is getattr(ephe_cli, f"cmd_{verb}")


@pytest.mark.parametrize("verb,flags", sorted(ISOLATION_FLAGS.items()))
def test_isolation_verb_carries_its_flags_and_is_completable(verb, flags):
    """
    GIVEN an isolation verb
    WHEN its own --help is rendered
    THEN the flags the operator needs are there and the verb is offered by completion.
    """
    help_text = _subparser(verb).format_help()

    for flag in flags:
        assert flag in help_text, f"{verb} lost {flag}"
    assert verb in ephe_cli._completion_subcommands(), "a verb completion hides is a dead verb"


@pytest.mark.parametrize("verb,phrase", sorted(ISOLATION_READS.items()))
def test_isolation_help_names_what_the_verb_reads(verb, phrase):
    """
    GIVEN an isolation verb
    WHEN its description is read back
    THEN it names the surface it reads, so --help answers 'where does this look?'.
    """
    assert phrase in _subparser(verb).description


def test_a_verdict_without_a_reviewer_or_a_reason_is_a_usage_error():
    """
    GIVEN the gate's two refusals as flags
    WHEN `ephe review` is parsed without them
    THEN argparse exits 2 rather than letting a bare submission reach the ledger.
    """
    for call in (["review", "cs-1", "approve"], ["review", "cs-1", "approve", "--reviewer", "r"]):
        with pytest.raises(SystemExit) as refused:
            _parser().parse_args(call)
        assert refused.value.code == 2


# Welle 2 "Work" — `ephe run`, the run from the terminal that streams and resumes.
#
# Frozen surface, same shape as the isolation block above: the verb reaches `cmd_run`, it
# carries the flags the streaming/resume contract needs, its description still names the
# resumable session it keeps, and completion offers it. Behaviour is pinned in
# tests/test_ephe_cli_run.py.

RUN_FLAGS = (
    "--model", "--workspace", "--resume", "--verify",
    "--no-stream", "--dry-run", "--json", "--run-record",
)


def test_run_verb_reaches_a_command_function():
    """
    GIVEN the CLI parser
    WHEN `ephe run` is parsed with a task
    THEN it dispatches to cmd_run — the streaming, resumable run.
    """
    args = _parser().parse_args(["run", "make", "the", "test", "green"])

    assert args.func is ephe_cli.cmd_run


def test_run_verb_carries_its_flags_and_is_completable():
    """
    GIVEN `ephe run`
    WHEN its own --help is rendered
    THEN the streaming, resume and record flags are there and completion offers the verb.
    """
    help_text = _subparser("run").format_help()

    for flag in RUN_FLAGS:
        assert flag in help_text, f"run lost {flag}"
    assert "run" in ephe_cli._completion_subcommands(), "a verb completion hides is a dead verb"


def test_run_help_names_what_the_verb_reads():
    """
    GIVEN `ephe run`
    WHEN its description is read back
    THEN it names the resumable session it keeps — the part that makes a run continuable.
    """
    assert "resumable session" in str(_subparser("run").description)


def _help_of(verb: str, option: str) -> str:
    """The one-liner a verb's own parser carries for a flag."""
    for action in _subparser(verb)._actions:
        if option in action.option_strings:
            return action.help or ""
    raise AssertionError(f"`{verb}` takes no {option}")


def test_tool_help_lists_the_tools_the_positional_points_at():
    """
    GIVEN `ephe tool`, whose positional points at its own `--help` for the list
    WHEN that help is rendered
    THEN the names are in it.
    """
    help_text = _subparser("tool").format_help()
    names = ephe_cli.available_tool_names()

    assert names, "the registry offers no tool for the help to name"
    missing = [name for name in names if name not in help_text]
    assert missing == [], f"`ephe tool --help` hides {missing}"


def test_tool_help_and_the_unknown_tool_failure_offer_the_same_names(monkeypatch, capsys):
    """
    GIVEN an unknown tool name
    WHEN the failure lists what is available
    THEN that list is the one the help prints.
    """
    monkeypatch.setattr(ephe_cli, "_init_cli_mcp", _async_ok)

    assert ephe_cli.cmd_tool(_parser().parse_args(["tool", "ghost"])) == 1
    listed = capsys.readouterr().err.split("Available tools: ", 1)[1]
    offered = {name.strip() for name in listed.split(",")}
    help_text = _subparser("tool").format_help()

    assert offered == set(ephe_cli.available_tool_names())
    assert [name for name in sorted(offered) if name not in help_text] == []


def test_no_subcommand_flag_is_left_without_a_one_liner():
    """
    GIVEN the CLI's subcommands
    WHEN every flag they register is read back
    THEN each carries help, so `--help` explains the flag wherever it appears.
    """
    parser = _parser()
    bare = [
        f"{verb} {action.option_strings[0]}"
        for root_action in parser._actions
        if isinstance(root_action, argparse._SubParsersAction)
        for verb, sub in root_action.choices.items()
        for action in sub._actions
        if action.option_strings and not action.help
    ]

    assert bare == [], f"flags without help: {bare}"


def test_host_and_port_are_explained_on_every_verb_that_takes_them():
    """
    GIVEN `start`, its alias `web` and `serve`
    WHEN their help is rendered
    THEN the bind address and the port are explained the same way on each.
    """
    for verb in ("start", "web", "serve"):
        help_text = _subparser(verb).format_help()

        assert "Bind address (default: localhost)" in help_text, verb
        assert "Port (default: " in help_text, verb


def test_the_headless_verbs_explain_the_model_flag_in_one_wording():
    """
    GIVEN `ephe code`, `ephe run` and `ephe goal`
    WHEN their `--model` help is read back
    THEN it is the wording `ephe serve` carries, so the flag reads the same everywhere.
    """
    serve = _help_of("serve", "--model")

    assert serve, "`ephe serve` explains no --model"
    for verb in ("code", "run", "goal"):
        assert _help_of(verb, "--model") == serve


def test_the_remaining_flags_carry_their_one_liners():
    """
    GIVEN the flags listed as unexplained
    WHEN their help is read back
    THEN each says what it does.
    """
    assert "Restart the server" in _help_of("start", "--reload")
    assert "probed on" in _help_of("doctor", "--port")
    assert _help_of("doctor", "--json")
    assert _help_of("tui", "--reset")
