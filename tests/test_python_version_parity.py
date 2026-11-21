"""The two version classes the matrix keeps re-growing.

`requires-python` says >=3.10 and the legs run 3.10 through 3.13, but the tracked tree has
twice carried code that only works on the newer interpreters. A stdlib `tomllib` read (3.11+)
that made `core/environment_mirror.py` answer None for every TOML tool config on the 3.10 leg,
and a subprocess that named its interpreter through PATH rather than the job's own, which is
green on macOS and dies on the shared-linked arm64 legs with exit 127. Neither class fails at
the place it was written, so the rule lives where a run can see it.

Both rules are read off the AST of the tracked files, each with a plant, because a check nobody
has seen fail is a reminder. The compile pass is here for the same reason: it is the only place
the whole tracked tree is handed to the interpreter that has to accept it, which is where
syntax newer than the leg shows up.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

from tests.toml_compat import tomllib

ROOT = Path(__file__).resolve().parents[1]

#: An interpreter named as a bare word is resolved by PATH, not by the job.
PATH_INTERPRETER = re.compile(r"^python(3(\.\d+)?)?$")

#: Files that spawn something: the call shapes whose first argv element chooses the interpreter.
SPAWN_NAMES = {
    "run",
    "Popen",
    "call",
    "check_output",
    "check_call",
    "create_subprocess_exec",
}


def tracked_files(suffix: str) -> list[Path]:
    listing = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", f"*{suffix}"],
        text=True,
        capture_output=True,
        check=True,
    )
    return [ROOT / line for line in listing.stdout.splitlines() if (ROOT / line).is_file()]


#: A direct read of the stdlib module. `from tests.toml_compat import tomllib` is the sanctioned
#: shape and is deliberately not matched: naming the shim as an offender taught the rule nothing.
DIRECT_TOMLLIB = re.compile(r"^\s*(?:try:\s*)?import tomllib\b|^\s*from tomllib\b")


def bare_toml_reads(source: str) -> list[int]:
    """Lines where this file reaches for stdlib `tomllib` without naming the 3.10 backport.

    The rule is one shape: a file that imports the stdlib module directly has to mention `tomli`
    too. That holds for each of the three readers the tree carries today (`tests/toml_compat.py`,
    `core/environment_mirror.py`, the heredoc in `scripts/uv_lock_sync.sh`) and it needs no
    exception list, which is the property that keeps it true after the next file arrives.
    """
    lines = [
        lineno
        for lineno, line in enumerate(source.splitlines(), 1)
        if DIRECT_TOMLLIB.search(line)
    ]
    if not lines:
        return []
    if re.search(r"^\s*(?:except[^:]*:\s*)?import tomli\b", source, re.MULTILINE):
        return []
    return lines


def path_interpreter_spawns(tree: ast.Module) -> list[int]:
    """Lines where a child process is started with a PATH interpreter name."""
    hits: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        called = ast.unparse(node.func).rsplit(".", 1)[-1]
        if called not in SPAWN_NAMES or not node.args:
            continue
        argv = node.args[0]
        if not isinstance(argv, (ast.List, ast.Tuple)) or not argv.elts:
            continue  # argv assembled elsewhere; the literal head is not visible here
        head = argv.elts[0]
        if (
            isinstance(head, ast.Constant)
            and isinstance(head.value, str)
            and PATH_INTERPRETER.match(head.value.strip())
        ):
            hits.append(node.lineno)
    return hits


def test_every_tracked_python_file_parses_on_the_running_interpreter():
    """The class that cannot be fixed later: syntax the leg's interpreter refuses to parse."""
    failures: list[str] = []
    files = tracked_files(".py")
    for path in files:
        try:
            ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as error:
            failures.append(f"{path.relative_to(ROOT)}:{error.lineno}: {error.msg}")
    assert not failures, (
        f"{sys.version.split()[0]} cannot parse {len(failures)} tracked file(s): "
        + "; ".join(failures[:8])
    )
    print(f"parsed {len(files)} tracked .py files on {sys.version.split()[0]}")


def test_no_tracked_reader_imports_tomllib_without_the_310_backport():
    offenders: list[str] = []
    for path in tracked_files(".py") + tracked_files(".sh"):
        lines = bare_toml_reads(path.read_text(encoding="utf-8"))
        offenders += [f"{path.relative_to(ROOT)}:{line}" for line in lines]
    assert not offenders, (
        "`tomllib` is stdlib from 3.11 while requires-python is >=3.10, so a bare read answers "
        "nothing at all on the 3.10 leg: " + ", ".join(offenders)
    )


def test_the_toml_reader_returns_data_on_the_interpreter_running_the_suite():
    """The runtime half the static rule cannot claim: on 3.10 the backport has to be installed.

    `tomli` is marker-scoped in the main dependencies, so this is also the check that the leg
    installed the project the way CI does -- a leg that skips the install would pass the AST rule
    and still read None.
    """
    assert tomllib.loads('[tool.x]\ny = "z"') == {"tool": {"x": {"y": "z"}}}
    if sys.version_info < (3, 11):
        assert tomllib.__name__ == "tomli", (
            f"on {sys.version.split()[0]} the shim must resolve to the backport, got "
            f"{tomllib.__name__}"
        )


def test_no_test_spawns_a_child_interpreter_named_through_path():
    """Work item #27. `[sys.executable, ...]` is the job's own interpreter; `python3` is whatever
    a login shell fronts, and on the arm64 legs that difference is exit 127 or a foreign
    site-packages, while macOS has both on PATH and stays green."""
    offenders: list[str] = []
    for path in tracked_files(".py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue  # the parse test owns that verdict
        offenders += [
            f"{path.relative_to(ROOT)}:{line}" for line in path_interpreter_spawns(tree)
        ]
    assert not offenders, (
        "a child interpreter has to be the one running the test: " + ", ".join(offenders)
    )


def test_the_two_rules_bite_on_planted_sources():
    """Without this the four rules above could pass by matching nothing at all."""
    assert bare_toml_reads("import tomllib\n\ndata = tomllib.loads(x)\n") == [1]
    assert bare_toml_reads(
        "try:\n    import tomllib\nexcept ModuleNotFoundError:\n    import tomli as tomllib\n"
    ) == []
    # The sanctioned shape, and the reason the rule reads direct imports only: seven tracked test
    # modules import the shim today, and calling one of them an offender would teach the rule
    # nothing while making the next correct file look like a defect.
    assert bare_toml_reads("from tests.toml_compat import tomllib\n\ndata = tomllib.loads(x)\n") == []
    planted = ast.parse(
        "import subprocess\nsubprocess.run(['python3', '-c', 'pass'], env={'PATH': '/usr/bin'})\n"
    )
    assert path_interpreter_spawns(planted) == [2]
    clean = ast.parse("import subprocess, sys\nsubprocess.run([sys.executable, '-c', 'pass'])\n")
    assert path_interpreter_spawns(clean) == []
