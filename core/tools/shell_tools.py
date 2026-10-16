"""Ephe – run_shell / execute_confirmed_shell tools (aggregator facade).

The implementation lives in the layers _shell_validate (command guard),
_shell_proc (process/docker primitives) and _shell_exec (background tasks +
public tools); this module only re-exports the stable API, so that all
import paths (`from core.tools.shell_tools import ...`) stay unchanged.
"""
from __future__ import annotations

# Facade contract (file header): all core symbols stay importable from HERE —
# tests and callers count on it (pytest patches _docker_run/_docker_teardown
# on shell_tools). noqa: F401, so that lint cleanup never touches them again.
from core.tools._shell_validate import (  # noqa: F401
    _SEGMENT_SEPARATORS,
    _REDIRECT_TOKENS,
    _INTERPRETER_HEADS,
    _INTERPRETER_OK_FLAGS,
    _EVAL_LETTERS,
    _DOCKER_HEADS,
    _DOCKER_OK_SUBCOMMANDS,
    _DOCKER_COMPOSE_OK_SUBCOMMANDS,
    _DOCKER_HOST_FLAGS,
    _shell_segments,
    _validate_interpreter_segment,
    _validate_docker_segment,
    validate_shell_command,
)
from core.tools._shell_exec import (  # noqa: F401
    _BG_TASKS,
    _BG_COUNTER,
    _BG_MAX_TASKS,
    _resolve_cwd,
    _sandbox_args,
    run_shell,
    _exec_bg_task,
    task_output,
    task_stop,
    execute_confirmed_shell,
    run_shell_pty,
)
from core.tools._shell_proc import (  # noqa: F401
    _DOCKER_MANAGED,
    _new_group_kwargs,
    _kill_group,
    _reap,
    _shell_backend,
    SANDBOX_UNAVAILABLE,
    resolve_sandbox,
    _docker_image,
    _docker_run,
    _docker_container_name,
    _ensure_docker_container,
    _docker_teardown,
    _docker_exec,
    _exec_sync,
)

__all__ = [
    "validate_shell_command",
    "run_shell",
    "execute_confirmed_shell",
    "task_output",
    "task_stop",
    "run_shell_pty",
    "_BG_TASKS",
    "_shell_backend",
    "_docker_run",
    "_docker_teardown",
    "_docker_exec",
    "_ensure_docker_container",
    "_sandbox_args",
    "resolve_sandbox",
    "SANDBOX_UNAVAILABLE",
    "_resolve_cwd",
    "_exec_bg_task",
    "_exec_sync",
    "_reap",
    "_kill_group",
    "_new_group_kwargs",
    "_shell_segments",
    "_validate_interpreter_segment",
    "_validate_docker_segment",
]
