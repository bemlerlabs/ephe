# Quality Rubric

1. The notebook, brief or deck is backed by real tool output (`SOURCE_NOTEBOOK_FILE`, `SOURCE_BRIEF_FILE`, `PPTX_DECK_FILE`).
2. Every grounded claim carries a chunk ID returned by `query_source_notebook`.
3. Every claim is labelled primary, secondary, user-provided, external or assumption.
4. Unsupported claims are named as unsupported and kept out of the conclusion.
5. No chunk ID, path or quotation is invented.
6. The notebook stays local; no cloud upload is required.
7. Credential material is summarised as redacted, never reproduced.
8. A gap in the sources is reported as a gap, not filled with general knowledge.
9. A deck carries one claim per slide and a citation in the speaker notes.
10. The answer ends with an evidence register and the open gaps.
