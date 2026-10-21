"""The kernel's secret boundary for child processes (GAP-05).

MCP stdio servers, user hooks and shell commands are plugin-reachable process
paths. None of them inherits the host's credential environment. The scrub keeps
the loader and shell basics a child needs (PATH, HOME, locale, library paths,
the SSH agent socket) and drops credential-shaped names and credential-file
pointers. An explicit value a trusted config hands to its own connector is added
by the caller through `extra`; it is then that declared value, not the host's.

Values are never logged here.
"""
from __future__ import annotations

import os
from collections.abc import Mapping

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


def is_secret_name(name: str) -> bool:
    upper = str(name or "").upper()
    if not upper or upper in _NOT_SECRET:
        return False
    if upper in _EXACT_SECRETS or upper in _CREDENTIAL_FILES:
        return True
    return any(part in upper for part in _SECRET_PARTS)


def child_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """A scrubbed copy of the environment, plus explicitly declared values.

    `extra` is for a trusted configuration that owns the connector and names
    its own values. It is the one path by which a credential reaches a child;
    inherited host credentials never do.
    """
    env = {
        str(name): str(value)
        for name, value in os.environ.items()
        if not is_secret_name(name)
    }
    for name, value in (extra or {}).items():
        env[str(name)] = str(value)
    return env
