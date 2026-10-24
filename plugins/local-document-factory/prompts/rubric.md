# Rubric - Suite `local-document-factory`

The matrix runs each case three times and counts a case only when all three
pass. The receipt names the engine, the model, the commit and n. No comparison
against other models until they have run the same cases.

Criteria:
1. **Real artifact**: every requested format ends in a file returned by the format tool.
2. **Verified**: `verify_artifact` returned `ARTIFACT_VERIFIED` for that path; a deck also has `qa_pptx_deck` output.
3. **One fact pack**: the same number carries the same value and unit in every format.
4. **Source line**: the supplied source line is present and unchanged.
5. **Measured size**: the answer states the page or slide count from the verification output.
6. **QA verdict**: PASS or FAIL per checklist item; a failed check is reported, not hidden.
7. **No invention**: no customer, number, date or source outside the request or a read file.
8. **No placeholders or secrets**: no TODO/TBD/Lorem ipsum and no credential in an artifact.
