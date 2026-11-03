"""core/persistence.py — what a device keeps, declared in one place.

The product says Ephe forgets, and it says the device folder holds the few things that
stay. Both sentences are about a list nobody could read: measured 2026-11-03 on the
machine that ships Ephe, fifty entries sat in `~/.ephe` and the only way to ask what
belongs there was to grep the code for the root expression. The cell runtime answers that
question differently — `core/cell_policy.policy_snapshot()` reports the caps
`core/cpython_cell.py` enforces, so a settings card, `ephe doctor` and the status page all
read one number that has to be the enforced one. This module is the same instrument for the
disk.

Three rules hold it honest:

* Every row names the code that writes it. A row with no writer is a claim, so the module
  keeps `writer` as a required field and the F1 contract refuses a row whose owner cannot
  be found in the tree.
* Retention stays in `core/store_retention.py`, which decides how long a store lives.
  `tests/test_ephemeral_session_proof.py` requires every store named there to appear here,
  so the two lists cannot drift into different pictures of the same folder.
* A project's own `.ephe` folder is not device state. `core/semindex/store.py` indexes into
  `<workspace>/.ephe/index.db`, and `core/chat_prompt.py` reads `.ephe/rules` and
  `.ephe/learning` beside the opened project: those travel with the folder a person chose
  and are deliberately absent below.

`forgettable` states what a device reset may remove. The reset itself is the next step of
this wave and does not exist yet, so the column is a promise the verb has to keep, and the
three rows marked false are the ones whose loss would break the box rather than empty it:
the audit log is append-only by its own contract, the cell guest costs a full interpreter
rebuild, and the trusted keys are what every installed plugin is verified against.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from core.engine_config import config_root


@dataclass(frozen=True)
class Persisted:
    """One entry the product creates, or reads, directly under the device folder.

    `kind` is `dir`, `file` or `socket`; `holds` says in plain words what a person loses
    when the entry goes; `writer` is the file in this tree that resolves it; `forgettable`
    is the promise the device reset has to keep.
    """

    name: str
    kind: str
    holds: str
    writer: str
    forgettable: bool


EPHE_PERSISTENCE: tuple[Persisted, ...] = (
    # Folders the product creates under the device root.
    Persisted("agents", "dir", "the agent profiles: who each role is and what it was told",
              "core/agent_profiles.py", True),
    Persisted("amber", "dir", "the monthly ephemeris crystals `ephe amber` wrote",
              "ephe_cli.py", True),
    Persisted("artifacts", "dir", "the files a turn produced, one folder per task",
              "core/artifact_store.py", True),
    Persisted("bench", "dir", "the bench harness's own scratch",
              "core/store_retention.py", True),
    Persisted("benchmarks", "dir", "the golden-matrix runs `ephe bench --run` left",
              "ephe_cli.py", True),
    Persisted("build", "dir", "the build scratch of the cell's interpreter; a recipe rebuilds it",
              "core/store_retention.py", True),
    Persisted("cells", "dir", "the installed cell guest and one work folder per session",
              "core/cpython_guest.py", False),
    Persisted("changesets", "dir", "one JSON per change set: what changed, where, and why",
              "core/change_set.py", True),
    Persisted("learning", "dir", "the learning map: episodes, heuristics and reflections",
              "core/learning_loop.py", True),
    Persisted("logs", "dir", "the log the detached backend writes when the CLI starts it",
              "ephe_cli.py", True),
    Persisted("marketplace-cache", "dir", "the mirror of the capability catalogue the shelf reads offline",
              "core/marketplace_sources.py", True),
    Persisted("mcp", "dir", "one sandboxed HOME per MCP server",
              "core/mcp_sandbox.py", True),
    Persisted("memory", "dir", "what the agent remembers, one folder per scope",
              "core/memory_provider.py", True),
    Persisted("models", "dir", "the downloaded weights, the embedding model among them",
              "core/memory_embed_gemma.py", True),
    Persisted("plugins", "dir", "the plugin packs that were installed",
              "core/plugin_lifecycle.py", True),
    Persisted("run", "dir", "the run ledger: what each turn did, tool by tool",
              "core/run/ledger.py", True),
    Persisted("secrets", "dir", "the vault entries a person stored for the shelf",
              "core/secret_store.py", True),
    Persisted("sessions", "dir", "the task history and every transcript in it",
              "core/session.py", True),
    Persisted("skills", "dir", "the skills installed for this device",
              "core/skills.py", True),
    Persisted("trusted-keys", "dir", "the public keys a plugin signature is checked against",
              "core/plugin_signing.py", False),
    Persisted("voices", "dir", "the installed voices the local reader speaks with",
              "core/voice_config.py", True),
    Persisted("workspace", "dir", "the neutral folder a run without a project works in",
              "core/engine_config.py", True),
    Persisted("workspaces", "dir", "the register of projects this device opened",
              "core/workspace_lifecycle.py", True),
    # One file per answer, each reachable from its own surface.
    Persisted("a2a_ledger.json", "file", "the agent-to-agent messages this device sent",
              "core/a2a.py", True),
    Persisted("artifacts.db", "file", "the index of the files a turn produced",
              "core/artifact_store.py", True),
    Persisted("audit.log", "file", "every tool call, approval and refusal, append-only",
              "core/audit_log.py", False),
    Persisted("desktop.json", "file", "the line the app icon needs: interpreter, project, port",
              "ephe_cli.py", True),
    Persisted("endpoints.json", "file", "the custom endpoints saved in Settings",
              "server/routes/settings.py", True),
    Persisted("engine.json", "file", "which engine and model a run picks",
              "core/engine_config.py", True),
    Persisted("engine.key", "file", "the token for a hosted engine, one line, owner-only",
              "core/engine_config.py", True),
    Persisted("engine.key.binding.json", "file", "which engine a stored token belongs to",
              "core/engine_config.py", True),
    Persisted("ephemeris.jsonl", "file", "the orbit log: what this device did, day by day",
              "core/ephemeris.py", True),
    Persisted("hooks.json", "file", "the user's own pre- and post-tool hooks",
              "core/user_hooks.py", True),
    Persisted("image.json", "file", "the image model chosen",
              "core/image_config.py", True),
    Persisted("marketplaces.json", "file", "which sources the shelf reads",
              "core/marketplace_sources.py", True),
    Persisted("mcp.json", "file", "the MCP servers configured",
              "core/mcp_config.py", True),
    Persisted("persona.md", "file", "the persona the agent answers as",
              "core/persona.py", True),
    Persisted("plugin-cancel.json", "file", "a teardown that was asked to stop",
              "core/plugin_activity.py", True),
    Persisted("plugin-lock.json", "file", "which plugin versions are installed",
              "core/plugin_lockfile.py", True),
    Persisted("plugin-state.json", "file", "which plugins are enabled",
              "core/plugin_lifecycle_types.py", True),
    Persisted("plugin-state.json.lock", "file", "the sibling the state writer locks while it writes",
              "core/plugin_lifecycle_store.py", True),
    Persisted("plugins.json", "file", "the installed plugin registry",
              "core/plugin_store.py", True),
    Persisted("reviews.jsonl", "file", "the review gate's ledger",
              "core/review_gate.py", True),
    Persisted("schedule_results.json", "file", "what each scheduled run answered",
              "core/scheduler.py", True),
    Persisted("scheduled_jobs.json", "file", "the jobs a person put on the clock",
              "core/scheduler.py", True),
    Persisted("search.db", "file", "the full-text index over the transcripts",
              "core/session_search.py", True),
    Persisted("security.json", "file", "the approval rules and the profile's ceiling",
              "core/security_config.py", True),
    Persisted("settings.json", "file", "every setting saved in the app",
              "core/settings_schema.py", True),
    Persisted("setup.json", "file", "the answers the first run collected",
              "server/routes/settings.py", True),
    Persisted("skills_state.json", "file", "which skills are switched off",
              "core/skills.py", True),
    Persisted("subagent_history.json", "file", "the last snapshot of the sub-agent runs",
              "core/subagent_history.py", True),
    Persisted("tasks.json", "file", "the task register",
              "core/tasks.py", True),
    Persisted("tour.json", "file", "how far the first-run tour got",
              "server/routes/tour.py", True),
    Persisted("trajectory.json", "file", "the turn-by-turn trace the learning loop reads",
              "core/trajectory.py", True),
    Persisted("usage.jsonl", "file", "the token ledger, one line per day",
              "core/usage_ledger.py", True),
    Persisted("voice.json", "file", "the voice chosen",
              "core/voice_config.py", True),
    # The one entry the Python product never writes: the desktop shell binds it.
    Persisted("ephe-desktop.sock", "socket",
              "the door a second window knocks on to reach the running one",
              "app/src-tauri/src/instance.rs", True),
)


def root() -> Path:
    """The device folder this declaration is read against."""
    return config_root()


def declared_names() -> frozenset[str]:
    return {entry.name for entry in EPHE_PERSISTENCE}


def present(base: Path | None = None) -> list[str]:
    """Declared entries that are actually on disk, in declaration order."""
    folder = base or root()
    return [entry.name for entry in EPHE_PERSISTENCE if (folder / entry.name).exists()]


def on_disk(base: Path | None = None) -> list[str]:
    """Every top-level entry in the folder, dot-files aside, sorted."""
    folder = base or root()
    try:
        return sorted(entry.name for entry in folder.iterdir() if not entry.name.startswith("."))
    except OSError:
        return []


def unnamed(base: Path | None = None) -> list[str]:
    """What the folder holds that the declaration does not name.

    The answer is the product's own honesty test: an entry here was written by code nobody
    declared, or left behind by a build, a backup or a hand. Both are worth seeing.
    """
    declared = declared_names()
    return [name for name in on_disk(base) if name not in declared]


def summary(base: Path | None = None) -> dict[str, object]:
    """The numbers a surface renders: declared, present, unnamed, and the names."""
    folder = base or root()
    return {
        "root": str(folder),
        "declared": len(EPHE_PERSISTENCE),
        "present": len(present(folder)),
        "unnamed": unnamed(folder),
        "forgettable": sum(1 for entry in EPHE_PERSISTENCE if entry.forgettable),
    }


def _size(path: Path) -> int:
    """Bytes for one entry: a file reports its own length, a folder reports its tree."""
    if path.is_file():
        return path.stat().st_size
    from core.cell_output import dir_bytes

    return dir_bytes(path)


def listing(base: Path | None = None) -> list[dict[str, object]]:
    """One row per declared entry: whether this folder holds it, how big it is, what it holds.

    Bytes come from the same helper the retention report reads, so the figure a person sees
    for `sessions` is the figure `ephe prune` reasons about.
    """
    folder = base or root()
    rows: list[dict[str, object]] = []
    for entry in EPHE_PERSISTENCE:
        path = folder / entry.name
        here = path.exists()
        rows.append({
            "name": entry.name,
            "kind": entry.kind,
            "holds": entry.holds,
            "writer": entry.writer,
            "forgettable": entry.forgettable,
            "present": here,
            "bytes": _size(path) if here else 0,
        })
    return rows


def forget(base: Path | None = None, *, dry_run: bool = True) -> dict[str, list[str]]:
    """Clear the entries the declaration marks forgettable; keep the rest and say why.

    Three questions, and the answer to each is a list a surface can print: what went (or
    would have gone), what stayed because removing it costs the box its audit trail, its
    cell guest or its verification anchors, and what stayed because the declaration never
    said the product writes it. That last list is the honest one: a leftover is a person's
    file to judge, and a verb that deletes what it cannot name would be the product
    claiming more of the folder than the code can account for.
    """
    folder = base or root()
    removed: list[str] = []
    kept: list[str] = []
    for entry in EPHE_PERSISTENCE:
        path = folder / entry.name
        if not path.exists():
            continue
        if not entry.forgettable:
            kept.append(entry.name)
            continue
        removed.append(entry.name)
        if dry_run:
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        except OSError:
            kept.append(entry.name)
    return {
        "removed": removed,
        "kept": kept,
        "unnamed": unnamed(folder),
        "root": str(folder),
    }
