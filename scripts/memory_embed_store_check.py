#!/usr/bin/env python3
"""Re-embed a Kepta memory store and report every vector that does not come back.

Why this is a script and not a test: the claim it checks is about *data* — the
vectors already in someone's brain — not about the code that produced them. The
suite in `tests/test_memory_embed_onnx.py` freezes the retired store's bytes for eight probe
texts and runs anywhere; this walks a real store, opens it read-only, re-embeds
every chunk with `core/memory_embed_onnx.py` and compares the 1536 bytes it gets
with the 1536 bytes that are on disk. It is the check to re-run before and after
anything that touches the embedder, and the one to run once per store when the
migration lanes move stores around.

Only chunks whose `embedding_model` matches the file being read are compared — the
product has stores under more than one embedder (`nomic-embed-text` in a Kepta
store, `vision_rules` under an L2 metric elsewhere), and a store that holds vectors
this model did not write is reported as skipped rather than as a failure.

Nothing is written: the connection is opened `mode=ro` and the model is read from
its cache. Exit code 1 means at least one stored vector could not be reproduced,
which is the condition that makes a stored vector stale.

Usage:
    python3 scripts/memory_embed_store_check.py                 # every store it finds
    python3 scripts/memory_embed_store_check.py --db PATH ...   # named stores
    python3 scripts/memory_embed_store_check.py --limit 1000    # chunks per store
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

DEFAULT_ROOTS = (Path.home() / ".ephe" / "memory" / "kepta", Path.home() / ".kepta")


def stores(argv_paths: list[str]) -> list[Path]:
    if argv_paths:
        return [Path(p).expanduser() for p in argv_paths]
    found: list[Path] = []
    for root in DEFAULT_ROOTS:
        if root.is_dir():
            found.extend(sorted(root.glob("**/kepta.db")))
        elif root.exists():
            found.append(root)
    return found


def chunks(db: Path, model: str, limit: int) -> tuple[list[tuple[str, bytes]], list[tuple[str, int]]]:
    """Stored (text, blob) rows for one model, plus a census of what the store holds."""
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "select text, embedding from chunks "
            "where embedding_model = ? and embedding is not null limit ?",
            (model, limit),
        ).fetchall()
        seen = conn.execute(
            "select coalesce(embedding_model, '(null)'), count(*) from chunks group by 1"
        ).fetchall()
    finally:
        conn.close()
    return [(str(row[0]), bytes(row[1])) for row in rows], [(str(row[0]), int(row[1])) for row in seen]


def main(argv: list[str]) -> int:
    headline = (__doc__ or "Kepta store check").splitlines()[0]
    parser = argparse.ArgumentParser(description=headline)
    parser.add_argument("--db", action="append", default=[], help="a kepta.db to check")
    parser.add_argument("--limit", type=int, default=250, help="chunks per store")
    parser.add_argument("--model", default=None, help="override the model name to filter on")
    args = parser.parse_args(argv)

    from core.memory_embed_onnx import MODEL_NAME, MiniLmEmbedder, model_problem

    model = args.model or MODEL_NAME
    problem = model_problem()
    if problem:
        print(f"the embedder refuses this machine's artifact: {problem}")
        return 2

    found = stores(args.db)
    if not found:
        print("no store found; pass --db PATH")
        return 2

    embedder = MiniLmEmbedder()
    failed = 0
    for db in found:
        if not db.is_file():
            print(f"{db}: no such file")
            failed += 1
            continue
        rows, seen = chunks(db, model, args.limit)
        holders = ", ".join(f"{name}={count}" for name, count in seen)
        if not rows:
            print(f"{db}: holds no {model!r} vector ({holders}) — skipped")
            continue
        measured = embedder.blobs([text for text, _ in rows])
        stored = [blob for _, blob in rows]
        bad = [i for i, (mine, theirs) in enumerate(zip(measured, stored)) if mine != theirs]
        state = "identical" if not bad else f"{len(bad)} DIFFERENT"
        print(f"{db}: {len(rows)} chunk(s) of {model!r} re-embedded — {state} ({holders})")
        if bad:
            failed += 1
            for i in bad[:5]:
                text, blob = rows[i]
                print(f"  {text[:70]!r} — {len(blob)} stored bytes vs {len(measured[i])} measured")
    print("store check:", "PASS" if not failed else f"FAIL on {failed} store(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
