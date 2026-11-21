"""A child that execs a Python interpreter may not be handed an environment built from literals.

The rule this holds is the one four red Linux legs wrote: `actions/setup-python` puts a
shared-linked arm64 CPython in the runner's tool cache and exports the loader directory into the
*job* environment, so a child whose environment is a literal dict has no `LD_LIBRARY_PATH` and
dies before it runs — exit 127 with `error while loading shared libraries`. `tests/subprocess_env.py`
carries the loader keys on purpose, and `env_without_tools()` keeps the whole inherited set while
removing one tool from PATH. `371da670`, `385a364d` and `68acd31d` are the three times this class
was re-opened by a test written the day after the fix, each time green on macOS where the local
interpreter links libpython statically.

What it decides, in one direction only: a call fails here when its first argument is a Python
interpreter (`sys.executable`, `python`, `python3`) and the environment handed to it cannot be
followed back to `hermetic_env`, `env_without_tools`, or an expression that contains the parent's
environment. Anywhere else it stays silent, because an isolated `HOME` for a `git` commit is a
different requirement and a filtered `PATH` for `npm` is the point of the test.

What it cannot see is listed in `blind_spots()` and printed with every run, so the file does not
claim a coverage it does not have: a child whose argv is assembled in a variable, an environment
built in a fixture or a helper outside the file, `asyncio.create_subprocess_exec`, `os.exec*`, and
a helper that reaches the interpreter through a second function of its own.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent

#: An environment expression naming any of these already carries the parent's loader view.
INHERITED = ("os.environ", "hermetic_env", "env_without_tools")

#: The names of the exec'ables this class is about: an interpreter that may be shared-linked.
INTERPRETERS = ("sys.executable", "python", "python3")

_UNRESOLVED = "cannot be followed in this file"

#: The file being scanned, by function name, so a local helper can be read for what it returns.
_function_sources: dict[str, str] = {}


def _interpreter_child(node: ast.Call) -> bool:
    """True when the call's argv head is an interpreter name rather than a system tool."""
    if not node.args:
        return False
    head = node.args[0]
    if isinstance(head, (ast.List, ast.Tuple)) and head.elts:
        head = head.elts[0]
    text = ast.unparse(head)
    return text in INTERPRETERS or text.startswith("python") or "sys.executable" in text


def _resolves(name: str, tree: ast.Module, depth: int = 0) -> str:
    """Follow one file-local name to the expression that produced it, twice at most."""
    if depth > 1:
        return _UNRESOLVED
    for node in ast.walk(tree):
        targets = getattr(node, "targets", [])
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name and hasattr(node, "value"):
                value = node.value
                text = ast.unparse(value)
                if any(marker in text for marker in INHERITED):
                    return "inherited"
                if isinstance(value, ast.Name):
                    return _resolves(value.id, tree, depth + 1)
                return "literal"
            if isinstance(target, ast.Name) and target.id == name and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return "fixture or parameter"
    return _UNRESOLVED


def scan(source: str) -> tuple[list[str], list[str]]:
    """(offenders, reports) for one test module's source."""
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        # This interpreter cannot judge the file. pytest's collector already refuses it under the
        # owning file's own node id, so raising here would only steal that attribution -- and on an
        # older leg (a 3.10 leg meeting 3.12 syntax) it would be this guard that goes red.
        return [], [f"unreadable source ({error.msg} at line {error.lineno}), not judged"]
    _function_sources.clear()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _function_sources[node.name] = ast.unparse(node)
    offenders: list[str] = []
    reports: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = ast.unparse(node.func)
        if func.rsplit(".", 1)[-1] not in {"run", "Popen", "call", "check_output", "check_call",
                                           "create_subprocess_exec", "create_subprocess_shell"}:
            continue
        if not func.startswith(("subprocess.", "asyncio.")):
            continue
        env = next((kw.value for kw in node.keywords if kw.arg == "env"), None)
        if env is None:
            continue  # no env at all means the child inherits everything, which is its own choice
        text = ast.unparse(env)
        if any(marker in text for marker in INHERITED):
            continue
        if isinstance(env, ast.Call) and _is_helper(env):
            continue
        state = ("literal" if isinstance(env, ast.Dict)
                 else _resolves(env.id, tree) if isinstance(env, ast.Name)
                 else "literal" if isinstance(env, ast.Call)
                 else _UNRESOLVED)
        line = f"env={text[:60]}"
        if state == _UNRESOLVED or state == "fixture or parameter":
            reports.append(f"line {node.lineno}: {line} {_UNRESOLVED}")
        elif state == "literal" and _interpreter_child(node):
            offenders.append(f"line {node.lineno}: interpreter child with {line}")
        elif state == "literal":
            reports.append(f"line {node.lineno}: {line} on a non-interpreter child, left alone")
    return offenders, reports


def _is_helper(node: ast.Call) -> bool:
    """A call that carries the parent's environment: the two helpers, or a file-local one whose
    own body reaches for them. A helper that delegates through a second function of its own is
    beyond this scan and is listed in `blind_spots()`.
    """
    name = ast.unparse(node.func).rsplit(".", 1)[-1]
    if name in {"hermetic_env", "env_without_tools"}:
        return True
    body = _function_sources.get(name)
    return body is not None and any(marker in body for marker in INHERITED)


def blind_spots() -> tuple[str, ...]:
    """The shapes this scan answers "reported" for instead of "clean"."""
    return (
        "argv assembled in a variable, so the interpreter is not visible in the source",
        "an environment built in a fixture, a conftest, or a helper imported from elsewhere",
        "a helper that reaches the interpreter through a second function of its own",
        "os.exec* and multiprocessing spawns, which are not subprocess calls",
        "a module this interpreter cannot parse, which is reported per file rather than judged",
    )


def test_every_tracked_test_file_hands_its_interpreter_children_a_carried_environment():
    offenders: list[str] = []
    reports: list[str] = []
    for path in sorted(TESTS.glob("test_*.py")):
        found, reported = scan(path.read_text(encoding="utf-8"))
        offenders += [f"{path.name}: {line}" for line in found]
        reports += [f"{path.name}: {line}" for line in reported]
    assert not offenders, (
        "interpreter children built from a literal environment die at exec on the arm64 legs "
        "(exit 127, no LD_LIBRARY_PATH). Use tests/subprocess_env.py::hermetic_env or "
        "env_without_tools: " + "; ".join(offenders)
    )
    print("\n".join(reports))
    print(f"not decided by this scan: {len(reports)} call(s); blind to: " + " | ".join(blind_spots()))


def test_a_literal_environment_on_an_interpreter_child_is_named():
    """The instrument has to bite before it is trusted."""
    source = (
        "import subprocess, sys\n"
        "subprocess.run([sys.executable, '-c', 'pass'], env={'PATH': '/usr/bin:/bin', "
        "'HOME': '/tmp/h'})\n"
    )
    offenders, reports = scan(source)
    assert len(offenders) == 1, (offenders, reports)
    assert "interpreter child" in offenders[0]


def test_a_module_this_interpreter_cannot_parse_is_reported_not_raised():
    """`def test GIVEN_...` reached the tree during a matrix leg: a guard that dies on someone
    else's unparseable file hands that file's verdict to this node id, and on an older leg it
    would do it on purpose. The collector owns the syntax error; the guard names what it could
    not read."""
    offenders, reports = scan("def test GIVEN_routing_off_WHEN_a_step_is_decided_THEN_it_answers():\n")
    assert offenders == []
    assert any("unreadable source" in line for line in reports), reports
    offenders, reports = scan(
        "import subprocess, sys\n"
        "subprocess.run([sys.executable, '-c', 'p'], env={'PATH': '/usr/bin'})\n"
    )
    assert len(offenders) == 1, (offenders, reports)


def test_an_inherited_or_helper_environment_is_clean():
    for source in (
        "import subprocess, sys\nsubprocess.run([sys.executable, '-c', 'p'], env=hermetic_env(HOME='/x'))\n",
        "import os, subprocess, sys\nsubprocess.run([sys.executable, '-c', 'p'], env={**os.environ, 'HOME': '/x'})\n",
        "import subprocess, sys\nenv = env_without_tools('npm')\nsubprocess.run([sys.executable, 'x'], env=env)\n",
        "import subprocess\nsubprocess.run(['git', 'add', '-A'], env={'PATH': '/usr/bin:/bin', 'HOME': '/tmp/h'})\n",
    ):
        offenders, _reports = scan(source)
        assert not offenders, (source, offenders)


@pytest.mark.parametrize("argv", [["git", "add"], ["npm", "run", "build"], ["sh", "-c", "true"]])
def test_a_system_tool_child_is_left_to_its_own_environment_choice(argv):
    source = ("import subprocess\nsubprocess.run(%r, env={'PATH': '/usr/bin:/bin'})\n" % (argv,))
    offenders, reports = scan(source)
    assert not offenders
    assert any("non-interpreter" in line for line in reports), reports
