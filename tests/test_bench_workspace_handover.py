"""Ephe — U8: the call site. The harness resolves its workspace locally and only reads the surface.

Landed with the change to `evals/bench_option_b.py`: `set_workspace()` and `restore_workspace()`
are gone, and the run loop's setup step is `require_isolated_surface()`. Measured against the
file before that change, both tests below are red — the old source carried `/api/settings` and
its handover answered a mismatch by POSTing, which is how a scratch `workspace_dir` reached
`~/.ephe/engine.json` (1 GET plus 2 POSTs per handover).

RULE: tests BEFORE implementation. Given / When / Then — strictly.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


class FakeSurface:
    """Answers the reads a run setup makes and records every call, writes included."""

    def __init__(self, workspace: str) -> None:
        self.workspace = workspace
        self.requests: list[tuple[str, str]] = []

    def open(self, req, timeout=None):
        if isinstance(req, str):
            method, path = "GET", req
        else:
            method, path = (req.method or "GET"), req.full_url
        self.requests.append((method, path.split("api/", 1)[-1].split("?")[0]))
        payload = {"workspace": self.workspace, "projects": []}
        return FakeResponse(payload)

    @property
    def posts(self):
        return [r for r in self.requests if r[0] == "POST"]


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_the_harness_carries_no_workspace_repointing():
    """GIVEN a harness that repointed the one shared workspace for the length of a run
    WHEN the change lands
    THEN neither hand of that mechanism survives in the shipped file, and the file makes no
    settings call at all, so a later reader cannot reinstate the write by importing a helper."""
    src = (REPO / "evals" / "bench_option_b.py").read_text(encoding="utf-8")
    assert "/api/settings" not in src
    assert "def set_workspace" not in src
    assert "def restore_workspace" not in src


def test_a_rep_writes_nothing_outside_the_cohort_root(monkeypatch, tmp_path):
    """GIVEN an empty sandbox and a surface that records every call the harness makes
    WHEN the run setup step, the fixtures and one rep manifest are written
    THEN no file appears outside the cohort directory and the surface received no write: the
    count this lane is graded on is zero, measured here rather than asserted from prose."""
    cohort = tmp_path / "cohort"
    monkeypatch.setenv("EPHE_BENCH_MODEL", "test-model")
    monkeypatch.setenv("EPHE_BENCH_DIR", str(cohort))
    monkeypatch.setenv("EPHE_BENCH_BASE", "http://surface")
    monkeypatch.delenv("EPHE_BENCH_WORKSPACE", raising=False)
    bench = _load("_bench_cohort_under_test", REPO / "evals" / "bench_option_b.py")
    surface = FakeSurface(str(cohort / "ws"))
    monkeypatch.setattr(bench.urllib.request, "urlopen", surface.open)

    before = {p for p in tmp_path.rglob("*")}
    assert bench.WORKSPACE == cohort / "ws"
    bench.require_isolated_surface(bench.BASE, bench.WORKSPACE)
    bench.write_fixtures()
    bench.RUNS.mkdir(parents=True, exist_ok=True)
    (bench.RUNS / "w3_r1.json").write_text("{}", encoding="utf-8")

    created = [p for p in tmp_path.rglob("*") if p.is_file() and p not in before]
    assert created, "the cohort tree should hold the fixtures it just wrote"
    outside = [p for p in created if not p.is_relative_to(cohort)]
    assert len(outside) == 0, f"files written outside the cohort: {outside}"
    assert surface.posts == [], f"surface writes a rep made: {surface.posts}"
