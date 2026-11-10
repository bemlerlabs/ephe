"""The shell and file tools. Each one asks the host.

The worker has no shell and cannot import the application. The bridge
handle is the third argument. The text it brings back is the tool result,
including the failure line the kernel tool already writes.
"""

from __future__ import annotations


def _text(page) -> str:
    body = str((page or {}).get("text") or "")
    if (page or {}).get("truncated"):
        return body + "\n[truncated]"
    return body


def _failure(name: str, exc: BaseException) -> str:
    detail = getattr(exc, "detail", "") or getattr(exc, "code", "") or type(exc).__name__
    return f"[tool-error '{name}': {detail}]"


def _ask(name: str, call):
    try:
        page = call()
    except Exception as exc:
        return _failure(name, exc)
    return _text(page)


def _kwargs(arguments, names):
    arguments = arguments or {}
    extra = {}
    for name in names:
        if name in arguments and arguments[name] is not None:
            extra[name] = arguments[name]
    return extra


def run_shell(arguments, _state_dir, bridge):
    arguments = arguments or {}
    command = "" if arguments.get("command") is None else str(arguments.get("command"))
    return _ask(
        "run_shell",
        lambda: bridge.run_shell(command, **_kwargs(arguments, ("cwd", "run_in_background"))),
    )


def read_file(arguments, _state_dir, bridge):
    arguments = arguments or {}
    path = "" if arguments.get("path") is None else str(arguments.get("path"))
    return _ask("read_file", lambda: bridge.read_file(path, **_kwargs(arguments, ("offset", "limit"))))


def write_file(arguments, _state_dir, bridge):
    arguments = arguments or {}
    path = "" if arguments.get("path") is None else str(arguments.get("path"))
    content = "" if arguments.get("content") is None else str(arguments.get("content"))
    return _ask("write_file", lambda: bridge.write_file(path, content))


def edit_file(arguments, _state_dir, bridge):
    arguments = arguments or {}
    path = "" if arguments.get("path") is None else str(arguments.get("path"))
    old_string = "" if arguments.get("old_string") is None else str(arguments.get("old_string"))
    new_string = "" if arguments.get("new_string") is None else str(arguments.get("new_string"))
    return _ask(
        "edit_file",
        lambda: bridge.edit_file(
            path, old_string, new_string, **_kwargs(arguments, ("replace_all",))
        ),
    )


def list_directory(arguments, _state_dir, bridge):
    arguments = arguments or {}
    path = "" if arguments.get("path") is None else str(arguments.get("path"))
    return _ask("list_directory", lambda: bridge.list_directory(path))


def file_search(arguments, _state_dir, bridge):
    arguments = arguments or {}
    query = "" if arguments.get("query") is None else str(arguments.get("query"))
    return _ask("file_search", lambda: bridge.file_search(query, **_kwargs(arguments, ("path",))))


def load_workspace(arguments, _state_dir, bridge):
    arguments = arguments or {}
    path = "" if arguments.get("path") is None else str(arguments.get("path"))
    return _ask(
        "load_workspace",
        lambda: bridge.load_workspace(path, **_kwargs(arguments, ("extensions", "max_depth"))),
    )


def analyze_project(arguments, _state_dir, bridge):
    arguments = arguments or {}
    path = "" if arguments.get("path") is None else str(arguments.get("path"))
    return _ask("analyze_project", lambda: bridge.analyze_project(path))


def run_tests(arguments, _state_dir, bridge):
    arguments = arguments or {}
    command = "" if arguments.get("command") is None else str(arguments.get("command"))
    return _ask("run_tests", lambda: bridge.run_tests(command, **_kwargs(arguments, ("cwd",))))


def run_linter(arguments, _state_dir, bridge):
    arguments = arguments or {}
    path = "" if arguments.get("path") is None else str(arguments.get("path"))
    return _ask(
        "run_linter",
        lambda: bridge.run_linter(path, **_kwargs(arguments, ("fix", "max_issues"))),
    )


def format_code(arguments, _state_dir, bridge):
    arguments = arguments or {}
    path = "" if arguments.get("path") is None else str(arguments.get("path"))
    return _ask(
        "format_code",
        lambda: bridge.format_code(path, **_kwargs(arguments, ("check_only",))),
    )


def scaffold_project(arguments, _state_dir, bridge):
    arguments = arguments or {}
    target_dir = "" if arguments.get("target_dir") is None else str(arguments.get("target_dir"))
    return _ask(
        "scaffold_project",
        lambda: bridge.scaffold_project(
            target_dir,
            **_kwargs(arguments, ("template", "project_name", "description", "author")),
        ),
    )
