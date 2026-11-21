"""Ephe — U8: the bench verifies its workspace on the surface and never repoints it.

Measured 2026-10-10 against the harness as it stood: one handover sent 1 GET plus 2 POSTs to
`/api/settings`, and the first POST persisted the scratch workspace into the product's own
config for the length of the run. Two incidents followed that shape — a parallel conversation
measured against the fixture tree, and a scratch `workspace_dir` that had to be restored by
hand. These tests pin the contract that replaces it: the workspace comes from the harness's own
environment, the surface is read and never written, and a surface that is not isolated stops
the run instead of being repointed.

RULE: tests BEFORE implementation. Given / When / Then — strictly.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def workspace_mod(tmp_path, monkeypatch):
    monkeypatch.delenv("EPHE_BENCH_WORKSPACE", raising=False)
    return _load("_bench_workspace_under_test", REPO / "evals" / "bench_workspace.py")


class FakeSurface:
    """Stands in for the product backend: it answers reads, and a write changes what it keeps.

    `persisted` is the value the product would store in `~/.ephe/engine.json`, `effective` is
    what its tools actually resolve — the two differ whenever the backend was started with
    `EPHE_WORKSPACE`, which is the whole point of the isolation this contract asks for.
    """

    def __init__(self, persisted: str, effective: str | None = None) -> None:
        self.persisted = persisted
        self.effective = effective or persisted
        self.before = persisted
        self.requests: list[tuple[str, str]] = []

    def open(self, req, timeout=None):
        if isinstance(req, str):
            method, path = "GET", req
        else:
            method, path = (req.method or "GET"), req.full_url
        self.requests.append((method, path.split("api/", 1)[-1].split("?")[0]))
        if method == "POST" and path.endswith("/api/settings"):
            body = json.loads(req.data.decode())
            if "workspace_dir" in body:
                self.persisted = body["workspace_dir"]
                self.effective = body["workspace_dir"]
        payload = {"workspace_dir": self.persisted}
        if path.endswith("/api/projects"):
            payload = {"workspace": self.effective, "projects": []}
        return FakeResponse(payload)

    @property
    def posts(self) -> list[tuple[str, str]]:
        return [r for r in self.requests if r[0] == "POST"]

    @property
    def settings_changed(self) -> bool:
        return self.persisted != self.before


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _wire(monkeypatch, surface: FakeSurface, module) -> None:
    monkeypatch.setattr(module, "urlopen", surface.open)


# Where a rep's workspace comes from

def test_workspace_comes_from_the_harness_environment(workspace_mod, monkeypatch, tmp_path):
    """GIVEN EPHE_BENCH_WORKSPACE naming a directory the harness owns
    WHEN the run workspace is resolved
    THEN that is the workspace, and nothing was asked of the surface to learn it."""
    wanted = tmp_path / "cohort" / "fixtures"
    monkeypatch.setenv("EPHE_BENCH_WORKSPACE", str(wanted))
    calls: list[str] = []

    def no_network(*args, **kwargs):
        calls.append(args[0] if args else "call")
        raise AssertionError("resolving the harness workspace must not touch the network")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)
    assert workspace_mod.run_workspace(tmp_path / "cohort") == wanted
    assert calls == []


def test_default_workspace_lives_under_the_cohort_root(workspace_mod, tmp_path):
    """GIVEN a cohort started without an explicit workspace
    WHEN the run workspace is resolved
    THEN it is a directory inside the cohort, so every fixture write stays in the run tree."""
    assert workspace_mod.run_workspace(tmp_path / "cohort") == tmp_path / "cohort" / "ws"


# The handover is a read

def test_an_isolated_surface_is_read_and_never_written(workspace_mod, monkeypatch, tmp_path):
    """GIVEN a backend whose tools already resolve to this cohort's workspace
    WHEN the harness verifies the surface
    THEN it accepts the path, and the settings the product persists are byte-identical."""
    cohort = tmp_path / "cohort" / "ws"
    surface = FakeSurface(persisted=str(tmp_path / "elsewhere"), effective=str(cohort))
    _wire(monkeypatch, surface, workspace_mod.urllib.request)
    assert workspace_mod.require_isolated_surface("http://surface", cohort) == str(Path(cohort).resolve())
    assert surface.posts == []
    assert not surface.settings_changed
    assert surface.requests.count(("GET", "projects")) == 1


def test_the_verifier_asks_the_surface_that_reflects_the_environment(workspace_mod, monkeypatch, tmp_path):
    """GIVEN a backend started with EPHE_WORKSPACE, so its effective workspace differs from the
    one it persisted
    WHEN the harness verifies it
    THEN the judgement is made on the effective value, because the persisted one describes a
    choice the user made in the UI and not the tree the tools will work in."""
    cohort = tmp_path / "cohort" / "ws"
    surface = FakeSurface(persisted=str(tmp_path / "product-project"), effective=str(cohort))
    _wire(monkeypatch, surface, workspace_mod.urllib.request)
    workspace_mod.require_isolated_surface("http://surface", cohort)
    assert ("GET", "settings") not in surface.requests


# A surface that is not isolated is refused, not repaired

def test_a_surface_on_the_product_workspace_stops_the_run(workspace_mod, monkeypatch, tmp_path):
    """GIVEN the live backend working in the owner's project directory
    WHEN a cohort tries to start against it
    THEN the run is refused with the boot line that would isolate it, and the surface is
    still untouched — the old harness answered this situation by POSTing the fixture tree."""
    cohort = tmp_path / "cohort" / "ws"
    surface = FakeSurface(persisted="/work/ephe")
    _wire(monkeypatch, surface, workspace_mod.urllib.request)
    with pytest.raises(workspace_mod.SurfaceNotIsolated) as raised:
        workspace_mod.require_isolated_surface("http://surface", cohort)
    message = str(raised.value)
    assert "EPHE_WORKSPACE" in message
    assert str(cohort) in message
    assert surface.posts == []
    assert not surface.settings_changed


def test_a_surface_that_does_not_answer_is_refused(workspace_mod, monkeypatch, tmp_path):
    """GIVEN a surface that cannot report its workspace
    WHEN the harness verifies it
    THEN the run is refused: an unknown workspace is not evidence of isolation."""
    def dead(url, timeout=None):
        raise urllib.error.URLError("no route")

    monkeypatch.setattr(workspace_mod.urllib.request, "urlopen", dead)
    with pytest.raises(workspace_mod.SurfaceNotIsolated):
        workspace_mod.require_isolated_surface("http://surface", tmp_path / "cohort" / "ws")
