# Artifact Contract

One fact sheet feeds every format. The contract is the same in each:

| Format | Tool | Required sections | Measured evidence |
|---|---|---|---|
| PDF | build_document / create_pdf | title, executive summary, findings, source notes | page count from verify_artifact |
| DOCX | create_docx | title, overview, key points, details and next steps | openable file from verify_artifact |
| XLSX | create_xlsx | Inputs, Model, Output | formulas present; file verified |
| PPTX | create_pptx_deck | cover, thesis, evidence, ask | slide count and qa_pptx_deck result |

Rules:

- A document is a file, not a description. If no tool returned a path, the artifact does not exist.
- The source line is copied verbatim from the fact sheet; it is not paraphrased per format.
- Numbers keep their unit and period across formats (`Revenue 4.2M EUR, Q3 2026`, not `4.2` in one file and `4.2M` in another).
- The fact sheet distinguishes supplied facts, read sources and open gaps. An open gap stays an open gap in every artifact.
- A deck slide carries one claim; a workbook sheet carries one role; a DOCX section carries one purpose.
- File names are ASCII-safe slugs with the correct suffix and no path traversal.
