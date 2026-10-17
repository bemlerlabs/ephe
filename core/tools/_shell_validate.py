"""Ephe – run_shell / execute_confirmed_shell tools."""

from __future__ import annotations

import shlex

from core.tools.base import (
    ALLOWED_COMMANDS,
    BLOCKED_PATTERNS,
)

# Separators between command segments (as standalone shlex tokens).
_SEGMENT_SEPARATORS = {";", "|", "&", "&&", "||"}


# Shell redirects write/read files past the whitelist —
# writing belongs in edit_file, reading in read_file.
_REDIRECT_TOKENS = {">", ">>", "<", "<<"}


# W16: interpreter heads with their own flag hardening (eval/REPL semantics).
_INTERPRETER_HEADS = {"python", "python3", "node"}


#: Known, uncritical interpreter flags (version/module/test mode).
_INTERPRETER_OK_FLAGS = {"-m", "-V", "--version", "-q", "-h", "--help", "--test"}


#: Single letters that carry the eval/REPL semantics inside a flag cluster.
_EVAL_LETTERS = {"c", "e", "i"}


# WB-13/G1: `docker`/`docker-compose` are whitelisted heads, but the container
# command and its host mounts live in the argv the head check never reads — the
# same hole the interpreter segment had before W16. A docker segment now carries
# its own subcommand allowlist: only inspection stays.
_DOCKER_HEADS = {"docker", "docker-compose"}

#: Read-only subcommands; none of them starts, enters or builds a container.
_DOCKER_OK_SUBCOMMANDS = {
    "ps", "images", "version", "info", "logs", "port", "stats", "top",
    "history", "diff", "inspect",
}

#: The docker-compose read-only subset.
_DOCKER_COMPOSE_OK_SUBCOMMANDS = {"ps", "logs", "config", "version", "port", "top"}

#: Flags that hand a host path, capability or namespace to a container. Refused
#: under any subcommand, so a later widening of the allowlist cannot reopen the mount.
_DOCKER_HOST_FLAGS = {
    "-v", "--volume", "--mount", "--privileged", "--pid", "--ipc",
    "--net", "--network", "--cap-add", "--cap-drop", "--device",
    "--userns", "--uts", "--security-opt",
}


def _shell_segments(command: str) -> list[list[str]] | None:
    """Splits a command into segments (respecting quotes).

    punctuation_chars=True makes ';|&()' standalone tokens even when they
    stick to the word ('ls;git'), and keeps quoted segments ('"a && b"')
    together. A None return = unparseable (unbalanced quotes).
    """
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:
        return None
    segments: list[list[str]] = [[]]
    for tok in tokens:
        if tok in _SEGMENT_SEPARATORS:
            segments.append([])
        else:
            segments[-1].append(tok)
    return segments


def _validate_interpreter_segment(seg: list[str]) -> str | None:
    """Hardening of the interpreter segments (W16).

    Allowed: a script file as positional arg, '-m module …', version flags.
    Declined: eval '-c'/'-e' and the interactive REPL ('-i', bare head) —
    they bypass the segment whitelist, because the code itself is not checked.
    """
    head = seg[0]
    args = seg[1:]
    if not args:
        return (
            f"⚠️ Security: bare interpreter '{head}' opens an interactive REPL "
            "(blocked); pass a script file or use '-m'."
        )
    for tok in args:
        if not tok.startswith("-"):
            continue
        if tok in _INTERPRETER_OK_FLAGS:
            continue
        letters = {ch for ch in tok.lstrip("-").casefold()}
        if letters & _EVAL_LETTERS:
            return (
                f"⚠️ Security: interpreter flag '{tok}' runs eval/interactive code "
                f"outside the checked segment list (blocked on '{head}')."
            )
    return None


def _validate_docker_segment(seg: list[str]) -> str | None:
    """A docker head alone is not binding; the argv decides.

    The head check confirms the word `docker`; the container command and its
    `-v /:/host` live in the argv it never reads. Read-only subcommands pass;
    run/exec/create/build/… and the host-handing flags do not, because any of
    them reaches the host root past the whitelist.
    """
    head = seg[0]
    args = seg[1:]
    allowed = (
        _DOCKER_COMPOSE_OK_SUBCOMMANDS if head == "docker-compose" else _DOCKER_OK_SUBCOMMANDS
    )
    if not args:
        return (
            f"⚠️ Security: bare '{head}' names no subcommand; use a read-only one "
            f"({', '.join(sorted(allowed))})."
        )
    subcommand = args[0]
    if subcommand not in allowed:
        return (
            f"⚠️ Security: '{head} {subcommand}' is not a read-only subcommand "
            f"({', '.join(sorted(allowed))} allowed) — a container it starts reaches "
            "the host filesystem past the whitelist."
        )
    for tok in args[1:]:
        flag = tok.split("=", 1)[0]
        if flag in _DOCKER_HOST_FLAGS:
            return (
                f"⚠️ Security: docker flag '{flag}' hands a host path, capability or "
                "namespace to the container (blocked)."
            )
    return None


def validate_shell_command(command: str, sandboxed: bool = False) -> str | None:
    """Check a shell command against the security barriers.

    A None return = allowed, otherwise the ⚠️ error message. Barriers:

    1. BLOCKED_PATTERNS — destructive patterns + command/process substitution,
       newlines (raw-string check, catches quote tricks like "$( inside double quotes)").
    2. EVERY segment (; | && || &) must start with an ALLOWED_COMMANDS head —
       not just the first token of the whole command.
    3. Redirects (> >> <) and subshell parentheses are blocked.
    4. Docker segments are limited to read-only subcommands and refused the
       host-handing flags — the head check alone is not binding (G1/WB-13).
    5. Interpreters (-c/-e/-i/bare REPL) are allowed as fully checked only with
       an active Seatbelt sandbox ('sandboxed=True' from the caller).
    """
    if not command or not command.strip():
        return "⚠️ Security: Empty command."

    cmd_lower = command.lower()
    for pattern in BLOCKED_PATTERNS:
        if pattern in cmd_lower:
            return f"⚠️ Security: command contains blocked pattern '{pattern}'."

    segments = _shell_segments(command)
    if segments is None:
        return "⚠️ Security: command not parseable (unbalanced quotes?)."

    heads = [seg[0] for seg in segments if seg]
    if not heads:
        return "⚠️ Security: Empty command."
    for head in heads:
        if head not in ALLOWED_COMMANDS:
            return (
                f"⚠️ Security: command part '{head}' is not in the whitelist ({len(ALLOWED_COMMANDS)} allowed commands)."
            )

    for seg in segments:
        for tok in seg:
            if tok in _REDIRECT_TOKENS:
                return "⚠️ Security: shell redirects (> >> <) are blocked — change files via edit_file."
            if tok in {"(", ")"}:
                return "⚠️ Security: Subshell parentheses are blocked."

    # WB-13/G1: docker segments get their own read-only subcommand allowlist.
    # Unconditional — NOT lifted by `sandboxed`: the daemon runs the container
    # outside the local Seatbelt profile, so a wrapper does not make
    # `docker run -v /:/host` safe.
    for seg in segments:
        if seg and seg[0] in _DOCKER_HEADS:
            refusal = _validate_docker_segment(seg)
            if refusal is not None:
                return refusal

    # W16-P3: interpreter hardening — strict only without a real sandbox wrapper.
    if not sandboxed:
        for seg in segments:
            if seg and seg[0] in _INTERPRETER_HEADS:
                refusal = _validate_interpreter_segment(seg)
                if refusal is not None:
                    return refusal
    return None
