"""Ephe – run_shell / execute_confirmed_shell tools."""

from __future__ import annotations

import os
import shlex
from pathlib import Path

from core.path_guard import denied, secret_shaped
from core.tools.base import (
    ALLOWED_COMMANDS,
    BLOCKED_PATTERNS,
    _is_path_allowed,
)

# Separators between command segments (as standalone shlex tokens).
_SEGMENT_SEPARATORS = {";", "|", "&", "&&", "||"}


# Shell redirects write/read files past the whitelist —
# writing belongs in edit_file, reading in read_file.
_REDIRECT_TOKENS = {">", ">>", "<", "<<"}


# W16: interpreter heads with their own flag hardening (eval/REPL semantics).
# bash is the same kind of head: a script is a file, eval flags are code.
_INTERPRETER_HEADS = {"python", "python3", "node", "bash"}


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


# Heads whose arguments name files. The head check never read those arguments,
# so `cat` could open a credential-shaped file or a path outside the file-tool
# roots. The sandbox does not lift this: its profile still allows reads.
_FILE_HEADS = {
    "cat", "head", "tail", "wc", "grep", "sort", "cut",
    "file", "stat", "cp", "mv", "touch", "chmod", "mkdir",
    "open", "vim", "nano", "code", "find", "ls",
    "ffmpeg", "ffprobe",
}

# The next token is an option value. Path flags are listed separately.
_FLAG_VALUES: dict[str, set[str]] = {
    "head": {"-n", "-c", "--lines", "--bytes"},
    "tail": {"-n", "-c", "--lines", "--bytes"},
    "grep": {
        "-e", "-f", "-m", "-A", "-B", "-C",
        "--regexp", "--file", "--max-count", "--context",
    },
    "sort": {"-k", "-t", "-S", "--key", "--field-separator"},
    "cut": {"-d", "-f", "--delimiter", "--fields"},
    "find": {
        "-name", "-iname", "-path", "-regex", "-type", "-maxdepth", "-mindepth",
        "-size", "-newer", "-printf", "-user", "-group",
    },
    "ffmpeg": {
        "-b", "-r", "-s", "-t", "-ss", "-to", "-vf", "-af", "-c", "-c:v", "-c:a",
        "-f", "-map", "-metadata", "-q:v",
    },
    "ffprobe": {"-v", "-show_entries", "-select_streams", "-of", "-o"},
    "git": {
        "-m", "-c", "--message", "--author", "-b", "--branch",
        "--format", "--pretty", "-n", "--max-count",
    },
    "cp": {"-S", "--suffix"},
    "mv": {"-S", "--suffix"},
}

# The next token is a path and has to pass the file door.
_FLAG_PATHS: dict[str, set[str]] = {
    "sort": {"-o", "--output"},
    "cp": {"-t", "--target-directory"},
    "mv": {"-t", "--target-directory"},
    "ffmpeg": {"-i"},
    "ffprobe": {"-i"},
    "git": {"-C", "--git-dir", "--work-tree"},
}

_FIND_BLOCKED = {
    "-exec", "-execdir", "-ok", "-okdir", "-delete",
    "-fprint", "-fprintf", "-fls", "-fprint0",
}

# Exact credential names that carry no dot. A bare word such as "token" stays
# a sentence, so an eval body may mention it.
_EXACT_SECRET_NAMES = {
    "credentials", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
    "authorized_keys", "known_hosts",
}

# Device nodes the seatbelt profile already names. They are not user files.
_DEVICE_PATHS = {
    "/dev/null",
    "/dev/tty",
    "/dev/zero",
    "/dev/stdin",
    "/dev/stdout",
    "/dev/stderr",
}

_PATH_REFUSAL = (
    "⚠️ Security: a shell file argument stays inside the file-tool roots, "
    "and a credential-shaped name is refused."
)

_FIND_REFUSAL = "⚠️ Security: find -exec, -ok and -delete are refused."

_INTERPRETER_VALUE_FLAGS = {"-m", "-W", "-X"}


def _workspace_root() -> str:
    from core.engine_config import get_workspace_dir

    return get_workspace_dir()


def _named_secret(token: str) -> bool:
    """A credential-shaped filename. A bare word such as ``token`` is not one."""
    name = Path(token).name.lower()
    if not name or name in {".", ".."} or not secret_shaped(name):
        return False
    if name.startswith(".") or "." in name:
        return True
    return name in _EXACT_SECRET_NAMES


def _path_shaped(token: str) -> bool:
    if token.startswith(("~", "/", ".")) or "/" in token or "\\" in token:
        return True
    return _named_secret(token)


def _is_device(real: Path) -> bool:
    text = os.path.normpath(str(real))
    if text in _DEVICE_PATHS:
        return True
    return text == "/dev/fd" or text.startswith("/dev/fd" + os.sep)


def _check_resolved(path: Path) -> str | None:
    try:
        real = path.expanduser().resolve()
    except (OSError, RuntimeError, ValueError):
        return _PATH_REFUSAL
    if secret_shaped(path) or secret_shaped(real) or denied(real):
        return _PATH_REFUSAL
    if _is_device(real):
        return None
    if not _is_path_allowed(real):
        return _PATH_REFUSAL
    return None


def _glob_is_secret(token: str) -> bool:
    lowered = token.lower()
    pieces = (
        ".env", ".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".kdbx",
        "credential", "secret", "token", "id_rsa", "id_ed25519", "authorized_keys",
    )
    return any(piece in lowered for piece in pieces)


def _glob_refusal(token: str, root: str) -> str | None:
    """A glob is judged on what it matches, not on how the pattern is spelled.

    `..` is not a refusal here. The ban refused `src/../docs/*.md`, which ends
    inside the root, on the same line as `../.ssh/*.md`, which does not, and the
    loop below already decides both: `pathlib` walks a `..` the same way the shell
    does, and every match goes through the same door as a plain file argument. A
    name check stays on the text, because a pattern can name a credential without
    matching anything.
    """
    if "**" in token or _glob_is_secret(token):
        return _PATH_REFUSAL
    expanded = os.path.expanduser(os.path.expandvars(token))
    path = Path(expanded)
    if path.is_absolute():
        base = path.parent
        pattern = path.name
        if _check_resolved(base) is not None:
            return _PATH_REFUSAL
    else:
        base = Path(root)
        pattern = token
    try:
        matches = []
        for index, match in enumerate(base.glob(pattern)):
            if index >= 200:
                return _PATH_REFUSAL
            matches.append(match)
    except (OSError, ValueError):
        return _PATH_REFUSAL
    for match in matches:
        if _check_resolved(match) is not None:
            return _PATH_REFUSAL
    return None


def _check_path_token(token: str, root: str) -> str | None:
    if not token:
        return None
    if "$" in token:
        expanded = os.path.expandvars(token)
        if "$" in expanded:
            return _PATH_REFUSAL
        token = expanded
    if any(ch in token for ch in "*?["):
        return _glob_refusal(token, root)
    if secret_shaped(token):
        return _PATH_REFUSAL
    path = Path(os.path.expanduser(token))
    if not path.is_absolute():
        path = Path(root) / path
    return _check_resolved(path)


def _split_flag(token: str) -> tuple[str, str | None]:
    if token.startswith("--") and "=" in token:
        flag, value = token.split("=", 1)
        return flag, value
    return token, None


def _attached_path(head: str, token: str) -> str | None:
    for flag in _FLAG_PATHS.get(head, ()):
        if len(flag) == 2 and token.startswith(flag) and token != flag and not token.startswith("--"):
            return token[len(flag):]
    return None


def _positional_paths(head: str, args: list[str]) -> list[str]:
    """Path operands of one segment. Option values that are not paths stay out."""
    paths: list[str] = []
    values = _FLAG_VALUES.get(head, set())
    path_flags = _FLAG_PATHS.get(head, set())
    index = 0
    while index < len(args):
        token = args[index]
        if token == "--":
            paths.extend(args[index + 1:])
            break
        attached = _attached_path(head, token)
        if attached is not None:
            paths.append(attached)
            index += 1
            continue
        if token.startswith("-") and token != "-":
            flag, inline = _split_flag(token)
            if flag in path_flags:
                if inline is not None:
                    paths.append(inline)
                elif index + 1 < len(args):
                    index += 1
                    paths.append(args[index])
            elif flag in values and inline is None and index + 1 < len(args):
                index += 1
            index += 1
            continue
        paths.append(token)
        index += 1
    return paths


def _grep_files(args: list[str], paths: list[str]) -> list[str]:
    flags = {_split_flag(token)[0] for token in args if token.startswith("-")}
    if flags & {"-e", "-f", "--regexp", "--file"}:
        return paths
    return paths[1:]


def _chmod_paths(paths: list[str]) -> list[str]:
    if not paths:
        return paths
    mode = paths[0]
    if mode.isdigit() or (any(mark in mode for mark in "+-=") and "/" not in mode and not mode.startswith(".")):
        return paths[1:]
    return paths


def _body_token(token: str, root: str) -> str | None:
    if not token or token.startswith("-") or token in "()[]{}.,:;":
        return None
    if _named_secret(token):
        return _PATH_REFUSAL
    if token.startswith(("~", "/", ".")) or "/" in token or "\\" in token:
        return _check_path_token(token, root)
    return None


def _body_refusal(body: str, root: str) -> str | None:
    quoted: list[str] = []
    collected = ""
    marker = ""
    for ch in body:
        if marker:
            if ch == marker:
                quoted.append(collected)
                collected = ""
                marker = ""
            else:
                collected += ch
            continue
        if ch in {"'", '"'}:
            marker = ch
    try:
        lex = shlex.shlex(body, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        tokens = list(lex)
    except ValueError:
        tokens = body.split()
    for token in [*tokens, *quoted]:
        refusal = _body_token(token, root)
        if refusal is not None:
            return refusal
    return None


def _eval_cluster(token: str) -> bool:
    if not token.startswith("-") or token.startswith("--") or token in _INTERPRETER_OK_FLAGS:
        return False
    return bool(set(token.lstrip("-").casefold()) & _EVAL_LETTERS)


def _interpreter_paths(args: list[str], root: str) -> str | None:
    paths: list[str] = []
    bodies: list[str] = []
    index = 0
    while index < len(args):
        token = args[index]
        flag, inline = _split_flag(token)
        if flag in {"-c", "-e", "--eval"} or _eval_cluster(token):
            if inline is not None:
                bodies.append(inline)
            elif index + 1 < len(args):
                index += 1
                bodies.append(args[index])
        elif flag in _INTERPRETER_VALUE_FLAGS:
            if inline is None and index + 1 < len(args):
                index += 1
        elif not token.startswith("-"):
            paths.append(token)
        index += 1
    for token in paths:
        refusal = _check_path_token(token, root)
        if refusal is not None:
            return refusal
    for body in bodies:
        refusal = _body_refusal(body, root)
        if refusal is not None:
            return refusal
    return None


def _git_paths(args: list[str], root: str) -> str | None:
    for token in _positional_paths("git", args):
        candidates = [token]
        if ":" in token:
            candidates.append(token.split(":")[-1])
        for candidate in candidates:
            if _named_secret(candidate):
                return _PATH_REFUSAL
            if _path_shaped(candidate):
                refusal = _check_path_token(candidate, root)
                if refusal is not None:
                    return refusal
    return None


def _find_blocked(args: list[str]) -> str | None:
    for token in args:
        flag = _split_flag(token)[0]
        if flag in _FIND_BLOCKED:
            return _FIND_REFUSAL
    return None


def _refuse_segment_paths(seg: list[str], root: str) -> str | None:
    head = seg[0]
    args = seg[1:]
    if head == "find":
        blocked = _find_blocked(args)
        if blocked is not None:
            return blocked
    if head in _INTERPRETER_HEADS:
        return _interpreter_paths(args, root)
    if head == "git":
        return _git_paths(args, root)
    if head not in _FILE_HEADS:
        return None
    paths = _positional_paths(head, args)
    if head == "grep":
        paths = _grep_files(args, paths)
    if head == "chmod":
        paths = _chmod_paths(paths)
    for token in paths:
        refusal = _check_path_token(token, root)
        if refusal is not None:
            return refusal
    return None


def _whitelist_refusal(head: str) -> str:
    import difflib

    closest = difflib.get_close_matches(head, sorted(ALLOWED_COMMANDS), n=1, cutoff=0.8)
    hint = f" Closest allowed command: {closest[0]}." if closest else ""
    return (
        f"⚠️ Security: command part '{head}' is not in the whitelist "
        f"({len(ALLOWED_COMMANDS)} allowed commands).{hint}"
    )


def validate_shell_command(
    command: str,
    sandboxed: bool = False,
    root: str | None = None,
) -> str | None:
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
    6. File arguments stay inside the file-tool roots. A credential-shaped
       name is refused with the sandbox on and with it off. An interpreter
       eval body is scanned for the same names.
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
            return _whitelist_refusal(head)

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

    # File arguments stay checked with the sandbox on. The profile allows reads,
    # so a wrapped `cat` of a credential-shaped name would still print it.
    base = root or _workspace_root()
    for seg in segments:
        if not seg:
            continue
        refusal = _refuse_segment_paths(seg, base)
        if refusal is not None:
            return refusal
    return None
