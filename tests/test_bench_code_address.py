"""The code address, tested where it can be proven: a repository built in tmp_path.

The claims worth pinning are the two that a number rests on: the address tracks the code
that answered the rep (`core/`, `server/`) and not the tool that scored it, and a row that
carries no address is never counted as agreement with the rows that do.
"""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load():
    name = "_bench_code_address_under_test"
    import sys
    sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(name, REPO / "evals" / "bench_code_address.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ca = _load()


def _mkrepo(tmp_path: Path) -> Path:
    def git(*args):
        subprocess.run(["git", *args], cwd=str(tmp_path), check=True, capture_output=True,
                       env={"PATH": "/usr/bin:/bin", "GIT_AUTHOR_NAME": "t",
                            "GIT_AUTHOR_EMAIL": "t@e", "GIT_COMMITTER_NAME": "t",
                            "GIT_COMMITTER_EMAIL": "t@e", "HOME": str(tmp_path)})
    (tmp_path / "core").mkdir()
    (tmp_path / "server").mkdir()
    (tmp_path / "core" / "chat.py").write_text("print('one')\n", encoding="utf-8")
    (tmp_path / "server" / "main.py").write_text("print('a')\n", encoding="utf-8")
    git("init", "-q", "-b", "main")
    git("add", "core", "server")
    git("commit", "-qm", "first")
    return tmp_path


def addr(commit: str = "", surface: str = "s" * 40) -> dict:
    return {"commit": commit or "c" * 40, "commit_short": (commit or "c" * 40)[:7],
            "surface": {"core": "x" * 40, "server": "y" * 40}, "surface_sha": surface,
            "dirty": []}


def test_address_names_the_commit_and_both_surfaces(tmp_path):
    root = _mkrepo(tmp_path)
    got = ca.address(root=root)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(root), capture_output=True,
                          text=True).stdout.strip()
    assert got["commit"] == head and got["commit_short"] == head[:7]
    assert set(got["surface"]) == {"core", "server"}
    assert len(got["surface_sha"]) == 40


def test_the_digest_moves_when_the_measured_code_moves(tmp_path):
    root = _mkrepo(tmp_path)
    before = ca.address(root=root)
    (root / "core" / "chat.py").write_text("print('two')\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(root), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "second"], cwd=str(root), check=True,
                   capture_output=True,
                   env={"PATH": "/usr/bin:/bin", "GIT_AUTHOR_NAME": "t",
                        "GIT_AUTHOR_EMAIL": "t@e", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@e", "HOME": str(root)})
    after = ca.address(root=root)
    assert after["commit"] != before["commit"]
    assert after["surface_sha"] != before["surface_sha"], "the surface moved, the digest must too"


def test_an_evals_commit_does_not_move_the_measured_surface(tmp_path):
    # The boundary `6483dd70` learned: the tool is not the thing under test.
    root = _mkrepo(tmp_path)
    (root / "evals").mkdir()
    (root / "evals" / "bench_option_b.py").write_text("print('tool')\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(root), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "tooling"], cwd=str(root), check=True,
                   capture_output=True,
                   env={"PATH": "/usr/bin:/bin", "GIT_AUTHOR_NAME": "t",
                        "GIT_AUTHOR_EMAIL": "t@e", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@e", "HOME": str(root)})
    got = ca.address(root=root)
    assert set(got["surface"]) == {"core", "server"}, "the address may not grow a third surface"
    assert got["surface_sha"] == ca.surface_sha(ca.tree_oids(root)), "same code, same digest"


def test_uncommitted_edit_is_recorded_and_does_not_change_the_address(tmp_path):
    root = _mkrepo(tmp_path)
    committed = ca.address(root=root)
    (root / "core" / "chat.py").write_text("print('buffer')\n", encoding="utf-8")
    dirty = ca.address(root=root)
    assert dirty["dirty"] == ["core/chat.py"]
    assert dirty["surface_sha"] == committed["surface_sha"], "HEAD is what ran, the buffer is a flag"


def test_a_tree_without_git_yields_none_not_a_zero(tmp_path):
    assert ca.address(root=tmp_path) is None


def test_digest_is_order_independent():
    one = {"core": "a" * 40, "server": "b" * 40}
    two = {"server": "b" * 40, "core": "a" * 40}
    assert ca.surface_sha(one) == ca.surface_sha(two)


def test_of_reads_legacy_as_none():
    assert ca.of({}) is None
    assert ca.of({"code_address": None}) is None
    assert ca.of({"code_address": {"commit": ""}}) is None
    assert ca.of({"code_address": addr()})["surface_sha"]


def test_absent_address_is_never_counted_as_agreement():
    # Two addressed rows plus one hole is a cohort that cannot be reproduced, not one stand minus a detail.
    state = ca.cohort_state([{"code_address": addr()}, {"code_address": addr()}, {"rep": 1}])
    assert state["status"] == "partly-unaddressed" and state["unaddressed"] == 1


def test_statuses_that_a_cohort_can_have():
    assert ca.cohort_state([])["status"] == "empty"
    assert ca.cohort_state([{"rep": 1}, {"rep": 2}])["status"] == "legacy"
    assert ca.cohort_state([{"code_address": addr()}])["status"] == "single-stand"
    moved = ca.cohort_state([{"code_address": addr(surface="a" * 40)},
                             {"code_address": addr(surface="b" * 40)}])
    assert moved["status"] == "moved-mid-run"
    assert moved["stands"] == 2 and moved["reps_per_stand"] == {"a" * 40: 1, "b" * 40: 1}


def test_two_commits_of_one_surface_are_still_one_number():
    # Docs, tests and tooling land between reps all day; the number is one number when the
    # measured code did not move. This is the case a commit-only check would refuse wrongly.
    rows = [{"code_address": addr(commit="c" * 40)}, {"code_address": addr(commit="d" * 40)}]
    state = ca.cohort_state(rows)
    assert state["status"] == "single-stand" and state["stands"] == 1 and state["commits"] == 2


def _harness(monkeypatch):
    """The bench module itself, with no server and no engine probe."""
    import ast
    import importlib.util
    monkeypatch.setenv("EPHE_BENCH_MODEL", "test-model")
    monkeypatch.setenv("EPHE_BENCH_BASE", "http://127.0.0.1:1")
    spec = importlib.util.spec_from_file_location("_bench_address_harness",
                                                  REPO / "evals" / "bench_option_b.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_harness_imports_the_address_module_from_a_test_context(monkeypatch):
    # `evals/` is not a package, so the harness bootstraps its own neighbour. Loading it the
    # way the other bench tests do proves that bootstrap and not just the intent.
    module = _harness(monkeypatch)
    got = module._code_address()
    assert got and len(got["surface_sha"]) == 40 and set(got["surface"]) == {"core", "server"}


def test_every_manifest_asks_for_an_address():
    # Read as syntax on purpose: the dict built inside run_task must carry the key, so a
    # refactor of the manifest cannot quietly drop the field again.
    import ast
    tree = ast.parse((REPO / "evals" / "bench_option_b.py").read_text(encoding="utf-8"))
    runs = [node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "run_task"]
    assert runs, "run_task is gone"
    dicts = [node for fn in runs for node in ast.walk(fn)
             if isinstance(node, ast.Dict)
             and any(isinstance(k, ast.Constant) and k.value == "schema_version" for k in node.keys)]
    assert dicts, "no manifest dict literal found in run_task"
    keys = {k.value for d in dicts for k in d.keys if isinstance(k, ast.Constant)}
    assert "code_address" in keys and "schema_version" in keys
