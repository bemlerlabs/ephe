# Memory: the store, its vectors, and the re-embed path

Status 2026-11-12. The product keeps one long-term store, Kepta (SQLite + FTS5),
under `~/.ephe/memory/kepta/<scope>/kepta.db`; the scope is the 16-hex workspace
hash, so two projects never read each other's facts. A retired store on disk is
recognised and named, never opened: the read is the offline command
`scripts/import_legacy_store.py`. The choice of provider is recorded in
`~/.ephe/memory/provider.json`, and `EPHE_MEMORY_PROVIDER` wins over the record.
`core/memory_provider.py` holds that resolution; `core/memory.py` is the facade.

## The vector arm is optional

Search fuses three legs: BM25 over FTS5, an entity graph, and brute-force cosine
over stored vectors. The first two always carry. The third needs an embedding
model on disk, and the install ships without one.

| Model | Where it lives | When it is used |
|---|---|---|
| `embeddinggemma-2` | `~/.ephe/models/embeddinggemma-2` | when the ONNX export is complete on disk |
| `all-MiniLM-L6-v2` | the retired store's cache (`~/.cache/chroma/onnx_models`) | only while that cache still holds it |

On a fresh installation neither is present. The vector arm is then off, and that
is reported, not papered over: `GET /api/memory/stats` answers `vector_leg: false`
and the numbers `chunks` / `chunks_embedded`. `GET /api/models/embedding` says
what the model directory is missing, how large the fetch is (542 MB) and whether
the consent setting would allow an automatic one.

The model labels are separate vector spaces. `chunks.embedding_model` carries the
label that wrote the vector, and the ranking leg selects only the active label. A
machine that switches models keeps the old vectors in the file; they are simply
not scored until the chunks are re-embedded under the new label.

## Fetching the model

The fetch is never automatic on a start. Two spellings allow it, the same pair
the speech model uses:

- `EPHE_EMBEDDINGGEMMA_DOWNLOAD=1` for a shell;
- the deep setting `memory.embedder_allow_download` for the desktop app.

`POST /api/models/embedding/download` is the one-click offer. The call itself is
the consent for that one fetch (`ensure_model(allow_fetch=True)`) and writes no
setting, so the next start needs the documented switch again.
`EPHE_OFFLINE=1` refuses every fetch. The download route requires the
`X-Requested-With` marker and the confirm word `download`.

After a successful fetch the running process is handed the new model: the
embedding factory cache, the memory facade and the route cache are reset, and the
re-embed pass starts (see below). Before that change a finished fetch changed
nothing until a restart.

## Re-embedding

A model on disk says nothing about the chunks written before it. The pass in
`core/memory_reembed.py` walks the chunks that carry no vector or one under a
different label and writes the active label, batch by batch.

- `KeptaProvider.reembed_missing` selects
  `embedding IS NULL OR embedding_model != <active label>`, embeds at most 16
  chunks per batch and commits each batch. The pass is therefore idempotent (a
  finished store costs one count query) and resumable (a killed run continues at
  the first missing chunk).
- It runs on a daemon thread, never on the request thread, and uses the
  provider's per-thread SQLite connection.
- It starts by itself after a successful fetch. `POST
  /api/models/embedding/reembed` (confirm word `reembed`) is the resume path for a
  process that restarted mid-pass, or for a store written while the arm was off.
- Progress is part of `GET /api/models/embedding` under `reembed`:
  `running`, `done`, `total`, `embedded`, `remaining`, `label`, `error`.
- The store is local-only here. A bridge or a plugin provider has its chunks on
  the other machine, and the facade refuses instead of pretending to know.

The surfaces state coverage, not a verdict. The inventory page prints
"X of N notes have a vector" (and names an empty inventory and a switched-off
arm); the Brains sub-page repeats the numbers beside the legs and offers
"Re-embed missing vectors" while the coverage is incomplete and the vector arm
loads. The same page shows 0 of N in the warning colour; "carries" next to 0 of 45
was the contradiction this replaces.

## Diagnostics

`scripts/memory_embed_store_check.py` opens a store read-only, re-embeds every
chunk under a named model and compares the stored blob with the computed one. Run
it on a store before and after anything that touches the embedder; it writes
nothing and reports unreadable or stale vectors by chunk.

`EPHE_MEMORY_EMBEDDER=none` (or `off`, `0`, `false`, `lexical`) turns the vector
arm off for a process. `memory.embedder` selects the model family; the fallback
to MiniLM is a property of the artifact cache, not a product download.

## Related

- `core/memory_embed.py` — factory, label, kill switch.
- `core/memory_embed_gemma.py` — EmbeddingGemma load, consent, status.
- `core/memory_embed_onnx.py` — MiniLM loader and its cache check.
- `core/memory_kepta_read.py` — stats and the leg counters.
- `server/routes/models.py` — the offer, the fetch, the re-embed route.
- `docs/ARCHITECTURE.md` §6 — the same picture in one line.
