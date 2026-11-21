# Notebook Schema

`create_source_notebook` returns a local manifest path (`SOURCE_NOTEBOOK_FILE`). The manifest is the contract between the index step and every later query.

| Field | Meaning |
|---|---|
| `title` | Human-readable notebook title |
| `created_at` | Local timestamp of the index run |
| `sources` | One entry per indexed file: path, content hash, kind and chunk count |
| `chunks` | Evidence chunks with a stable ID (`S001-C001`), source path and text |

Rules:

- The manifest stays on the user's machine; it is not uploaded.
- A source path is the real path that was read, never a guessed path.
- Chunk IDs are stable for the life of the notebook; a re-index creates a new manifest.
- A query returns at most the requested number of chunks and names the chunk IDs it used.
- A brief or a deck cites the same chunk IDs as the query; it does not paraphrase a citation into a different ID.
- A source that cannot be read is reported as missing; it is not silently dropped from the register.
