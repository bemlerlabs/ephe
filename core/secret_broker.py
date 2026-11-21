"""The kernel's secret boundary for child processes (GAP-05).

MCP stdio servers, user hooks and shell commands are plugin-reachable process
paths. None of them inherits the host's credential environment. The child gets
an allowlist of loader and shell basics (PATH, HOME, locale, library paths) and
drops every other name by default; SSH_AUTH_SOCK is the one reviewed exception,
so git/ssh can use the agent the user already authorised. An explicit value a
trusted config hands to its own connector is added by the caller through
`extra`; it is that declared value alone.

Values are never logged here.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

#: Credential-shaped fragments, matched against the upper-cased name.
_SECRET_PARTS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "API_KEY",
    "APIKEY",
    "ACCESS_KEY",
    "PRIVATE_KEY",
    "CREDENTIAL",
    "AUTHORIZATION",
    "COOKIE",
    "SESSION_KEY",
)

#: Names that carry a credential without one of the fragments above.
_EXACT_SECRETS = frozenset(
    {
        "DOCKER_AUTH_CONFIG",
        "NETRC",
        "SENTRY_DSN",
        "OTEL_EXPORTER_OTLP_HEADERS",
    }
)

#: Pointers to files whose content is a credential.
_CREDENTIAL_FILES = frozenset(
    {
        "KUBECONFIG",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "AWS_SHARED_CREDENTIALS_FILE",
        "AWS_CONFIG_FILE",
        "AZURE_CONFIG_DIR",
        "DOCKER_CONFIG",
        "NPM_CONFIG_USERCONFIG",
        "PIP_CONFIG_FILE",
    }
)

#: Harmless names that a fragment would otherwise catch.
_NOT_SECRET = frozenset({"TOKENIZERS_PARALLELISM"})

#: The complete set a child may inherit. Default-deny: a new host variable is
#: not passed until it is named here. Locale prefixes are the only wildcard.
#: The SSH agent is NOT in this set. A plugin or MCP child that needs git over SSH
#: gets the socket only when its own connector names it in `extra`; an inherited
#: agent would let any child sign with the user's keys.
_CHILD_ENV_NAMES = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LOGNAME",
        "SHELL",
        "PWD",
        "TMPDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LANGUAGE",
        "TERM",
        "COLORTERM",
        "NO_COLOR",
        "FORCE_COLOR",
        "DISPLAY",
        "WAYLAND_DISPLAY",
        "DBUS_SESSION_BUS_ADDRESS",
    }
)
_CHILD_ENV_PREFIXES = ("LC_",)


def is_secret_name(name: str) -> bool:
    upper = str(name or "").upper()
    if not upper or upper in _NOT_SECRET:
        return False
    if upper in _EXACT_SECRETS or upper in _CREDENTIAL_FILES:
        return True
    return any(part in upper for part in _SECRET_PARTS)


def child_env(
    extra: Mapping[str, str] | None = None, *, home: str | os.PathLike[str] | None = None
) -> dict[str, str]:
    """A scrubbed copy of the environment, plus explicitly declared values.

    `extra` is for a trusted configuration that owns the connector and names
    its own values. It is the one path by which a credential, including
    `SSH_AUTH_SOCK`, reaches a child; inherited host credentials never do.
    """
    env = {
        str(name): str(value)
        for name, value in os.environ.items()
        if str(name).upper() in _CHILD_ENV_NAMES
        or any(str(name).upper().startswith(prefix) for prefix in _CHILD_ENV_PREFIXES)
    }
    env["PATH"] = hydrate_path(env.get("PATH"))
    if home is not None:
        root = str(home)
        env["HOME"] = root
        env["TMPDIR"] = str(Path(root) / "tmp")
    for name, value in (extra or {}).items():
        env[str(name)] = str(value)
    return env


# A Finder-launched app inherits launchd's minimal PATH, which never contains
# Homebrew: the shell tool answered "command not found" for node, npm and pnpm
# while the same user's terminal had them. The heads below go in front when
# they exist on disk; the POSIX core stays at the end so a child never runs
# with a PATH that cannot find `sh` at all.
_MACOS_TOOL_PATH = ("/opt/homebrew/bin", "/opt/homebrew/sbin", "/usr/local/bin")
_POSIX_CORE_PATH = ("/usr/bin", "/bin", "/usr/sbin", "/sbin")


def hydrate_path(
    value: "str | None",
    *,
    platform: str | None = None,
    exists: "Callable[[str], bool] | None" = None,
) -> str:
    """The PATH a child gets: tool heads first, then what was inherited."""
    current = [entry for entry in (value or "").split(os.pathsep) if entry]
    head: list[str] = []
    if (platform or sys.platform) == "darwin":
        is_dir = exists or os.path.isdir
        head = [entry for entry in _MACOS_TOOL_PATH if is_dir(entry)]
    tail = list(_POSIX_CORE_PATH) if (platform or sys.platform) != "win32" else []
    seen: set[str] = set()
    ordered: list[str] = []
    for entry in [*head, *current, *tail]:
        if entry in seen:
            continue
        seen.add(entry)
        ordered.append(entry)
    return os.pathsep.join(ordered)
