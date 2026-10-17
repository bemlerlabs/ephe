from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

MAX_VOICE_BYTES = 200 * 1024 * 1024

# Constants + engine-choice shim (from ephe_cli.py)
try:
    from core._version import __version__ as EPHE_VERSION
except Exception:  # standalone source-tree run without the core/ package
    # The same sentinel core/_version.py answers when no version can be read; a
    # literal born here would be a second home for the number.
    EPHE_VERSION = "0.0.0+unknown"

# W16: goal-loop class as a module attribute (testable via monkeypatch.setattr).
try:
    from core.goal_loop import GoalRunner
except Exception:  # pragma: no cover — standalone case as above
    GoalRunner = None  # type: ignore


# Engine-choice persistence (core/engine_config.py): `ephe tui` starts
# without a model flag — the user picks their engine once, the config is
# stored to ~/.ephe/engine.json and reused on every start.
try:
    from core.engine_config import (
        EngineChoice,
        LOCAL_OLLAMA,
        OPENAI_COMPAT,
        load_engine_config,
        save_engine_config,
    )
except Exception:  # standalone source-tree run without the core/ package
    class EngineChoice:  # type: ignore
        """Defensive shim – functionally identical to the real module."""

        def __init__(self, provider: str, model: str, api_url: str | None = None) -> None:
            self.provider = provider
            self.model = model
            self.api_url = api_url

        def to_flags(self) -> list[str]:
            flags = ["--model", self.model]
            if self.api_url:
                flags += ["--api-url", self.api_url]
            return flags

        def apply_env(self) -> None:
            os.environ["EPHE_MODEL_PROVIDER"] = self.provider
            os.environ["EPHE_MODEL"] = os.environ["EPHE_MODEL"] = self.model
            if self.api_url:
                os.environ["EPHE_OPENAI_COMPAT_BASE_URL"] = self.api_url

    LOCAL_OLLAMA = "local_ollama"
    OPENAI_COMPAT = "openai_compatible"
    def load_engine_config(*a, **k):
        return None  # type: ignore
    def save_engine_config(*a, **k):
        return False  # type: ignore
DEFAULT_PORT = 8765
LOCAL_OLLAMA_HOST = "127.0.0.1:11434"
LOCAL_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # core/ -> Repo-Root

def _run(
    cmd: list[str],
    *,
    check: bool = False,
    env: dict[str, str] | None = None,
    capture_output: bool = False,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd or PROJECT_ROOT,
        text=True,
        env=env,
        check=check,
        capture_output=capture_output,
    )


def _json_get(url: str, timeout: float = 3.0, headers: dict | None = None) -> dict | None:
    try:
        request = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def _json_post(url: str, payload: dict, timeout: float = 20.0) -> dict | None:
    try:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def _venv_python() -> str:
    candidate = PROJECT_ROOT / ".venv" / "bin" / "python"
    return str(candidate) if candidate.exists() else sys.executable


def _print_check(ok: bool, label: str, detail: str = "") -> None:
    status = "OK" if ok else "MISSING"
    suffix = f" - {detail}" if detail else ""
    print(f"{status:7} {label}{suffix}")


def _emit_error(args: argparse.Namespace, code: int, message: str, fix: str = "", error: object | None = None) -> None:
    """Actionable Errors (DX): a clear cause+fix, never a raw stack trace. With
    --json, a stable machine-readable format, without secrets.

    ``error``: the exception a caller caught. When given, the stable code and the
    exit code come from the one classifier (core/provider_errors) instead of the
    numeric-only rule, so a CLI failure is reported as the same upstream_error /
    auth_error the serve and chat surfaces report."""
    # Phase 4 Item 15: stable machine-readable error codes (code_id) alongside the
    # numeric exit code. Mapping: 2 -> usage_error, otherwise runtime_error.
    try:
        from core.observability import ErrorCode  # lazy: the except below covers a run without observability

        if error is not None:
            from core import provider_errors

            code_id = provider_errors.error_code_for(error).value
            code = provider_errors.exit_code_for(error)
        else:
            code_id = ErrorCode.USAGE.value if code == 2 else ErrorCode.RUNTIME.value
    except Exception:
        code_id = "usage_error" if code == 2 else "runtime_error"
    if getattr(args, "json", False):
        print(json.dumps({"error": {"code": code, "code_id": code_id, "message": message, "fix": fix}}, indent=2))
    else:
        print(f"Error: {message}", file=sys.stderr)
        if fix:
            print(f"  Fix: {fix}", file=sys.stderr)


def _abort_url() -> str:
    raise SystemExit("Aborted: engine base URL is required for this selection.")


def _ask_url(input_fn, prompt: str, required: bool = False, prefill: str = "") -> str | None:
    """Reads an engine base URL; None on abort/empty when not required.

    ``prefill`` (e.g. from the env) is the suggestion: Enter accepts it.
    """
    while True:
        try:
            url = input_fn(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            return None if not required else _abort_url()
        if url:
            return url
        if prefill:
            return prefill
        if required:
            print("  ⚠ A URL is required for this engine – please enter it again.")
            continue
        return None


def _fetch_served_models(api_url: str, timeout: float = 5.0) -> list[str] | None:
    """
    Live query of the model IDs served by an OpenAI-compatible engine.

    Deployment-drift defence (Mandate 2026-08-21): the onboarding default is
    derived from the chosen engine's LIVE /v1/models instead of hardcoded —
    the same source as the PWA SetupPage and the TUI connection check. Returns
    None on a reachability error (the default fallback then stays in effect).
    """
    base = (api_url or "").strip().rstrip("/")
    if not base:
        return None
    from core.engine_config import engine_api_key_for

    headers = {}
    if key := engine_api_key_for(api_url):
        headers["Authorization"] = f"Bearer {key}"
    try:
        request = urllib.request.Request(f"{base}/models", headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    ids = [m.get("id") for m in payload.get("data", []) if isinstance(m, dict) and m.get("id")]
    return [str(i) for i in ids] or None


def _probe_remote_engine(api_url: str, model: str) -> tuple[bool, str]:
    """Non-blocking health probe for an OpenAI-compatible remote engine.

    Returns (reachable, detail). Does NOT pull or install anything — a remote
    vLLM/DGX engine just needs to answer ``GET {api_url}/models``.

    The probe sends the same bearer token the chat path uses (env, keychain, else
    ``~/.ephe/engine.key``). A hosted endpoint answers an unauthenticated request with
    401, which reads as "not reachable" and reports a working setup as broken (measured
    against this repository's own engine.json endpoint, 2026-10-13);
    `ephe_cli._probe_active_remote_engine` already worked this way.
    """
    base = (api_url or "").strip().rstrip("/")
    if not base:
        return False, "no engine URL"
    from core.engine_config import engine_api_key_for

    headers: dict[str, str] = {}
    if key := engine_api_key_for(api_url):
        headers["Authorization"] = f"Bearer {key}"
    payload = _json_get(f"{base}/models", timeout=4.0, headers=headers)
    if payload is None:
        return False, f"engine not reachable: {base}"
    ids = [m.get("id") for m in payload.get("data", []) if isinstance(m, dict)]
    if model and any(model in (i or "") for i in ids):
        return True, f"engine up, model '{model}' served"
    if ids:
        return True, f"engine up (served models: {', '.join(map(str, ids))})"
    return False, f"engine answered but lists no models: {base}"


def _parse_tool_args(pairs: list[str]) -> dict:
    """Parse --arg k=v pairs into a dict. Values stay strings (the tool types
    them via its JSON schema; deliberately simple here for CLI usage)."""
    out: dict[str, Any] = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise ValueError(f"Invalid --arg format: '{pair}' (erwartet: key=value)")
        key, value = pair.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Leerer --arg-Key: '{pair}'")
        # try JSON interpretation (lists/numbers/bools), else keep the string
        try:
            out[key] = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            out[key] = value
    return out


def task_from_stdin() -> str:
    """The task text a pipe carries; empty when stdin is a terminal.

    pytest replaces stdin while it captures output and raises on a read there, so
    the read is guarded; a verb that got its task as an argument never reaches it.
    """
    stream = sys.stdin
    if stream is None or stream.isatty():
        return ""
    try:
        return stream.read().strip()
    except (OSError, ValueError):
        return ""


def resolve_task(tokens: list[str] | None) -> str:
    """A task-taking verb's task: its own words, or what the pipe carries.

    `ephe run -` names stdin explicitly, `cat spec.md | ephe run` passes no task at
    all: in both shapes the words are empty or the single `-`.
    """
    words = " ".join(tokens or []).strip()
    if words and words != "-":
        return words
    return task_from_stdin()


#: How much of a diff digest a reader compares — the algorithm and this many hex characters.
SHA_PREFIX_CHARS = 12


def short_sha(diff_sha: str) -> str:
    """A diff digest as a reader compares it: the algorithm and the first 12 hex characters.

    One definition for both CLI seams (``core/_cli_isolation.py`` re-exports it,
    ``core/_cli_run.py`` imports it): a digest shortened two ways would let the same change
    set read differently per verb.
    """
    text = str(diff_sha or "")
    if not text:
        return "no digest"
    algorithm, _, digest = text.partition(":")
    if not digest:
        return text[:SHA_PREFIX_CHARS]
    return f"{algorithm}:{digest[:SHA_PREFIX_CHARS]}"
