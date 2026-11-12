"""
◑ Ephe – Kepta port: the re-embed pass
core/memory_kepta_reembed.py

A model switch leaves the chunks written before it under the old label, and the
ranking leg selects on the active label. This mixin is the write side that closes
that gap: it selects only the rows whose vector is missing or stamped with another
model, commits one batch at a time and reports progress to its caller. The pass is
therefore idempotent (a finished store costs one count query) and resumable (a run
that stopped halfway continues at the first missing chunk).

Split from `core/memory_kepta.py` for the architecture line limit; the provider
composes it beside `KeptaReadMixin`.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

from typing import Any, Callable

from core.memory_kepta_schema import to_blob


class KeptaReembedMixin:
    """Re-embed methods composed into `KeptaProvider`."""

    def reembed_missing(
        self,
        embed: Callable[[list[str]], list[list[float]]],
        embed_model: str,
        *,
        batch_size: int = 16,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> dict[str, Any]:
        """Give every chunk of this scope a vector under `embed_model`.

        The select takes only rows that carry no vector or one from another model,
        and each batch commits with its label, so the call is idempotent and a run
        that was killed halfway continues from the first missing chunk. The batches
        are small on purpose: a re-embed runs beside the server and must not hold
        the write lock for the length of a whole store.
        """
        if not embed_model:
            raise ValueError("re-embedding needs the model label the vectors are written under")
        predicate = (
            "FROM chunks c JOIN memories m ON m.id = c.memory_id "
            "WHERE m.scope = ? AND (c.embedding IS NULL OR c.embedding_model != ?)"
        )
        total = int(
            self._db.execute(f"SELECT COUNT(*) AS c {predicate}", (self._scope, embed_model)).fetchone()["c"]
        )
        done = 0
        if on_progress is not None:
            on_progress(0, total)
        while done < total:
            rows = self._db.execute(
                f"SELECT c.memory_id AS mid, c.seq AS seq, c.text AS text {predicate} "
                "ORDER BY c.memory_id, c.seq LIMIT ?",
                (self._scope, embed_model, max(1, int(batch_size))),
            ).fetchall()
            if not rows:
                break
            vectors = embed([str(row["text"]) for row in rows])
            if vectors is None or len(vectors) != len(rows):
                raise RuntimeError(
                    f"the embedder returned {0 if vectors is None else len(vectors)} vector(s) "
                    f"for {len(rows)} chunk(s)"
                )
            for row, vector in zip(rows, vectors):
                self._db.execute(
                    "UPDATE chunks SET embedding = ?, embedding_model = ? "
                    "WHERE memory_id = ? AND seq = ?",
                    (to_blob([float(v) for v in vector]), embed_model, row["mid"], int(row["seq"])),
                )
            self._db.commit()
            done += len(rows)
            if on_progress is not None:
                on_progress(done, total)
        return {"total": total, "embedded": done, "label": embed_model}
