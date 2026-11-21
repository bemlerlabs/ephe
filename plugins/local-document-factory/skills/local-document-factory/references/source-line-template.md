# Source Line Template

Use exactly one source line in a document that carries facts:

    Source: <source name>, <date>

Examples:

    Source: Q3 finance dashboard, 2026-10-22
    Source: project risk register, 2026-10-22
    Source: user-provided fact sheet, 2026-10-22

Rules:

- The source must be supplied by the user or read from a local file. Never invent a source name.
- If several sources back the document, list them comma-separated after one `Source:` label.
- If no source was supplied, write `Source: user-provided facts, <date>` only when the user supplied the facts; otherwise write `Source: not provided` and keep the gap visible.
- The source line is identical in the PDF, DOCX and PPTX that share the fact sheet.
