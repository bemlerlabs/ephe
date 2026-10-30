"""
◑ Ephe – Slash Commands

Extensible command registry. Add your own commands in 30 seconds:

    COMMANDS["/mycmd"] = "Do something awesome with: {input}"

Commands are resolved before sending to Ollama.
The {input} placeholder is replaced with the user's text after the command.

Example:
    User types:  /post AI productivity
    Resolves to: "Write a professional LinkedIn post about... AI productivity"

Ephe – Bad Liebenzell, Schwarzwald
"""

from __future__ import annotations

import shlex
from typing import NamedTuple

from core.goal_loop import DEFAULT_CHECK_COMMAND, DEFAULT_MAX_TURNS

# Registry
# Format: "/command": "Prompt template with optional {input} placeholder"

COMMANDS: dict[str, str] = {
    "/post": (
        "Write a professional, authentic LinkedIn post about the following topic. "
        "Keep it concise (max 150 words), engaging, and avoid corporate buzzwords. "
        "Topic: {input}"
    ),
    "/debug": (
        "You are a senior software engineer with 15 years of experience. "
        "Carefully analyze the following code for bugs, edge cases, performance issues, "
        "and improvements. Be specific and explain your reasoning. "
        "Code:\n{input}"
    ),
    "/idea": (
        "Generate exactly 5 creative, actionable startup ideas related to: {input}\n\n"
        "For each idea use this format:\n"
        "**Name** | Problem | Solution | Why now\n\n"
        "Be concrete, not generic."
    ),
    "/explain": (
        "Explain the following concept clearly and simply, "
        "as if explaining to a smart developer who has never encountered it before. "
        "Use analogies if helpful. Concept: {input}"
    ),
    "/commit": (
        "Write a conventional Git commit message for the following changes. "
        "Use the format: <type>(<scope>): <short description>\n\n"
        "Then add a brief body if needed. Changes:\n{input}"
    ),
    # /swarm is handled specially by the App (triggers multi-agent pipeline)
    # The template here is only used as a fallback usage hint.
    "/swarm": "__swarm__:{input}",
    # /learn triggers the Skill-Builder (the AI creates new skills for itself)
    "/learn": "__learn__:{input}",
    # /goal runs the autonomous goal loop (core/goal_loop.py) that `ephe goal` drives
    "/goal": "__goal__:{input}",
    # Phase 2 Item 8 — prompt commands (like /post: {input} = user text):
    "/plan": (
        "Create a detailed, stepwise implementation plan for:\n{{input}}\n\nPer step, format: goal, concrete approach, changed files, risk. End with a verification strategy (tests/checks). No code spam — plan first."
    ),
    "/review": (
        "You are a critical senior reviewer. Analyse the following code for bugs, security gaps, performance and style issues. Be concrete (lines/behaviour), prioritise by severity. If no code is attached: ask for code.\n{{input}}"
    ),
    # Phase 2 Item 8 — info commands (rendered locally, NO LLM).
    # The templates are only fallback documentation; the TUI renders them
    # via render_info_command() (info commands are intercepted there,
    # before resolve_command would resolve them here).
    # App commands: the terminal runs them itself (no prompt, no engine call).
    # The templates are documentation only; ui/app.py branches on the verb
    # before resolve_command is reached.
    "/new": "Start a new session (terminal)",
    "/sessions": "Open, rename or delete a session (terminal)",
    "/undo": "Remove the last turn from the transcript (terminal)",
    "/redo": "Restore the last undone turn (terminal)",
    "/editor": "Edit the draft in $VISUAL/$EDITOR (terminal)",
    "/help": "Ephe command overview (see /help in the TUI)",
    "/model": "Show active model/provider (see /model in the TUI)",
    "/engine": "Show engine config (see /engine in the TUI)",
    "/setup": "Engine setup: provider, endpoint, API key, model (terminal)",
    "/configure": "Same as /setup (terminal)",
}

APP_COMMANDS: frozenset[str] = frozenset(
    {"/new", "/sessions", "/undo", "/redo", "/editor"}
)

# Info commands (Phase 2 Item 8)
# These commands are rendered LOCALLY (no LLM pass): they show state.
# In the TUI, is_info_command() is evaluated before resolve_command();
# the registry entries above are fallback + documentation.
INFO_COMMANDS: frozenset[str] = frozenset({"/help", "/model", "/engine", "/configure"})


def is_info_command(text: str) -> bool:
    """True if text is an info command (/help, /model, /engine, /configure),
    regardless of any additional arguments."""
    parts = text.strip().split(maxsplit=1)
    return bool(parts) and parts[0].lower() in INFO_COMMANDS


def render_info_command(text: str) -> str:
    """Render an info command locally (no LLM).

    Returns:
        The rendered text, or "" when text is not an info command.

    Lazy imports: model_provider / engine_config load only when needed, so
    core.commands stays importable without the full provider ecosystem
    (e.g. in lightweight test runs).
    """
    cmd = text.strip().split(maxsplit=1)[0].lower()
    if cmd not in INFO_COMMANDS:
        return ""

    if cmd == "/help":
        lines = ["Ephe — Commands"]
        lines.append("─" * 40)
        for name, desc in get_command_help():
            tag = " [Info]" if name in INFO_COMMANDS else ""
            lines.append(f"  {name:<12} {desc}{tag}")
        lines.append("")
        lines.append("Info commands render locally (no LLM): /help /model /engine /configure")
        lines.append("Terminal commands: /new /sessions /undo /redo /editor")
        return "\n".join(lines)

    if cmd == "/model":
        try:
            from core.model_provider import get_active_provider

            cfg = get_active_provider()
            return (
                f"Active model/provider:\n  Provider : {cfg.provider}\n  Label    : {cfg.label}\n  Model    : {cfg.model}\n  Base URL : {cfg.base_url}"
            )
        except Exception as exc:  # noqa: BLE001
            return f"model info not available: {exc}"

    if cmd == "/engine":
        try:
            from core.engine_config import default_config_path, load_engine_config

            choice = load_engine_config()
            if choice is None:
                return (
                    "No engine selection persisted (~/.ephe/engine.json).\nChoose an engine: `ephe tui --configure`\n(alternative: `ephe serve` for the OpenAI-compatible engine)"
                )
            lines = [
                f"Engine config ({default_config_path()}):",
                f"  Provider : {choice.provider}",
                f"  Model    : {choice.model}",
            ]
            if choice.api_url:
                lines.append(f"  API URL  : {choice.api_url}")
            lines.append("Switch: `ephe tui --configure`")
            return "\n".join(lines)
        except Exception as exc:  # noqa: BLE001
            return f"engine info not available: {exc}"

    if cmd == "/configure":
        try:
            from core.engine_config import load_engine_config

            choice = load_engine_config()
            if choice is not None:
                state = f"Current: {choice.provider} / {choice.model}"
            else:
                state = "No engine chosen yet."
            return (
                f"{state}\nChoose a new engine (interactive, persisted to ~/.ephe/engine.json): `ephe tui --configure`"
            )
        except Exception as exc:  # noqa: BLE001
            return f"configure info not available: {exc}"

    # Unreachable (cmd was checked against INFO_COMMANDS above) — defensive.
    return ""

# Lookup

_COMMAND_DESCRIPTIONS: dict[str, str] = {
    "/post":    "Write a LinkedIn post",
    "/debug":   "Debug code as a senior engineer",
    "/idea":    "Generate 5 startup ideas",
    "/explain": "Explain a concept simply",
    "/commit":  "Write a Git commit message",
    "/swarm":   "Multi-agent parallel pipeline",
    "/learn":   "Learn a pattern and create a new skill",
    "/goal":    "Autonomous goal loop with a check command",
    "/plan":    "Stepwise implementation plan (prompt)",
    "/review":  "Critical code review (prompt)",
    "/new":     "Start a new session (terminal)",
    "/sessions": "Open, rename or delete a session (terminal)",
    "/undo":    "Remove the last turn from the transcript (terminal)",
    "/redo":    "Restore the last undone turn (terminal)",
    "/editor":  "Edit the draft in $VISUAL/$EDITOR (terminal)",
    "/help":    "Command overview (local, no LLM)",
    "/model":   "Active model/provider (local, no LLM)",
    "/engine":  "Engine config (local, no LLM)",
    "/setup":   "Engine setup: provider, endpoint, key, model (terminal)",
    "/configure": "Same as /setup (terminal)",
}

# Commands that trigger special app-level behaviour (not resolved to a prompt)
SWARM_COMMANDS: frozenset[str] = frozenset({"/swarm"})
LEARN_COMMANDS: frozenset[str] = frozenset({"/learn"})
GOAL_COMMANDS: frozenset[str] = frozenset({"/goal"})
PROJECT_COMMANDS: frozenset[str] = frozenset({"/project"})


class GoalCommandSpec(NamedTuple):
    """The three values a `/goal` command names — the loop's own three values."""

    task: str
    check: str
    max_turns: int


def resolve_command(raw_input: str) -> str:
    """
    Resolve a slash command to its full prompt.

    Examples:
        resolve_command("/post AI trends")
        → "Write a professional LinkedIn post about... AI trends"

        resolve_command("/post")
        → "[/post] Usage: /post <topic>  —  Write a LinkedIn post"

        resolve_command("/unknown foo")
        → "/unknown foo"   (passthrough, no match)

        resolve_command("hello")
        → "hello"          (passthrough, no slash)

    Returns:
        The resolved prompt string, or the original input if no match.
    """
    raw_input = raw_input.strip()

    if not raw_input.startswith("/"):
        return raw_input

    parts = raw_input.split(maxsplit=1)
    command = parts[0].lower()
    argument = parts[1].strip() if len(parts) > 1 else ""

    if command not in COMMANDS:
        return raw_input  # unknown command → passthrough

    template = COMMANDS[command]

    if "{input}" in template:
        if not argument:
            desc = _COMMAND_DESCRIPTIONS.get(command, "")
            return (
                f"[{command}] Usage: {command} <text>  "
                f"{'— ' + desc if desc else ''}"
            )
        return template.replace("{input}", argument)

    # Template has no {input} placeholder → append argument if present
    return template + (" " + argument if argument else "")


def get_completions(prefix: str) -> list[str]:
    """
    Return all commands that start with the given prefix.
    Used for Tab-completion in HistoryInput.

    Example:
        get_completions("/po") → ["/post"]
        get_completions("/")   → ["/post", "/debug", "/idea", "/explain", "/commit"]
    """
    return [cmd for cmd in COMMANDS if cmd.startswith(prefix)]


def get_command_help() -> list[tuple[str, str]]:
    """Return list of (command, description) for the help overlay."""
    return [
        (cmd, _COMMAND_DESCRIPTIONS.get(cmd, ""))
        for cmd in COMMANDS
    ]


def is_command(text: str) -> bool:
    """Return True if text starts with a known slash command."""
    parts = text.strip().split(maxsplit=1)
    return bool(parts) and parts[0].lower() in COMMANDS


def is_swarm_command(text: str) -> bool:
    """Return True if text is a /swarm command (handled by swarm pipeline)."""
    parts = text.strip().split(maxsplit=1)
    return bool(parts) and parts[0].lower() in SWARM_COMMANDS


def extract_swarm_task(text: str) -> str:
    """
    Everything after "/swarm", trimmed down to the task text.
    "/swarm Plan a REST API" → "Plan a REST API"
    "/swarm" → ""  (caller should show usage hint)
    """
    parts = text.strip().split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def is_learn_command(text: str) -> bool:
    """Return True if text is a /learn command (handled by skill-builder)."""
    parts = text.strip().split(maxsplit=1)
    return bool(parts) and parts[0].lower() in LEARN_COMMANDS


def extract_learn_topic(text: str) -> str:
    """
    Everything after "/learn", trimmed down to the topic text.
    "/learn FastAPI route style" → "FastAPI route style"
    "/learn" → ""  (caller should show usage hint)
    """
    parts = text.strip().split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def is_goal_command(text: str) -> bool:
    """Return True if text is a /goal command (handled by the goal loop)."""
    parts = text.strip().split(maxsplit=1)
    return bool(parts) and parts[0].lower() in GOAL_COMMANDS


def is_project_command(text: str) -> bool:
    """Return True if text is a /project command (handled by the phase runner)."""
    parts = text.strip().split(maxsplit=1)
    return bool(parts) and parts[0].lower() in PROJECT_COMMANDS


def parse_project_command(text: str) -> str:
    """The plan path after `/project`; empty when the message names none."""
    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return ""
    body = parts[1].strip()
    if body.startswith("`") and body.endswith("`") and len(body) > 1:
        body = body[1:-1].strip()
    return body


def parse_goal_command(text: str) -> GoalCommandSpec:
    """
    What "/goal <target> [--check \"<cmd>\"] [--max-turns N]" declares.

    "/goal Fix the login bug"                → the defaults of core.goal_loop
    "/goal Fix the login bug --max-turns 2"  → ("Fix the login bug", "pytest -q", 2)
    "/goal --check \"npm test\" ship it"      → ("ship it", "npm test", 10)
    "/goal"                                  → ("", …)  (caller shows the usage hint)

    The flags are the two `ephe goal` takes, so the CLI and this command name the
    same three values. A flag without a usable value keeps the default and the
    emitted state carries what was used, so the surface never shows a number the
    loop is not obeying.
    """
    parts = text.strip().split(maxsplit=1)
    body = parts[1].strip() if len(parts) > 1 else ""
    check = DEFAULT_CHECK_COMMAND
    max_turns = DEFAULT_MAX_TURNS
    try:
        tokens = shlex.split(body)
    except ValueError:  # an unclosed quote: the target is whatever is readable
        return GoalCommandSpec(task=body, check=check, max_turns=max_turns)
    kept: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        value = tokens[index + 1] if index + 1 < len(tokens) else ""
        if token == "--check":
            check = value or check
            index += 2
            continue
        if token == "--max-turns":
            try:
                max_turns = max(1, int(value))
            except ValueError:
                pass
            index += 2
            continue
        kept.append(token)
        index += 1
    return GoalCommandSpec(task=" ".join(kept).strip(), check=check, max_turns=max_turns)
