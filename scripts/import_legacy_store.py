#!/usr/bin/env python3
"""Read a store the removed vector provider left behind and write it into Kepta.

The retired package is out of the product: not in `pyproject.toml`, not in the lock, not in the
venv, and no scanner reads it. What that costs a user is the readable directory, and this
file is the answer — it opens the stores an older install left behind, copies every row
into the memory store Ephe ships today, and prints what it moved:

    uv run --with chromadb==1.5.9 python scripts/import_legacy_store.py  # gate:legacy

The package is imported inside `read_client` and nowhere else, so a venv without it still
opens this file. The source is never written and never deleted — its database files are
hashed before and after the run, so the owner deletes it once the receipt reads right.

An old install keeps memory in three places sharing one directory: `chroma_db/<hash>/`
holds `ephe_memory_<hash>` per workspace, `chroma_db` itself the single bucket from before
workspace scoping, and `chroma_db` again the vision rules, indexed in `l2` while every
memory collection is `cosine`. The `1.2` in `core/vision_memory.py:61` is an L2 radius;
`equivalent_gate` restates it with the metric attached or refuses to name a number.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Legacy vocabulary of an existing install: the removed provider chose these names, so
# they are the only way to find its data. After removal this file is the one place they
# still live.
LEGACY_COLLECTION = "mimi_nox_memory"  # gate:legacy
WORKSPACE_PREFIX = "ephe_memory"
VISION_COLLECTION = "vision_rules"

COSINE, L2, IP = "cosine", "l2", "ip"
# A collection created without `hnsw: space` metadata is indexed in this space: the
# library's own default (measured on 1.5.9).
SOURCE_DEFAULT_SPACE = L2
UNIT_NORM_TOLERANCE = 1e-3
GATE_KEY = "chroma_import"
PAGE_SIZE = 256
SAMPLE_SIZE = 8

# The one relevance boundary an old install held outside its collection metadata: the
# vision query compares an L2 distance against 1.2, so a cosine reader taking the number
# as written would accept nearly everything.
#: The retired package, pinned — the one literal here, and it is marked.
PACKAGE = "chromadb==1.5.9"  # gate:legacy

VISION_GATE = {"distance": 1.2, "space": L2,
               "origin": "core/vision_memory.py LEGACY_L2_RADIUS"}


def read_client():
    """The removed package, imported here and nowhere else in this tree."""
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
    try:
        import chromadb as legacy  # type: ignore[import-not-found]  # gate:legacy
    except ImportError as exc:  # a venv that no longer carries it is the normal case
        raise SystemExit(f"run: uv run --with {PACKAGE} python {sys.argv[0]}") from exc
    return legacy


def classify(name: str, override: str | None = None) -> tuple[str, str]:
    """(kind, scope) from the legacy naming alone: memory, vision, or something this file
    leaves alone. A scoped bucket names its own workspace after either prefix — the
    `<hash>` is the same key the provider opens that workspace under, so a bucket that
    kept the old prefix beside the new one lands in the scope its rows belong to. A bare
    bucket from before that scoping was global, so it keeps its own name.
    """
    if name == VISION_COLLECTION:
        return "vision", override or name
    for prefix in (WORKSPACE_PREFIX, LEGACY_COLLECTION):
        if name.startswith(prefix + "_") and len(name) > len(prefix) + 1:
            return "memory", override or name[len(prefix) + 1 :]
    if name in (WORKSPACE_PREFIX, LEGACY_COLLECTION):
        return "memory", override or name
    return "unknown", override or name


def index_metric(collection: Any) -> tuple[str, str]:
    """(space, vectorizer) of a collection, read from the store instead of assumed: the
    metadata where it is set, the resolved configuration where it is not (the vision
    collection carries none, which is why its space comes back as `l2`).
    """
    metadata = getattr(collection, "metadata", None) or {}
    space = str(metadata.get("hnsw:space") or "").strip().lower()
    if space not in (COSINE, L2, IP):
        space = ""
    config = getattr(collection, "configuration_json", None)
    hnsw = config.get("hnsw") if isinstance(config, dict) else None
    if not space and isinstance(hnsw, dict) and hnsw.get("space") in (COSINE, L2, IP):
        space = str(hnsw["space"])
    function = config.get("embedding_function") if isinstance(config, dict) else None
    name = function.get("name") if isinstance(function, dict) else ""
    return space or SOURCE_DEFAULT_SPACE, name if isinstance(name, str) else ""


def equivalent_gate(distance: float, space: str, *, unit_norm: bool) -> tuple[str, float] | None:
    """`distance` restated in the metric Kepta ranks with, or None when it cannot travel.

    Unit-norm vectors make the two metrics one number twice: an L2 distance is
    `sqrt(2 - 2*cos)`, so an L2 radius of 1.2 is a cosine floor of 0.28. Without unit-norm
    vectors that identity does not hold, and an inner-product index has no cosine floor.
    """
    if space == COSINE:
        return COSINE, float(distance)
    if space == L2 and unit_norm:
        return COSINE, round(1.0 - (float(distance) ** 2) / 2.0, 6)
    return None


def gate_for(name: str, space: str, *, unit_norm: bool) -> dict[str, Any] | None:
    """The boundary this collection's reader must use after the move, with its basis."""
    if name != VISION_COLLECTION:
        return None
    source: dict[str, Any] = dict(VISION_GATE)
    record: dict[str, Any] = {"collection": name, "source": source, "target": None}
    if space != source["space"]:
        record["reason"] = (f"the store indexes this collection in {space}, not "
                            f"{source['space']}: the boundary was never written for it")
        return record
    converted = equivalent_gate(source["distance"], space, unit_norm=unit_norm)
    if converted is None:
        record["reason"] = ("the sampled vectors are not unit-norm, so an L2 radius has no "
                            "cosine equivalent; a cosine reader must not take the number")
        return record
    metric, threshold = converted
    record["target"] = {"metric": metric, "threshold": threshold}
    record["basis"] = "unit-norm vectors: L2 distance = sqrt(2 - 2*cos)"
    return record


def vector_rows(root: Path) -> dict[str, int]:
    """Stored vectors per database file — the data claim behind the "read-only" line, and
    the one number that opening a store does not move (its bytes do move)."""
    counts: dict[str, int] = {}
    for path in sorted(root.rglob("chroma.sqlite3")):
        found = sqlite_read(path, "SELECT COUNT(*) FROM embeddings")
        counts[path.relative_to(root).as_posix()] = int(found[0][0]) if found else -1
    return counts


def sqlite_read(db_path: Path, query: str, params: tuple = ()) -> list[tuple]:
    """One query against a database file, read-only, closed again whatever happens."""
    try:
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as connection:
            return list(connection.execute(query, params))
    except sqlite3.Error:
        return []


def stores_under(root: Path) -> list[Path]:
    """The root store plus every subdirectory holding its own database file."""
    if not root.is_dir():
        return []
    found = [root] if (root / "chroma.sqlite3").exists() else []
    found += [p.parent for p in sorted(root.rglob("chroma.sqlite3")) if p.parent != root]
    return found


def drop_client_cache(legacy_mod) -> None:
    """The client cache is keyed by path, and a workspace store lives inside the root store."""
    with suppress(Exception):
        legacy_mod.api.client.Client.clear_system_cache()


def write_gate(db_path: Path, payload: dict[str, Any]) -> None:
    """Record the carried metric in the brain's own key/value table.

    The table belongs to the schema, so this adds a key and no table; a reader after the
    move finds the boundary next to the data.
    """
    with sqlite3.connect(str(db_path)) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (GATE_KEY, json.dumps(payload, ensure_ascii=False)),
        )


def already_there(db_path: Path, scope: str) -> set[str]:
    """Ids the target scope already holds, so a second run reports nothing as written."""
    return {str(row[0]) for row in
            sqlite_read(db_path, "SELECT id FROM memories WHERE scope = ?", (scope,))}


def as_list(value: Any) -> list:
    """An embeddings page arrives as an array whose truth value is ambiguous."""
    return [] if value is None else list(value)


def import_collection(collection, *, store_rel: str, source_root: str, target_root: str | None,
                      scope_override: str | None, allow_all: bool, vectors: bool,
                      dry_run: bool) -> dict[str, Any]:
    """Copy one collection's rows into its Kepta scope and return the accounting.

    Nothing is held across rows except counters and the norm sample: a vision row carries
    a base64 crop, so a whole collection in memory is megabytes per thousand rows.
    """
    name = collection.name
    space, vectorizer = index_metric(collection)
    kind, scope = classify(name, scope_override)
    record: dict[str, Any] = {
        "store": store_rel, "collection": name, "kind": kind, "scope": scope,
        "rows": int(collection.count()), "space": space, "embedding_function": vectorizer,
        "dimension": None, "vectors_sampled": 0, "min_norm": None, "max_norm": None,
        "unit_norm": None, "target": "", "imported": 0, "merged": 0,
        "chunks_embedded": 0, "skipped": {}, "gate": None, "error": "",
    }
    if kind == "unknown" and not allow_all:
        record["skipped"] = {"not an Ephe collection": record["rows"]}
        return record

    record["target"] = str(_kepta_db_path(record["scope"], target_root))
    provider = None
    if not dry_run:
        from core.memory_provider import KEPTA, open_provider

        provider = open_provider(KEPTA, scope=record["scope"], persist_dir=target_root,
                                 embedder="auto" if vectors else None)

    norms: list[float] = []
    known = already_there(Path(record["target"]), record["scope"]) if provider else set()
    offset = 0
    try:
        while offset < record["rows"]:
            page = collection.get(include=["documents", "metadatas", "embeddings"],
                                  limit=PAGE_SIZE, offset=offset)
            ids = as_list(page.get("ids"))
            if not ids:
                break
            texts = as_list(page.get("documents"))
            metas = as_list(page.get("metadatas"))
            stored = as_list(page.get("embeddings"))
            for index, doc_id in enumerate(ids):
                text = (texts[index] if index < len(texts) else "") or ""
                metadata = metas[index] if index < len(metas) else None
                vector = stored[index] if index < len(stored) else None
                if vector is not None:
                    record["dimension"] = record["dimension"] or len(vector)
                    if len(norms) < SAMPLE_SIZE:
                        norms.append(math.sqrt(sum(float(v) * float(v) for v in list(vector))))
                if not text.strip():
                    record["skipped"]["no text"] = record["skipped"].get("no text", 0) + 1
                elif str(doc_id) in known:
                    record["skipped"]["already there"] = record["skipped"].get(
                        "already there", 0) + 1
                elif provider is not None:
                    written = provider.store(text, dict(metadata or {}), doc_id=str(doc_id))
                    if written == str(doc_id):
                        record["imported"] += 1
                        known.add(str(doc_id))
                    elif written:
                        record["merged"] += 1
                    else:
                        record["skipped"]["refused"] = record["skipped"].get("refused", 0) + 1
            offset += len(ids)
    except Exception as exc:  # one damaged collection must not end the whole run
        record["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if provider is not None:
            try:
                record["chunks_embedded"] = int(provider.stats().get("chunks_embedded", 0))
            except Exception:
                record["chunks_embedded"] = -1
            provider.close()

    record["vectors_sampled"] = len(norms)
    if norms:
        record["min_norm"], record["max_norm"] = min(norms), max(norms)
        record["unit_norm"] = all(abs(1.0 - value) <= UNIT_NORM_TOLERANCE for value in norms)
    if record["kind"] != "unknown" or allow_all:
        record["gate"] = gate_for(name, space, unit_norm=bool(record["unit_norm"]))
    if record["gate"] and not dry_run and not record["error"]:
        payload = dict(record["gate"], store=store_rel, source_root=source_root,
                       rows=record["rows"], space=space, imported_at=time.time())
        write_gate(Path(record["target"]), payload)
    return record


def _kepta_db_path(scope: str, target_root: str | None) -> Path:
    from core.memory_provider import kepta_db_path

    return kepta_db_path(scope, target_root)


def receipt(records: list[dict], *, source_root: Path, target_root: str | None, dry_run: bool,
            before: dict[str, int], after: dict[str, int]) -> str:
    """What was found, what was written, what was skipped and why — in that order."""
    mode = "read only (--dry-run)" if dry_run else "copy into Kepta"
    lines = [
        f"legacy store import — source {source_root}",
        f"mode: {mode} — target {target_root or 'the configured memory root'}",
        "",
        f"{'collection':<40}{'rows':>6}{'space':>8}{'vectors':>12}  scope",
    ]
    for record in records:
        vectors = ("unit-norm" if record["unit_norm"] else
                   "loose" if record["min_norm"] is not None else "not read")
        lines.append(f"{record['collection'] + ' (' + record['store'] + ')':<40}"
                     f"{record['rows']:>6}{record['space']:>8}{vectors:>12}  "
                     f"{record['scope'] or '-'}")
        if record["imported"] or record["merged"]:
            lines.append(f"    -> {record['target']}  ({record['imported']} row(s) with their "
                         f"ids; the scope holds {record['chunks_embedded']} embedded chunk(s))")
        if record["error"]:
            lines.append(f"    failed: {record['error']}")
        elif "not an Ephe collection" in record["skipped"]:
            lines.append("    skipped: not an Ephe collection (--all takes it)")
        else:
            note = "; ".join(f"{count} {reason}"
                             for reason, count in sorted(record["skipped"].items()))
            if record["merged"]:
                note = "; ".join(filter(None, [note, f"{record['merged']} merged into one fact"]))
            if note:
                lines.append(f"    {note}")
        gate = record["gate"]
        if gate:
            source = gate["source"]
            lines.append(f"  {record['collection']}  {source['space']} distance <= "
                         f"{source['distance']} ({source['origin']})")
            if not gate.get("target"):
                lines.append(f"    -> no conversion: {gate['reason']}")
            else:
                target = gate["target"]
                measured = (f"measured norm {record['min_norm']:.4f}..{record['max_norm']:.4f} "
                            f"over {record['vectors_sampled']} vector(s)"
                            if record["vectors_sampled"] else "no vector sampled")
                lines.append(f"    -> {target['metric']} >= {target['threshold']} "
                             f"({gate['basis']}; {measured})")
                lines.append(f"    recorded as meta['{GATE_KEY}'] in {record['target']}")
    written = sum(record["imported"] for record in records)
    skipped = sum(sum(record["skipped"].values()) for record in records)
    lines += [
        "",
        "source",
        f"  {sum(record['rows'] for record in records)} row(s) read, {written} written, "
        f"{skipped} skipped",
        "  read-only: no add, update or delete was called on a source store",
    ]
    moved = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    state = f"row counts moved in {', '.join(moved)}" if moved else "nothing removed"
    lines.append(f"  stored vectors before/after: {sum(before.values())} -> "
                 f"{sum(after.values())} ({state})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--source", type=Path, help="directory the removed provider wrote")
    parser.add_argument("--target-root", help="memory root to write into")
    parser.add_argument("--scope", help="force one scope for every collection")
    parser.add_argument("--all", action="store_true", help="also take unknown collections")
    parser.add_argument("--dry-run", action="store_true", help="read and report, write nothing")
    parser.add_argument("--no-vectors", action="store_true", help="text only, no model")
    args = parser.parse_args(argv)

    if args.source:
        source = args.source.expanduser().resolve()
    else:
        from core.memory import DEFAULT_MEMORY_DIR

        source = DEFAULT_MEMORY_DIR.resolve()
    stores = stores_under(source)
    if not stores:
        print(f"no store found under {source}: no chroma.sqlite3 in it or below", file=sys.stderr)
        return 1

    before = vector_rows(source)
    legacy_mod = read_client()
    records: list[dict[str, Any]] = []
    options = {"target_root": args.target_root, "scope_override": args.scope,
               "allow_all": args.all, "vectors": not args.no_vectors, "dry_run": args.dry_run}
    for store in stores:
        store_rel = "." if store == source else store.relative_to(source).as_posix()
        client = legacy_mod.PersistentClient(path=str(store))
        try:
            for collection in sorted(client.list_collections(), key=lambda item: item.name):
                records.append(import_collection(collection, store_rel=store_rel,
                                                 source_root=str(source), **options))
        finally:
            drop_client_cache(legacy_mod)
    after = vector_rows(source)
    print(receipt(records, source_root=source, target_root=args.target_root, dry_run=args.dry_run,
                  before=before, after=after))
    return 1 if any(record["error"] for record in records) else 0


if __name__ == "__main__":
    raise SystemExit(main())
