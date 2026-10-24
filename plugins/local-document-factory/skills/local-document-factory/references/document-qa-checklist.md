# Document QA Checklist

Run this checklist after every artifact build. Report PASS or FAIL per line; a failed line is a failed delivery, not a warning.

1. **File exists** - the tool returned a real path and `verify_artifact` returned `ARTIFACT_VERIFIED` for that exact path.
2. **Openable** - the format matches the suffix (PDF, DOCX, XLSX, PPTX) and the tool reports a readable file.
3. **Structure** - title, purpose, body sections and a closing section are present; the document is not a wall of text.
4. **Fact trace** - every number and proper name appears in the request or in a read source; no invented customer, date or figure.
5. **Source line** - the exact source line from the fact sheet is present when the document carries facts.
6. **Size** - the measured page or slide count matches the requested scope; state both numbers.
7. **Placeholders** - no `TODO`, `TBD`, `Lorem ipsum`, `[...]` or "insert here" remains.
8. **Secrets** - no credential, token or private-key material appears in the artifact or the answer.
9. **Cross-format consistency** - when one fact pack produces several formats, the same figure carries the same value and unit in each artifact.
10. **QA verdict** - the answer names the artifact path, the measured size, the verification line and the PASS/FAIL result for this checklist.
