"""WS6-42: route path/branch edges the existing route suites leave uncovered.

Basis: a coverage run over the 145 route-touching test files reported 84% for
server/routes. Each class pins one uncovered cluster: the file/fs path bases and
guards, the git relative-path guard, the session-mirror id/restore edges and the
model-provider probe/window branches. Tests name the branch, not the fixture.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from core.model_probe import mirror_api_key, probe_ollama, probe_openai_compatible


@pytest.fixture
def client(tmp_path, monkeypatch):
    """App client with session store and config dir moved under tmp_path."""
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma_db"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "user_profile.json"))
    monkeypatch.setenv("EPHE_CORRECTIONS_PATH", str(tmp_path / "corrections.md"))
    monkeypatch.setenv("EPHE_FEEDBACK_DIR", str(tmp_path))
    monkeypatch.setenv("EPHE_SKILLS_DIR", str(tmp_path / "skills"))
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "config"))
    (tmp_path / "config").mkdir(exist_ok=True)

    import core.engine_config as ec
    monkeypatch.setattr(ec, "CONFIG_DIR", tmp_path / "config")

    from server.routes.memory import _get_memory
    _get_memory.cache_clear()

    from server.main import create_app
    return TestClient(create_app())


def _isolate_config(tmp_path, monkeypatch) -> Path:
    cfg = tmp_path / "config"
    cfg.mkdir(exist_ok=True)
    import core.engine_config as ec
    monkeypatch.setattr(ec, "CONFIG_DIR", cfg)
    return cfg


def _save_workspace(ws: Path) -> None:
    from core.engine_config import EngineChoice, save_engine_config
    save_engine_config(EngineChoice(provider="local_ollama", model="m", workspace_dir=str(ws)))


def _git_repo(base: Path, name: str = "repo") -> Path:
    ws = base / name
    ws.mkdir(parents=True)
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=ws, check=True, capture_output=True, env=env)

    git("init", "-b", "main")
    (ws / "a.txt").write_text("hello\n", encoding="utf-8")
    git("add", "a.txt")
    git("commit", "-m", "init")
    return ws


# server/routes/files.py — _relative_bases (43-73) and the preview guard
class TestFileRoutePathBases:
    def test_relative_bases_names_workspace_output_and_home(self, tmp_path, monkeypatch):
        import server.routes.files as fm

        _isolate_config(tmp_path, monkeypatch)
        ws = tmp_path / "projekt"
        ws.mkdir()
        out = tmp_path / "out"
        out.mkdir()
        monkeypatch.setenv("EPHE_WORKSPACE", str(ws))
        monkeypatch.setenv("EPHE_OUTPUT_DIR", str(out))
        home = tmp_path / "home"
        (home / "Desktop").mkdir(parents=True)
        monkeypatch.setattr(Path, "home", lambda: home)

        bases = fm._relative_bases()

        assert ws in bases
        assert out in bases
        assert home in bases
        assert home / "Desktop" in bases

    def test_relative_path_resolves_against_workspace(self, client, tmp_path, monkeypatch):
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "report.md").write_text("# Titel", encoding="utf-8")
        monkeypatch.setenv("EPHE_WORKSPACE", str(ws))

        r = client.get("/api/file", params={"path": "report.md"})

        assert r.status_code == 200
        assert "inline" in r.headers["content-disposition"]
        assert r.headers["content-type"].startswith("text/markdown")

    def test_relative_path_without_match_is_404(self, client, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_WORKSPACE", str(tmp_path / "empty"))
        r = client.get("/api/file", params={"path": "nowhere.md"})
        assert r.status_code == 404
        assert "relative path resolved" in r.json()["error"]["message"]

    def test_absolute_path_outside_roots_is_403(self, client):
        r = client.get("/api/file", params={"path": "/etc/hosts"})
        assert r.status_code == 403
        assert "allowed roots" in r.json()["error"]["message"]

    def test_symlink_escape_is_403(self, client, tmp_path, monkeypatch):
        ws = tmp_path / "ws"
        ws.mkdir()
        link = ws / "escape.txt"
        try:
            link.symlink_to("/etc/hosts")
        except OSError:
            pytest.skip("symlinks unavailable")
        monkeypatch.setenv("EPHE_WORKSPACE", str(ws))

        r = client.get("/api/file", params={"path": str(link)})

        assert r.status_code == 403

    def test_directory_target_is_404(self, client, tmp_path, monkeypatch):
        ws = tmp_path / "ws"
        ws.mkdir()
        monkeypatch.setenv("EPHE_WORKSPACE", str(ws))
        r = client.get("/api/file", params={"path": str(ws)})
        assert r.status_code == 404

    def test_oversized_file_is_413(self, client, tmp_path, monkeypatch):
        import server.routes.files as fm
        monkeypatch.setattr(fm, "MAX_FILE_BYTES", 4)
        big = tmp_path / "big.md"
        big.write_text("too long", encoding="utf-8")
        r = client.get("/api/file", params={"path": str(big)})
        assert r.status_code == 413

    def test_home_expansion_is_resolved(self, client, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        (home / "note.md").write_text("hi", encoding="utf-8")
        monkeypatch.setenv("HOME", str(home))
        r = client.get("/api/file", params={"path": "~/note.md"})
        assert r.status_code == 200


# server/routes/fs.py — listing quirks, workspace helpers, mkdir edges
class TestFsListingEdges:
    def test_listing_truncates_at_the_entry_cap(self, client, tmp_path):
        d = tmp_path / "many"
        d.mkdir()
        for i in range(505):
            (d / f"f{i:03d}.txt").write_text("x", encoding="utf-8")

        r = client.get("/api/fs", params={"path": str(d)})

        assert r.status_code == 200
        entries = r.json()["entries"]
        assert len(entries) == 501
        assert entries[-1]["type"] == "info"
        assert "500" in entries[-1]["name"]

    def test_unreadable_dir_yields_empty_listing(self, client, tmp_path, monkeypatch):
        d = tmp_path / "locked"
        d.mkdir()

        def boom(self):
            raise PermissionError("denied")

        monkeypatch.setattr(Path, "iterdir", boom)

        r = client.get("/api/fs", params={"path": str(d)})

        assert r.status_code == 200
        assert r.json()["entries"] == []

    def test_entry_with_failing_is_dir_is_skipped(self, client, tmp_path, monkeypatch):
        d = tmp_path / "mixed"
        d.mkdir()
        (d / "ok.txt").write_text("x", encoding="utf-8")
        (d / "boomdir").mkdir()
        real = Path.is_dir
        calls: dict[str, int] = {}

        def flaky(self):
            if self.name == "boomdir":
                calls[self.name] = calls.get(self.name, 0) + 1
                if calls[self.name] >= 2:
                    raise OSError("stat went away")
            return real(self)

        monkeypatch.setattr(Path, "is_dir", flaky)

        r = client.get("/api/fs", params={"path": str(d)})

        names = [e["name"] for e in r.json()["entries"]]
        assert "ok.txt" in names
        assert "boomdir" not in names

    def test_file_without_size_reports_zero(self, client, tmp_path, monkeypatch):
        d = tmp_path / "sizes"
        d.mkdir()
        (d / "nosize.txt").write_text("x", encoding="utf-8")
        real_is_dir = Path.is_dir
        real_stat = Path.stat

        def as_file(self):
            if self.name == "nosize.txt":
                return False
            return real_is_dir(self)

        def no_stat(self, *, follow_symlinks=True):
            if self.name == "nosize.txt":
                raise OSError("gone")
            return real_stat(self, follow_symlinks=follow_symlinks)

        monkeypatch.setattr(Path, "is_dir", as_file)
        monkeypatch.setattr(Path, "stat", no_stat)

        r = client.get("/api/fs", params={"path": str(d)})

        entry = next(e for e in r.json()["entries"] if e["name"] == "nosize.txt")
        assert entry["type"] == "file"
        assert entry["size"] == 0


class TestFsWorkspaceHelpers:
    def test_workspace_state_reports_set_workspace(self, tmp_path, monkeypatch):
        import server.routes.fs as fsmod
        _isolate_config(tmp_path, monkeypatch)
        ws = tmp_path / "projekt"
        ws.mkdir()
        _save_workspace(ws)

        assert fsmod._workspace_state() == (str(ws), True)

    def test_workspace_state_falls_back_when_first_source_breaks(self, tmp_path, monkeypatch):
        import server.routes.fs as fsmod
        import core.engine_config as ec

        _isolate_config(tmp_path, monkeypatch)
        real_load = ec.load_engine_config
        state = {"n": 0}

        def flaky(*a, **k):
            state["n"] += 1
            if state["n"] == 1:
                raise RuntimeError("unreadable config")
            return real_load(*a, **k)

        monkeypatch.setattr(ec, "load_engine_config", flaky)
        monkeypatch.delenv("EPHE_WORKSPACE", raising=False)
        monkeypatch.chdir(tmp_path)

        ws, is_set = fsmod._workspace_state()

        assert ws == str(Path(os.getcwd()).resolve())
        assert is_set is False

    def test_workspace_state_none_when_all_sources_fail(self, tmp_path, monkeypatch):
        import server.routes.fs as fsmod
        import core.engine_config as ec

        def boom(*a, **k):
            raise RuntimeError("no config")

        monkeypatch.setattr(ec, "load_engine_config", boom)
        monkeypatch.setattr(ec, "get_workspace_dir", boom)

        assert fsmod._workspace_state() == (None, False)

    def test_workspace_or_none_prefers_configured(self, tmp_path, monkeypatch):
        import server.routes.fs as fsmod
        _isolate_config(tmp_path, monkeypatch)
        ws = tmp_path / "p"
        ws.mkdir()
        _save_workspace(ws)
        assert fsmod._workspace_or_none() == str(ws)

    def test_workspace_or_none_falls_back_to_cwd(self, tmp_path, monkeypatch):
        import server.routes.fs as fsmod
        _isolate_config(tmp_path, monkeypatch)
        monkeypatch.delenv("EPHE_WORKSPACE", raising=False)
        monkeypatch.chdir(tmp_path)
        assert fsmod._workspace_or_none() == str(Path(os.getcwd()).resolve())

    def test_workspace_or_none_none_when_all_sources_fail(self, tmp_path, monkeypatch):
        import server.routes.fs as fsmod
        import core.engine_config as ec

        def boom(*a, **k):
            raise RuntimeError("x")

        monkeypatch.setattr(ec, "load_engine_config", boom)
        monkeypatch.setattr(ec, "get_workspace_dir", boom)
        assert fsmod._workspace_or_none() is None


class TestFsMkdirEdges:
    def test_empty_parent_is_422(self, client):
        assert client.post("/api/fs/mkdir", json={"parent": "  ", "name": "x"}).status_code == 422

    def test_parent_outside_roots_is_403(self, client):
        assert client.post("/api/fs/mkdir", json={"parent": "/etc", "name": "x"}).status_code == 403

    def test_missing_parent_is_404(self, client, tmp_path):
        r = client.post("/api/fs/mkdir", json={"parent": str(tmp_path / "weg"), "name": "x"})
        assert r.status_code == 404

    @pytest.mark.parametrize("name", ["", "a/b", "..", ".hidden", "x" * 81])
    def test_invalid_names_are_422(self, client, tmp_path, name):
        d = tmp_path / "target"
        d.mkdir()
        r = client.post("/api/fs/mkdir", json={"parent": str(d), "name": name})
        assert r.status_code == 422

    def test_existing_file_with_same_name_is_409(self, client, tmp_path):
        d = tmp_path / "target"
        d.mkdir()
        (d / "afile").write_text("x", encoding="utf-8")
        r = client.post("/api/fs/mkdir", json={"parent": str(d), "name": "afile"})
        assert r.status_code == 409

    def test_existing_dir_reports_not_created(self, client, tmp_path):
        d = tmp_path / "target"
        d.mkdir()
        (d / "existing").mkdir()
        r = client.post("/api/fs/mkdir", json={"parent": str(d), "name": "existing"})
        assert r.status_code == 200 and r.json()["created"] is False

    def test_new_dir_reports_created(self, client, tmp_path):
        d = tmp_path / "target"
        d.mkdir()
        r = client.post("/api/fs/mkdir", json={"parent": str(d), "name": "fresh"})
        assert r.status_code == 200 and r.json()["created"] is True
        assert (d / "fresh").is_dir()

    def test_mkdir_oserror_is_500(self, client, tmp_path, monkeypatch):
        d = tmp_path / "target"
        d.mkdir()
        real_mkdir = Path.mkdir

        def boom(self, *a, **k):
            if self.name == "denied":
                raise OSError("denied")
            return real_mkdir(self, *a, **k)

        monkeypatch.setattr(Path, "mkdir", boom)

        r = client.post("/api/fs/mkdir", json={"parent": str(d), "name": "denied"})
        assert r.status_code == 500


# server/routes/git_info.py — relative path guard, diff/apply edges
class TestGitPathGuards:
    def test_safe_relpath_rejects_unsafe_shapes(self, tmp_path):
        import server.routes.git_info as gi
        ws = tmp_path / "repo"
        ws.mkdir()
        for raw in ["", "-A", "/etc/passwd", "a\\b", "a\x00b", "../x", "sub/../x"]:
            assert gi._safe_relpath(str(ws), raw) is None, raw

    def test_safe_relpath_accepts_workspace_file(self, tmp_path):
        import server.routes.git_info as gi
        ws = tmp_path / "repo"
        ws.mkdir()
        assert gi._safe_relpath(str(ws), "a.txt") == "a.txt"

    def test_safe_relpath_refuses_symlink_escape(self, tmp_path):
        import server.routes.git_info as gi
        ws = tmp_path / "repo"
        ws.mkdir()
        try:
            (ws / "link").symlink_to("/etc")
        except OSError:
            pytest.skip("symlinks unavailable")
        assert gi._safe_relpath(str(ws), "link/hosts") is None

    def test_safe_relpath_none_when_resolve_fails(self, tmp_path, monkeypatch):
        import server.routes.git_info as gi
        ws = tmp_path / "repo"
        ws.mkdir()

        def boom(*a, **k):
            raise OSError("resolve failed")

        monkeypatch.setattr("server.routes.git_info.os.path.realpath", boom)
        assert gi._safe_relpath(str(ws), "a.txt") is None

    def test_apply_guard_allows_dev_null_and_strips_prefixes(self, tmp_path):
        import server.routes.git_info as gi
        ws = tmp_path / "repo"
        ws.mkdir()
        patch = "--- /dev/null\n+++ b/a.txt\n@@ -0,0 +1 @@\n+x\n"
        assert gi._apply_path_guard(str(ws), patch) is None

    def test_apply_guard_rejects_escaping_header(self, tmp_path):
        import server.routes.git_info as gi
        ws = tmp_path / "repo"
        ws.mkdir()
        patch = "--- a/../../etc/passwd\n+++ b/../../etc/passwd\n@@ -1 +1 @@\n-x\n+y\n"
        err = gi._apply_path_guard(str(ws), patch)
        assert err is not None and "invalid path" in err

    def test_apply_guard_ignores_patch_without_headers(self, tmp_path):
        import server.routes.git_info as gi
        ws = tmp_path / "repo"
        ws.mkdir()
        assert gi._apply_path_guard(str(ws), "@@ -1 +1 @@\n-a\n+b\n") is None


def _valid_patch() -> str:
    return "--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-hello\n+hello!\n"


def _shim_git_subprocess(monkeypatch, *, time_out=False, rc=0, stderr=b""):
    """Replace the apply subprocess with a fake proc; wait_for either returns
    the fake output or raises TimeoutError, so both branches run without git."""
    import server.routes.git_info as gi
    real_asyncio = asyncio

    class _Proc:
        returncode = rc

        def kill(self):
            pass

        async def communicate(self, input=None):
            return (b"", stderr)

    async def _exec(*a, **k):
        return _Proc()

    async def _wait(aw, timeout=None):
        if time_out:
            aw.close()
            raise real_asyncio.TimeoutError()
        return await aw

    shim = SimpleNamespace(
        create_subprocess_exec=_exec,
        wait_for=_wait,
        subprocess=real_asyncio.subprocess,
        TimeoutError=real_asyncio.TimeoutError,
    )
    monkeypatch.setattr(gi, "asyncio", shim)


class TestGitDiffApplyEdges:
    def test_diff_without_workspace_is_409(self, client, tmp_path, monkeypatch):
        import server.routes.git_info as gi
        monkeypatch.setattr(gi, "get_workspace_dir", lambda: str(tmp_path / "weg"))
        assert client.get("/api/git/diff", params={"path": "a.txt"}).status_code == 409

    def test_apply_empty_patch_is_400(self, client, tmp_path, monkeypatch):
        ws = _git_repo(tmp_path)
        monkeypatch.setenv("EPHE_WORKSPACE", str(ws))
        r = client.post("/api/git/apply", json={"patch": "   "})
        assert r.status_code == 400

    def test_apply_escaping_header_is_400(self, client, tmp_path, monkeypatch):
        ws = _git_repo(tmp_path)
        monkeypatch.setenv("EPHE_WORKSPACE", str(ws))
        patch = "--- a/../../etc/passwd\n+++ b/../../etc/passwd\n@@ -1 +1 @@\n-a\n+b\n"
        r = client.post("/api/git/apply", json={"patch": patch})
        assert r.status_code == 400

    def test_apply_timeout_is_409(self, client, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_WORKSPACE", str(tmp_path))
        _shim_git_subprocess(monkeypatch, time_out=True)
        r = client.post("/api/git/apply", json={"patch": _valid_patch()})
        assert r.status_code == 409
        assert "timed out" in r.json()["error"]["message"]

    def test_apply_conflict_surfaces_the_git_error(self, client, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_WORKSPACE", str(tmp_path))
        _shim_git_subprocess(monkeypatch, rc=1, stderr=b"error: U1 conflict in a.txt\n")
        r = client.post("/api/git/apply", json={"patch": _valid_patch()})
        assert r.status_code == 409
        assert "U1 conflict" in r.json()["error"]["message"]


# server/routes/session_mirror.py — id paths, restore file edges
@pytest.fixture
def sync_stack(tmp_path, monkeypatch):
    """Hermetic session store + search db + TestClient with lifespans."""
    import core.multi_session as ms

    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    monkeypatch.setattr(ms, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setenv("EPHE_SEARCH_DB", str(tmp_path / "search.db"))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma_db"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "user_profile.json"))
    cfg = tmp_path / "config"
    cfg.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))

    import core.engine_config as ec
    monkeypatch.setattr(ec, "CONFIG_DIR", cfg)

    from server.main import create_app
    with TestClient(create_app()) as c:
        yield c, sessions_dir


class TestSessionSyncEdges:
    def test_too_many_messages_is_413(self, sync_stack):
        client, _ = sync_stack
        payload = {"sessions": [{
            "id": "big",
            "messages": [{"role": "user", "content": "x"} for _ in range(2001)],
        }]}
        assert client.post("/api/sessions/sync", json=payload).status_code == 413

    def test_chmod_failure_does_not_break_sync(self, sync_stack, monkeypatch):
        client, sessions_dir = sync_stack
        real_chmod = Path.chmod

        def boom(self, *a, **k):
            if str(self).endswith(".json"):
                raise OSError("read-only fs")
            return real_chmod(self, *a, **k)

        monkeypatch.setattr(Path, "chmod", boom)
        r = client.post("/api/sessions/sync", json={"sessions": [
            {"id": "chmod1", "title": "T", "messages": [{"role": "user", "content": "x"}]}
        ]})
        assert r.status_code == 200 and r.json()["stored_sessions"] == 1

    def test_second_sync_updates_registry_fields(self, sync_stack):
        client, sessions_dir = sync_stack
        client.post("/api/sessions/sync", json={"sessions": [
            {"id": "abc", "title": "T1", "messages": [{"role": "user", "content": "x"}]}
        ]})
        r = client.post("/api/sessions/sync", json={"sessions": [{
            "id": "abc",
            "mode": "code",
            "parent_id": "root",
            "created_at": 1717171717.0,
            "messages": [{"role": "user", "content": "x"}],
        }]})
        assert r.status_code == 200
        entry = json.loads((sessions_dir / "registry.json").read_text(encoding="utf-8"))["sessions"]
        entry = next(e for e in entry if e["id"] == "pwa-abc")
        assert entry["mode"] == "code"
        assert entry["parent_id"] == "root"
        assert entry["created_at"] == 1717171717.0

    def test_deleted_invalid_id_is_skipped(self, sync_stack):
        client, _ = sync_stack
        r = client.post("/api/sessions/sync", json={"sessions": [], "deleted": ["../evil", "ok-id"]})
        assert r.status_code == 200
        assert r.json()["dropped_sessions"] == 1

    def test_deleted_unlink_failure_is_swallowed(self, sync_stack, monkeypatch):
        client, sessions_dir = sync_stack
        (sessions_dir / "pwa-gone.json").write_text("[]", encoding="utf-8")
        real_unlink = Path.unlink

        def boom(self, *a, **k):
            if self.name == "pwa-gone.json":
                raise OSError("busy")
            return real_unlink(self, *a, **k)

        monkeypatch.setattr(Path, "unlink", boom)
        r = client.post("/api/sessions/sync", json={"sessions": [], "deleted": ["gone"]})
        assert r.status_code == 200 and r.json()["dropped_sessions"] == 1

    def test_deleted_evaporates_cell_when_switch_is_on(self, sync_stack, monkeypatch):
        client, sessions_dir = sync_stack
        from core.settings_schema import save_deep_settings
        save_deep_settings({"ephemera": {"ephemera.evaporate_on_delete": True}})
        (sessions_dir / "pwa-doomed.json").write_text("[]", encoding="utf-8")

        from core import ephemeral_cell
        forgotten: list[str] = []
        monkeypatch.setattr(ephemeral_cell, "forget", lambda sid: forgotten.append(sid))

        r = client.post("/api/sessions/sync", json={"sessions": [], "deleted": ["doomed"]})

        assert r.status_code == 200 and r.json()["dropped_sessions"] == 1
        assert forgotten == ["doomed"]


class TestSessionMirrorHelpers:
    def test_geburt_ms_reads_number_and_iso_and_bad(self):
        import server.routes.session_mirror as sm
        assert sm._geburt_ms({"created_at": 5.5}) == 5.5
        assert sm._geburt_ms({"createdAt": 1000}) == 1_000_000
        assert sm._geburt_ms({"createdAt": "2026-01-02T03:04:05"}) is not None
        assert sm._geburt_ms({"createdAt": "not-a-date"}) is None
        assert sm._geburt_ms({}) is None

    def test_schlank_keeps_card_but_drops_result(self, monkeypatch):
        import server.routes.session_mirror as sm
        monkeypatch.setattr(sm, "MAX_MESSAGE_JSON", 200)
        out = sm._schlank({"role": "assistant", "content": "c",
                           "tool_calls": [{"name": "read", "result": "R" * 400}]})
        assert out["tool_calls"] == [{"name": "read"}]

    def test_schlank_drops_tool_calls_when_still_oversized(self, monkeypatch):
        import server.routes.session_mirror as sm
        monkeypatch.setattr(sm, "MAX_MESSAGE_JSON", 120)
        out = sm._schlank({"role": "assistant", "content": "x",
                           "tool_calls": [{"name": "read", "args": {"p": "y" * 500}}]})
        assert "tool_calls" not in out
        assert out["content"] == "x"


class TestSessionRestoreEdges:
    async def test_restore_without_store_returns_empty(self, tmp_path, monkeypatch):
        import core.multi_session as ms
        import server.routes.session_mirror as sm
        monkeypatch.setattr(ms, "SESSIONS_DIR", tmp_path / "missing")
        assert await sm.restore_sessions() == {"sessions": []}

    async def test_restore_glob_failure_returns_empty(self, tmp_path, monkeypatch):
        import core.multi_session as ms
        import server.routes.session_mirror as sm
        monkeypatch.setattr(ms, "SESSIONS_DIR", tmp_path)
        real_glob = Path.glob

        def boom(self, pattern, *a, **k):
            if pattern == "pwa-*.json":
                raise OSError("glob failed")
            return real_glob(self, pattern, *a, **k)

        monkeypatch.setattr(Path, "glob", boom)
        assert await sm.restore_sessions() == {"sessions": []}

    async def test_restore_skips_oversized_file(self, tmp_path, monkeypatch):
        import core.multi_session as ms
        import server.routes.session_mirror as sm
        monkeypatch.setattr(ms, "SESSIONS_DIR", tmp_path)
        monkeypatch.setattr(sm, "_MAX_RESTORE_FILE_BYTES", 1)
        (tmp_path / "pwa-x.json").write_text('[{"role": "user", "content": "x"}]', encoding="utf-8")
        assert await sm.restore_sessions() == {"sessions": []}

    async def test_restore_skips_broken_and_non_list(self, tmp_path, monkeypatch):
        import core.multi_session as ms
        import server.routes.session_mirror as sm
        monkeypatch.setattr(ms, "SESSIONS_DIR", tmp_path)
        (tmp_path / "pwa-bad.json").write_text("{ not json", encoding="utf-8")
        (tmp_path / "pwa-obj.json").write_text('{"a": 1}', encoding="utf-8")
        (tmp_path / "pwa-good.json").write_text('[{"role": "user", "content": "ok"}]', encoding="utf-8")
        res = await sm.restore_sessions()
        assert [s["id"] for s in res["sessions"]] == ["good"]

    async def test_restore_derives_created_at_from_registry(self, tmp_path, monkeypatch):
        import core.multi_session as ms
        import server.routes.session_mirror as sm
        monkeypatch.setattr(ms, "SESSIONS_DIR", tmp_path)
        (tmp_path / "pwa-a.json").write_text('[{"role": "user", "content": "x"}]', encoding="utf-8")
        (tmp_path / "registry.json").write_text(json.dumps({"sessions": [
            {"id": "pwa-a", "title": "T", "createdAt": 1000}
        ]}), encoding="utf-8")
        res = await sm.restore_sessions()
        assert res["sessions"][0]["created_at"] == 1_000_000


# server/routes/model_provider.py — probe and context-window branches
class _FakeResp:
    def __init__(self, payload=None, status=200):
        self._payload = payload if payload is not None else {}
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            req = httpx.Request("GET", "http://fake")
            raise httpx.HTTPStatusError("err", request=req,
                                        response=httpx.Response(self.status_code, request=req))

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, resp=None, exc=None, **kwargs):
        self._resp = resp
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, headers=None):
        if self._exc is not None:
            raise self._exc
        return self._resp


def _patch_http(monkeypatch, resp=None, exc=None):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **k: _FakeClient(resp=resp, exc=exc))


class TestModelProviderProbes:
    async def test_probe_ollama_adds_scheme_for_bare_host(self, monkeypatch):
        _patch_http(monkeypatch, resp=_FakeResp({"models": [{"name": "llama3"}]}))
        ok, models, detail, state = await probe_ollama("127.0.0.1:11434")
        assert ok is True and state == "ok"
        assert "http://127.0.0.1:11434" in detail
        assert models == ["llama3"]

    async def test_probe_ollama_timeout_is_busy(self, monkeypatch):
        _patch_http(monkeypatch, exc=httpx.TimeoutException("slow"))
        ok, models, detail, state = await probe_ollama("http://h:1")
        assert ok is False and state == "busy" and models == []

    async def test_probe_ollama_status_error_is_unreachable(self, monkeypatch):
        _patch_http(monkeypatch, resp=_FakeResp(status=500))
        ok, _, detail, state = await probe_ollama("http://h:1")
        assert ok is False and state == "unreachable" and "500" in detail

    async def test_probe_openai_without_url(self, monkeypatch):
        ok, _, detail, state = await probe_openai_compatible("", None)
        assert ok is False and state == "unreachable" and detail == "no engine URL given"

    async def test_probe_openai_adds_scheme_and_strips_v1(self, monkeypatch):
        _patch_http(monkeypatch, resp=_FakeResp({"data": [{"id": "gemma"}]}))
        ok, ids, detail, state = await probe_openai_compatible("host:8000/v1", None)
        assert ok is True and state == "ok"
        assert ids == ["gemma"]
        assert "http://host:8000 reachable" in detail

    async def test_probe_openai_timeout_is_busy(self, monkeypatch):
        _patch_http(monkeypatch, exc=httpx.TimeoutException("slow"))
        ok, _, _, state = await probe_openai_compatible("http://h:1", None)
        assert ok is False and state == "busy"

    async def test_probe_openai_status_error(self, monkeypatch):
        _patch_http(monkeypatch, resp=_FakeResp(status=503))
        ok, _, detail, state = await probe_openai_compatible("http://h:1", None)
        assert ok is False and state == "unreachable" and "503" in detail

    async def test_probe_openai_generic_error(self, monkeypatch):
        _patch_http(monkeypatch, exc=RuntimeError("kaboom"))
        ok, _, detail, state = await probe_openai_compatible("http://h:1", None)
        assert ok is False and state == "unreachable" and "not reachable" in detail

    def test_mirror_api_key_swallows_broken_json(self, tmp_path):
        home = tmp_path / "h"
        (home / ".cache" / "opencode").mkdir(parents=True)
        (home / ".local" / "share" / "opencode").mkdir(parents=True)
        (home / ".cache" / "opencode" / "models.json").write_text("{ broken", encoding="utf-8")
        (home / ".local" / "share" / "opencode" / "auth.json").write_text("{}", encoding="utf-8")
        assert mirror_api_key("http://x", home=home) is None


class TestModelProviderContextWindow:
    async def test_window_read_from_models_and_cached(self, monkeypatch):
        import server.routes.model_provider as mp
        mp._CONTEXT_WINDOW_CACHE.clear()
        _patch_http(monkeypatch, resp=_FakeResp({"data": [{"id": "m", "max_model_len": 262144}]}))
        active = SimpleNamespace(provider="openai_compatible", base_url="http://host:8000", model="m")
        try:
            assert await mp._active_context_window(active) == 262144
            assert ("http://host:8000", "m") in mp._CONTEXT_WINDOW_CACHE
            _patch_http(monkeypatch, exc=RuntimeError("cache miss would hit HTTP"))
            assert await mp._active_context_window(active) == 262144
        finally:
            mp._CONTEXT_WINDOW_CACHE.clear()

    async def test_window_none_when_model_absent(self, monkeypatch):
        import server.routes.model_provider as mp
        mp._CONTEXT_WINDOW_CACHE.clear()
        _patch_http(monkeypatch, resp=_FakeResp({"data": [{"id": "other", "max_model_len": 4096}]}))
        active = SimpleNamespace(provider="openai_compatible", base_url="http://h:1", model="m")
        assert await mp._active_context_window(active) is None

    async def test_window_none_for_non_openai_provider(self):
        import server.routes.model_provider as mp
        active = SimpleNamespace(provider="local_ollama", base_url=None, model="m")
        assert await mp._active_context_window(active) is None


class TestModelProviderPricingAndUpdate:
    def test_active_pricing_reads_engine_table(self, tmp_path, monkeypatch):
        import server.routes.model_provider as mp
        import core.engine_config as ec
        _isolate_config(tmp_path, monkeypatch)
        ec.save_engine_config(ec.EngineChoice(
            provider="openai_compatible", model="m",
            pricing={"in_per_m": 0.05, "out_per_m": 0.4},
        ))
        assert mp._active_pricing() == {"in_per_m": 0.05, "out_per_m": 0.4}

    def test_active_pricing_none_without_table(self, tmp_path, monkeypatch):
        import server.routes.model_provider as mp
        _isolate_config(tmp_path, monkeypatch)
        assert mp._active_pricing() is None

    async def test_update_rejects_unknown_provider_type(self):
        from fastapi import HTTPException
        import server.routes.model_provider as mp
        with pytest.raises(HTTPException) as exc:
            await mp.update_model_provider(mp.ProviderUpdateRequest(provider="bogus"))
        assert exc.value.status_code == 422

    async def test_update_online_without_confirmation_is_409(self):
        from fastapi import HTTPException
        import server.routes.model_provider as mp
        req = mp.ProviderUpdateRequest(provider="openai_compatible", model="m",
                                       base_url="http://x", confirm_online=False)
        with pytest.raises(HTTPException) as exc:
            await mp.update_model_provider(req)
        assert exc.value.status_code == 409

    async def test_update_setup_error_is_400(self, monkeypatch):
        from fastapi import HTTPException
        import server.routes.model_provider as mp

        async def no_models():
            return []

        monkeypatch.setattr(mp, "list_local_model_options", no_models)

        def boom(**k):
            raise mp.ProviderSetupError("no engine")

        monkeypatch.setattr(mp, "set_active_provider", boom)
        req = mp.ProviderUpdateRequest(provider="local_ollama", model=None)
        with pytest.raises(HTTPException) as exc:
            await mp.update_model_provider(req)
        assert exc.value.status_code == 400

    async def test_update_persist_failure_is_swallowed(self, monkeypatch):
        import server.routes.model_provider as mp
        import core.engine_config as ec

        async def no_models():
            return []

        monkeypatch.setattr(mp, "list_local_model_options", no_models)
        active = SimpleNamespace(provider="local_ollama", model="m", base_url=None,
                                 to_dict=lambda: {"provider": "local_ollama", "model": "m"})
        monkeypatch.setattr(mp, "set_active_provider", lambda **k: active)

        def boom(*a, **k):
            raise RuntimeError("disk full")

        monkeypatch.setattr(ec, "persist_engine_choice", boom)
        monkeypatch.setattr("server.routes.settings._clear_setup_skip", lambda: None)

        res = await mp.update_model_provider(mp.ProviderUpdateRequest(provider="local_ollama", model="m"))
        assert res["active"]["provider"] == "local_ollama"
