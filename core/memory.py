"""
◑ Ephe – Persistent Memory (Facade)
core/memory.py

Stores conversation highlights with semantic search.

Wave D separated memory from storage: this module is the API that
chat, auto-memory, tools and /api/memory have always used — the decision *where*
the facts live is made by `core/memory_provider.py`.

  * KeptaProvider   — SQLite/FTS5 + RRF + Oblivion retention + supersede
    (port from kepta/src/core, MIT), the brain of every installation.
  * KeptaBridgeProvider — the same brain, but inside a running Kepta instance
    through its HTTP API (D4a); only selectable explicitly, never auto-detected.

Storage paths:
  kepta:  ~/.ephe/memory/kepta/{workspace_hash}/kepta.db   (default)
  choice: ~/.ephe/memory/provider.json  (overridable via EPHE_MEMORY_PROVIDER)
  retired: ~/.ephe/memory/chroma_db/{workspace_hash}  — read once, offline
  any persist_dir for tests.
"""
from __future__ import annotations

import errno
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from core.engine_config import config_subdir

logger = logging.getLogger(__name__)

COLLECTION_NAME_DEFAULT = "ephe_memory"
DEFAULT_MEMORY_DIR = config_subdir("memory") / "chroma_db"

# I6-7: the injection policy is a control, not a comment
#
# Both values were literals in get_context_injection. The memory area now
# shows them as rows; they are read here, through the register's accessor
# wiring (core/settings_schema.py).


def inject_max_entries() -> int:
    """At most how many entries are lifted into the system prompt."""
    from core.settings_schema import deep_number

    return int(deep_number("memory.inject_max_entries"))


def inject_min_score() -> float:
    """Below this similarity the entry only costs tokens."""
    from core.settings_schema import deep_number

    return float(deep_number("memory.inject_min_score"))


#: "decide yourself" signals to the provider lookup.
_AUTO = "auto"


# W16: workspace scoping (no global single bucket any more)
# The collection name and the persist subfolder follow the SHA256 hash
# (16 characters) of the active workspace folder. Two projects in the same
# process therefore get separate buckets; switching the workspace in the
# WorkspacePicker switches the search without leaking data from the old project.

def workspace_memory_dir() -> Path:
    """Persist folder of the active workspace: {memory_root}/chroma_db/{hash}."""
    return config_subdir("memory") / "chroma_db" / workspace_hash_local()


def workspace_collection_name() -> str:
    """Collection name of the active workspace: ephe_memory_{hash}."""
    from core.engine_config import workspace_hash

    return f"{COLLECTION_NAME_DEFAULT}_{workspace_hash()}"


def workspace_hash_local() -> str:
    from core.engine_config import workspace_hash

    return workspace_hash()


# The memory write's own refusals, in the language the engine is instructed with and a
# surface localises by `code` — the `server.refusals.REASONS` convention. A write that
# meets a full disk is the one a bare install meets, because the memory volume sits under
# the user's home; so the failure names the move that reopens it instead of handing
# SQLite's own sentence to whoever reads the verdict.
MEMORY_NEXT_STEP = "Free space on the volume that holds {volume}, then retry the write."
MEMORY_WRITE_REFUSALS = {
    "memory_disk_full": "the memory store is full and nothing was written ({error})",
}


def is_full_disk(exc: BaseException) -> bool:
    """SQLite's SQLITE_FULL and the kernel's ENOSPC are the same wall.

    SQLite answers ``database or disk is full`` once ``write()`` returns ENOSPC, and a
    provider that writes without SQLite raises the bare ``OSError``. Anything else is a
    different failure and is left as it is.
    """
    text = str(exc).lower()
    if isinstance(exc, sqlite3.OperationalError) and "disk" in text and "full" in text:
        return True
    return getattr(exc, "errno", None) == errno.ENOSPC


class MemoryWriteRefused(sqlite3.OperationalError, OSError):
    """A memory write that did not happen, with the move that reopens it named.

    It keeps the provider's own fault class on both sides: a caller that caught
    ``sqlite3.OperationalError`` or ``OSError`` before keeps catching the failure, so the
    facade does not swallow it. What it adds is ``code`` for a surface to translate and the
    one line that names what to do. The message keeps the driver's own text, so a reader
    that pinned SQLITE_FULL still reads it.
    """

    def __init__(self, code: str, *, error: str, volume: str) -> None:
        if code not in MEMORY_WRITE_REFUSALS:
            raise KeyError(f"uncoded write refusal: {code}")
        self.code = code
        self.error = error
        self.volume = volume
        self.next_step = MEMORY_NEXT_STEP.format(volume=volume)
        super().__init__(
            f"{MEMORY_WRITE_REFUSALS[code].format(error=error)}. {self.next_step}"
        )


@dataclass(frozen=True)
class InjectionResult:
    """What one injection query lifted, together with the entries it lifted.

    G7: the context layer is the product, so a run has to be able to say *which*
    facts shaped it. A formatted block alone cannot: it drops the ids and scores
    at the door, and nothing downstream can point back at the entry a reader
    would want to correct. ``block`` is byte-for-byte what goes into the system
    prompt; ``entries`` is the same facts as rows (``{id, text, score, source}``)
    in the same order, so prompt and provenance can never describe two different
    runs.

    An empty ``block`` means nothing was injected — ``entries`` is empty then
    too, never a row the model never saw.
    """

    block: str
    entries: list[dict[str, Any]]


class Memory:
    """
    Persistent text storage with semantic search.

    Usage:
        mem = Memory()
        mem.store("Ich bin Python-Entwickler")
        results = mem.search("Programmiersprache Python")

    The public signature is the contract; providers change underneath it.
    """

    COLLECTION_NAME = COLLECTION_NAME_DEFAULT
    #: Old bucket name in existing chroma DBs (migration read path). # gate:legacy
    LEGACY_COLLECTION_NAME = "mimi_nox_memory"  # gate:legacy

    #: Process singleton per workspace scope: the retired client was expensive
    #: (~100+ MB idle), and a Kepta file is still better kept open. The
    #: key is the 16-character workspace hash.
    _SCOPED: dict[str, "Memory"] = {}
    #: Serializes __init__'s provider build (see __init__).
    _INIT_LOCK = threading.Lock()

    def __new__(
        cls,
        persist_dir: str | None = None,
        collection_name: str | None = None,
        provider: str | None = None,
        embedder: Any = None,
        scope: str | None = None,
    ) -> "Memory":
        if (
            persist_dir is None
            and collection_name is None
            and provider is None
            and embedder is None
            and scope is None
        ):
            from core.engine_config import workspace_hash

            key = workspace_hash()
            cached = cls._SCOPED.get(key)
            if cached is not None:
                return cached
            inst = super().__new__(cls)
            cls._SCOPED[key] = inst
            return inst
        return super().__new__(cls)

    @classmethod
    def reset_scoped_instances(cls) -> None:
        """W16: clear the singleton cache (workspace switch / test isolation)."""
        for mem in cls._SCOPED.values():
            try:
                mem.close()
            except Exception:  # a closed handle must not slow the switch down
                pass
        cls._SCOPED = {}

    @staticmethod
    def has_persisted_memory() -> bool:
        """True when memory data already exists. Keeps the idle path from building
        a store at all (RAM fix)."""
        root = config_subdir("memory")
        for candidate in (DEFAULT_MEMORY_DIR, root / "kepta"):
            try:
                if candidate.exists() and any(candidate.iterdir()):
                    return True
            except OSError:
                continue
        return False

    def __init__(
        self,
        persist_dir: str | None = None,
        collection_name: str | None = None,
        provider: str | None = None,
        embedder: Any = None,
        scope: str | None = None,
    ) -> None:
        if getattr(self, "_initialized", False):
            return
        # __new__ puts the scoped instance into _SCOPED before __init__ runs, so
        # two threads that call Memory() together both reach here for the same
        # object; without the lock both build a provider and one is leaked. The
        # second caller waits, re-checks _initialized and returns.
        with self._INIT_LOCK:
            if getattr(self, "_initialized", False):
                return
            self._initialize(persist_dir, collection_name, provider, embedder, scope)

    def _initialize(
        self,
        persist_dir: str | None,
        collection_name: str | None,
        provider: str | None,
        embedder: Any,
        scope: str | None,
    ) -> None:
        from core.memory_provider import KEPTA, open_provider, resolve_provider

        kind, reason = resolve_provider(
            persist_dir=persist_dir,
            collection_name=collection_name,
            explicit=provider,
        )
        self.provider_kind = kind
        self.provider_reason = reason
        # A named store wins over the workspace: whoever passes a collection gets
        # exactly that one, which is what the legacy vocabulary promised.
        self._scope = scope or collection_name or workspace_hash_local()
        self._provider = open_provider(
            kind,
            persist_dir=persist_dir,
            collection_name=collection_name,
            scope=self._scope if kind == KEPTA else None,
            embedder=_AUTO if embedder is None else embedder,
        )
        if kind == KEPTA and self._provider.count() == 0:
            self._offer_legacy_import()
        self._initialized = True

    def _offer_legacy_import(self) -> None:
        """Names a retired store in this workspace instead of opening it.

        Nothing here can read it any more: the read needs the package this
        product no longer carries, so it runs offline in an environment of its
        own and the user is told the command. Only applies without a persisted
        workspace, otherwise one project's facts land in the next.
        """
        try:
            from core.engine_config import load_engine_config
            from core.memory_provider import legacy_import_command

            choice = load_engine_config()
            if choice is not None and (choice.workspace_dir or None) is not None:
                return
            legacy_dir = config_subdir("memory") / "chroma_db"
            if not legacy_dir.is_dir():
                return
            try:
                if not any(legacy_dir.iterdir()):
                    return
            except OSError:
                return
            logger.info(
                "memory: a retired store sits in %s that this build does not read — %s",
                legacy_dir,
                legacy_import_command(self._scope, source=str(legacy_dir)),
            )
        except Exception as exc:
            logger.debug("legacy store detection skipped: %s", exc)

    # Public API

    def store(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
        *,
        supersedes: str | None = None,
        **provider_options: Any,
    ) -> str:
        """
        Stores a text entry.

        Args:
            text:     the text to store
            metadata: optional metadata (e.g. session-id, timestamp, source)
            supersedes: ID of the fact this wording corrects. A correction is
                its own write style, not a second fact: the old entry gets
                `superseded_by` and stays queryable.
            provider_options: Kepta extensions (memory_type/tags/entities/
                confidence) — the column model behind them.

        Returns:
            The ID of the leading entry, '' when empty.

        Raises:
            MemoryWriteRefused: when the volume is full. The fact did not land — no
                partial record — and the message names the space to free.
        """
        try:
            if supersedes:
                if not (text or "").strip():
                    return ""
                return str(self._provider.supersede(supersedes, text, metadata, **provider_options))
            return self._put(text, metadata, provider_options)
        except (sqlite3.OperationalError, OSError) as exc:
            if is_full_disk(exc):
                raise MemoryWriteRefused(
                    "memory_disk_full", error=str(exc), volume=self._memory_volume()
                ) from exc
            raise

    def _memory_volume(self) -> str:
        """The folder whose fullness closed the write — the path the next step names."""
        db = getattr(self._provider, "_db_path", None)
        return str(Path(db).parent) if db else str(config_subdir("memory"))

    def _put(self, text: str, metadata: dict | None, options: dict[str, Any]) -> str:
        return self._provider.store(text, metadata, **options)

    def search(self, query: str, top_k: int = 15) -> list[dict]:
        """
        Searches for similar stored texts.

        Returns:
            List of dicts: [{id, text, metadata, score}]
            Empty list when there are no entries.

        The document ID is part of the hit: without it found
        entries could not be addressed (delete/edit from the search).
        """
        return self._provider.search(query, top_k)

    def count(self) -> int:
        """Returns the number of stored entries."""
        return self._provider.count()

    def list_all(self, limit: int = 100) -> list[dict]:
        """
        Returns all memory entries (with IDs for delete operations),
        newest first.
        """
        return self._provider.list_all(limit)

    def list_deleted(self, limit: int = 100) -> list[dict]:
        """The trash bin: soft-deleted facts with `deleted_at`, so a removal is
        reversible rather than final."""
        return self._provider.list_deleted(limit)

    def restore(self, doc_id: str) -> None:
        """Brings a deleted entry back.

        Raises:
            KeyError: when the ID is not in the trash bin
        """
        self._provider.restore(doc_id)

    def get_injection(self, query: str, max_entries: int | None = None) -> InjectionResult:
        """
        The injection together with the result set behind it.

        Returns relevant memory entries as a formatted context block **and** the
        entries that block was built from. G7: the run that injected them records
        them, so a reader can open a past turn and see the facts that shaped it.

        The injection policy stays an intent of this layer: a provider changes
        the memory, not the prompt wording.

        Returns:
            An ``InjectionResult``; ``block`` is empty and ``entries`` is empty
            when nothing cleared the similarity floor.
        """
        limit = inject_max_entries() if max_entries is None else max_entries
        results = self.search(query, top_k=limit)
        if not results:
            return InjectionResult(block="", entries=[])

        # R30 curation: high-priority facts lead the block, then relevance.
        prio = {"high": 2, "medium": 1, "low": 0}
        results.sort(
            key=lambda r: (prio.get((r.get("metadata") or {}).get("priority"), 0), r["score"]),
            reverse=True,
        )

        floor = inject_min_score()
        used: list[dict[str, Any]] = []
        lines = ["\n--- Relevant context from your memory ---"]
        for r in results:
            if r["score"] < floor:  # too irrelevant to pay in tokens
                continue
            lines.append(f"• {r['text']}")
            # The same row the block line was written from — kept together so the
            # prompt and its provenance cannot drift apart.
            used.append(
                {
                    "id": str(r.get("id") or ""),
                    "text": str(r.get("text") or ""),
                    "score": round(float(r.get("score") or 0.0), 4),
                    "source": str((r.get("metadata") or {}).get("source") or ""),
                }
            )

        if len(lines) <= 1:
            # Nothing cleared the floor: nothing reached the model, so nothing is
            # recorded as having reached it.
            return InjectionResult(block="", entries=[])

        lines.append("--- End of memory context ---\n")
        return InjectionResult(block="\n".join(lines), entries=used)

    def get_context_injection(self, query: str, max_entries: int | None = None) -> str:
        """
        Returns relevant memory entries as a formatted context block.
        Optimised for injection into the system prompt (128K context).

        Kept as the string-returning door older callers use; the block itself is
        built by ``get_injection`` so the prompt and its provenance cannot drift.
        Resolved on the class, so a duck-typed caller (a test stub that only
        offers ``search``) keeps working exactly as before.
        """
        return Memory.get_injection(self, query, max_entries).block

    def delete(self, doc_id: str) -> None:
        """
        Deletes a single memory entry by ID.

        Raises:
            KeyError: when the ID does not exist
        """
        self._provider.delete(doc_id)

    def update(self, doc_id: str, text: str) -> None:
        """Replaces the text of an entry and re-embeds it.

        Metadata is kept (source drives the eviction in auto_memory,
        timestamp the sorting) and gets an updated_at. The ID does not change
        so references from the list/search stay valid.

        Raises:
            KeyError:  when the ID does not exist
            ValueError: when the new text consists only of whitespace
        """
        self._provider.update(doc_id, text)

    @property
    def collection_name(self) -> str:
        """Name of the collection actually used (workspace-scoped)."""
        return str(self._provider.name)

    def provider_stats(self) -> dict[str, Any]:
        """Which brain answers, and which retrieval layers are active."""
        stats = dict(self._provider.stats())
        stats.setdefault("provider", self.provider_kind)
        stats["reason"] = self.provider_reason
        return stats

    def migrate_to_kepta(self, dry_run: bool = False) -> dict[str, Any]:
        """Reports how a retired store is read now — offline, with its own command.

        The target path comes from the same resolution that also opens the provider
        (`kepta_db_path(scope)`); `scope` passes on the layer that already
        decided this here through W16."""
        from core.memory_provider import migrate_chroma_to_kepta

        return migrate_chroma_to_kepta(scope=self._scope, dry_run=dry_run)

    def close(self) -> None:
        try:
            self._provider.close()
        except Exception as exc:
            logger.debug("memory provider close failed: %s", exc)

    def clear(self) -> None:
        """Deletes all entries of the scope. Cannot be undone."""
        self._provider.clear()


# The timestamp helpers stay importable so older callers (and tests) do not
# have to be rewritten.
_now = time.time
