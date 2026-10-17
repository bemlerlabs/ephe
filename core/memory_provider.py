"""
◑ Ephe – Memory provider: choice, records, migration
core/memory_provider.py

One facade, one brain (docs/MEMORY_KEPTA_DESIGN.md). This module does *not*
decide which memory is the better one — it decides which memory a user gets, and
puts that decision in writing. That is the whole trick behind "always active,
without silently switching anything":

  1. The legacy vocabulary (persist_dir / collection_name) still names a store and
     is honoured as one: the path is where the Kepta file lands, the collection
     name is the scope. Every existing call site keeps its behaviour line for line.
  2. EPHE_MEMORY_PROVIDER = explicit choice, beats everything else.
  3. Decision record = the last choice that was actually *made*, persisted and readable.
  4. Recognition rule: a retired store on disk is recognised and named, never opened —
     the brain is Kepta, and the one-time import is offered (`legacy_import_command`).

There is no hidden default that moves data: rule 4 only decides which empty brain
gets addressed, and writes the outcome as a record.

The bridge (D4a, `kepta-bridge`) takes part in rules 2 and 3, never in rule 4: a
memory across the network is something you can only opt into, Ephe does not infer it.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable

from core.engine_config import config_subdir, workspace_hash

logger = logging.getLogger(__name__)

KEPTA = "kepta"
#: D4a: provider backed by a running Kepta instance. Selectable, never recognised —
#: the recognition rule must not hand out a memory across the network.
KEPTA_BRIDGE = "kepta-bridge"
VALID_PROVIDERS = (KEPTA, KEPTA_BRIDGE)
#: The two brains Ephe runs without an external instance (D4a keeps the bridge apart).
LOCAL_PROVIDERS = (KEPTA,)
#: Scope the retired vision collection is imported under.
RETIRED_VISION_SCOPE = "vision_rules"

ENV_PROVIDER = "EPHE_MEMORY_PROVIDER"

#: The one command that still reads a retired store. It needs the package this
#: product no longer carries, so it runs in a throwaway environment of its own.
IMPORT_COMMAND = "uv run --with chromadb==1.5.9 python scripts/import_legacy_store.py"  # gate:legacy


def kepta_db_path(scope: str, persist_dir: str | None = None) -> Path:
    """One file per brain (Kepta), per workspace scope (Ephe W16)."""
    if persist_dir:
        return Path(persist_dir) / f"kepta_{scope}.db"
    return config_subdir("memory") / "kepta" / scope / "kepta.db"


def provider_record_path() -> Path:
    return config_subdir("memory") / "provider.json"


def read_provider_record() -> dict[str, Any] | None:
    try:
        raw = json.loads(provider_record_path().read_text(encoding="utf-8"))
        if isinstance(raw, dict) and raw.get("provider") in VALID_PROVIDERS:
            return raw
    except (OSError, ValueError):
        pass
    return None


def write_provider_record(provider: str, *, reason: str) -> None:
    """Writes the decision down where it is visible — 0600, no secret, room to go back."""
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"Unknown memory provider: {provider!r}")
    path = provider_record_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "provider": provider,
        "reason": reason,
        "decided_at": time.time(),
        "schema": 1,
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def legacy_store_present() -> bool:
    """Rule 4: does a retired store sit in this workspace, waiting to be read?

    Recognised, not opened — the read needs a package this product no longer
    carries, and the import runs offline, on purpose, once.
    """
    from core.memory import workspace_memory_dir

    d = workspace_memory_dir()
    if not d.is_dir():
        return False
    try:
        return any(d.iterdir())
    except OSError:
        return False


def resolve_provider(
    *,
    persist_dir: str | None = None,
    collection_name: str | None = None,
    explicit: str | None = None,
    record: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """(provider, reason) — the decision, without guessing at it."""
    if persist_dir or collection_name:
        return KEPTA, "benannter Speicher: der Aufrufer gibt Pfad oder Scope vor"
    if explicit:
        if explicit not in VALID_PROVIDERS:
            raise ValueError(f"Unknown memory provider: {explicit!r}")
        return explicit, "explicit übergeben"
    env = (os.environ.get(ENV_PROVIDER) or "").strip().lower()
    if env in VALID_PROVIDERS:
        return env, f"env {ENV_PROVIDER}"
    if env:
        logger.warning("memory: ignoring unknown %s=%r", ENV_PROVIDER, env)
    rec = record if record is not None else read_provider_record()
    if rec:
        return str(rec["provider"]), f"record ({rec.get('reason', 'unknown')})"
    if legacy_store_present():
        write_provider_record(KEPTA, reason="existing-data")
        return KEPTA, "Altbestand gefunden — Kepta ist das Gehirn, ein Import steht bereit"
    write_provider_record(KEPTA, reason="fresh-install")
    return KEPTA, "frischer Workspace — Kepta-Core ist das neue Gehirn"


def _lazy_embedder() -> Callable[[list[str]], list[list[float]]] | None:
    """Materialises the ONNX model only when an embedding is first needed.

    A fresh Ephe with the Kepta brain should not import the embedding runtime
    while nobody touches a vector layer — the import is the expensive part, not
    the search.
    """
    from core.memory_embed import get_embedder, is_disabled

    if is_disabled():
        return None

    def _embed(texts: list[str]) -> list[list[float]]:
        fn = get_embedder()
        if fn is None:
            raise RuntimeError("embedding model unavailable")
        return fn(texts)

    return _embed


class LazyEmbedder:
    """Wrapper with identical callability, so that `is not None` reveals the layer."""

    def __call__(self, texts: list[str]) -> list[list[float]]:
        return _lazy_embedder()(texts)  # type: ignore[misc]


def open_provider(
    provider: str,
    *,
    persist_dir: str | None = None,
    collection_name: str | None = None,
    scope: str | None = None,
    embedder: Any = "auto",
) -> Any:
    """Builds the provider; `embedder='auto'` decides on the embedding module."""
    if provider == KEPTA:
        from core.memory_embed import effective_label, is_disabled
        from core.memory_kepta import KeptaProvider

        resolved_scope = scope or collection_name or workspace_hash()
        if callable(embedder):
            fn, model = embedder, "kepta-custom"
        elif embedder is None:
            fn, model = None, ""
        else:  # 'auto': settings decision, materialisation only when needed
            disabled = is_disabled()
            fn, model = (None, "") if disabled else (LazyEmbedder(), effective_label())
        return KeptaProvider(
            db_path=str(kepta_db_path(resolved_scope, persist_dir)),
            scope=resolved_scope,
            embedder=fn,
            embed_model=model,
        )
    if provider == KEPTA_BRIDGE:
        from core.memory_kepta_bridge import KeptaBridgeProvider, bridge_url_from_env

        # `persist_dir` may pass the URL through (tests/diagnostics); otherwise it comes
        # from the env only — there is no default endpoint.
        return KeptaBridgeProvider(
            persist_dir or collection_name or bridge_url_from_env(),
            scope=scope or collection_name or workspace_hash(),
        )
    raise ValueError(f"Unknown memory provider: {provider!r}")



# Migration (offline, non-destructive)


def legacy_import_command(scope: str | None = None, *, source: str | None = None) -> str:
    """The one command that reads a retired store, for surfaces that can only name it."""
    parts = [IMPORT_COMMAND]
    if source:
        parts += ["--source", str(source)]
    if scope:
        parts += ["--scope", str(scope)]
    return " ".join(parts)


def migrate_chroma_to_kepta(
    *,
    src_dir: str | None = None,
    src_collection: str | None = None,
    target_path: str | None = None,
    scope: str | None = None,
    dry_run: bool = False,
    embedder: Any = "auto",
    limit: int = 10000,
) -> dict[str, Any]:
    """Reports how a retired store is read now: offline, in an environment of its own.

    This used to copy the bucket in-process with the vendor's client. That client
    left the product — advisories on it that no release closed — so the read moved to `scripts/import_legacy_store.py`,
    which runs under `uv run --with …` and never installs the retired package
    beside the app.

    The source is not touched by either path, so the answer here is the command:
    `imported` stays 0 because this process cannot read the source at all, and a
    caller must not read that 0 as "the store was empty".
    """
    from core.memory import workspace_collection_name, workspace_memory_dir

    source = str(src_dir or workspace_memory_dir())
    resolved_scope = scope or workspace_hash()
    return {
        "dry_run": dry_run,
        "moved_in_process": False,
        "provider_target": KEPTA,
        "source_dir": source,
        "source_collection": src_collection or workspace_collection_name(),
        "imported": 0,
        "skipped": 0,
        "target_path": str(target_path or kepta_db_path(resolved_scope)),
        "scope": resolved_scope,
        "command": legacy_import_command(resolved_scope, source=source),
    }
