# Citation Contract

A citation is a pointer to a chunk the notebook actually returned. It is not a source name, a URL or a page number on its own.

Format:

    [S001-C001]

- `S001` is the source number, `C001` the chunk number inside that source.
- The chunk ID must come from `query_source_notebook` output or the notebook manifest.
- Put the citation immediately after the claim it supports.
- A quote is reproduced verbatim inside quotation marks and followed by its chunk ID.
- A claim that spans two sources carries both IDs.
- A claim with no returned chunk is labelled `assumption` or `unsupported`; it never receives a citation.
- Never reuse a chunk ID for a different claim than the one the chunk supports.
- Never invent a chunk ID to make an answer look grounded.

Answer shape:

    Conclusion: <one sentence>
    Evidence: <claim> [S001-C004]; <claim> [S002-C001].
    Unsupported: <claim> (no returned chunk).
    Gaps: <source or question the notebook does not cover>.
