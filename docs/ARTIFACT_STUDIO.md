# Artifact studio — files open, render and can be edited inside Ephe (2026-10-29)

Owner order (2026-10-29): a file the assistant produces — a landing page, a PDF, a
spreadsheet, a deck — has to open **in the chat**, look right for its kind, and be
editable there, so the user does not leave the product to finish a document. The
reference is a desktop operating system that simply has the right program for each
output. This page records what exists, what is missing, the options measured against
the state of the art today, and the order the gaps close in.

## What exists today (evidence in this tree)

| Capability | Where | State |
|---|---|---|
| Preview dispatcher by extension | `app/src/lib/previewMode.ts` | image, frame (pdf/html), audio, video, content (xlsx/csv/docx/text), code, none |
| Server extraction for kinds a browser cannot render | `core/artifact_preview.py` | xlsx → table, docx → markdown text, text kinds → text, pptx → slides (2026-10-29) |
| Card and pane surfaces | `artifacts/preview.tsx`, `artifacts/messageCard.tsx`, `ArtifactRail.tsx` | inline preview in the chat message, pane in the rail, lightbox for images |
| Producing tools | `core/tools/office_tools.py` | `create_xlsx`, `create_docx`, `create_qrcode`; no deck writer |
| Sandboxed frames | `previewSandbox` + CSP `sandbox` on the file routes | html/svg run without same-origin; pdf keeps the browser viewer |

So opening and rendering exists for most kinds. The honest gaps are:

1. **Nothing renders a deck's shape.** A `.pptx` reached the card as "no viewer".
   Closed on 2026-10-29 by a slide read on the server (title and body lines per
   slide, standard library only) and a slide card in the preview pane.
2. **No file can be edited.** Every surface reads. The owner's order asks for the
   editing side, and that is where the design work starts.
3. **The desktop window's previews follow the bundle, not the server.** A file that
   was just written opens in the PWA immediately; the bundled window needs the
   release that carries the same code.
4. **No "open with" handoff.** A user who wants a real office program has no way to
   say so from the card, and no statement of what that program would be.

## Options, measured against today's field

| Kinds | Option | Licence | Fit for Ephe |
|---|---|---|---|
| Sheets | Univer (office SDK, sheets/docs/slides, browser + node) | Apache-2.0 core | Strong: embeds in React, self-hosted, no server, designed for agent-produced files |
| Word (.docx) | SuperDoc (browser DOCX editor with a document API) | open source | Strong: renders and edits OOXML in the page, no server round trip |
| Word (.docx) render only | `docx-preview` / existing python-docx text | MIT | Cheap fallback; no editing |
| PDF | PDF.js viewer + annotation layer | Apache-2.0 | Strong: renders and annotates in-page, works offline |
| Every office kind, full fidelity | LibreOffice compiled to WebAssembly (ZetaOffice / zetajs) | MPL-2.0 | Highest fidelity, heaviest payload (tens of MB); viable as an opt-in "full editor" |
| Every office kind via a server | Collabora Online or ONLYOFFICE Document Server | AGPL-3.0 / AGPL-3.0 | Complete suites, but a service the user must run and a licence that demands care; opt-in connector only |
| Native handoff | macOS `open`, Windows `ShellExecute` from the desktop shell | — | Honest escape hatch: the card names the program that would open the file |

Decision: **render in the product, edit in the product for the formats a browser can
own, and hand off — never fake it — for the rest.** That keeps Ephe offline-first and
dependency-light, and it makes the boundary visible instead of approximating Word.

## Phases and acceptance

**V1 — viewer parity (started 2026-10-29).** Every produced kind opens in the chat with
the right shape: image, pdf, html, audio, video, code, markdown, table, slides.
*Accept:* a deck, a spreadsheet, a document, a page and a PDF each open from the
message and from the rail; no kind ends in an empty surface.

**V2 — light editing.** Text, markdown, CSV and JSON edit in place with save-as-version;
the artifact store already keeps versions. Sheets get a grid editor (Univer) with
XLSX import/export. PDF gets annotation (PDF.js) without rewriting the original.
*Accept:* an edit produces a new artifact version, the original stays readable, and the
diff is visible in the card.

**V3 — document editing.** DOCX editing with SuperDoc; deck editing follows the same SDK
family (Univer documents/slides). Both run in the page, offline.
*Accept:* round-trip a .docx and a .pptx produced by the assistant, edit, save, reopen —
byte-faithful for untouched parts.

**V4 — the escape hatches.** "Open with <program>" from the card: the desktop shell
hands the file to the system's default app; a server-side connector is offered for a
user who already runs a full office suite. "Edit in full editor" becomes a WASM
LibreOffice session behind an explicit, measured download.
*Accept:* the card always names what will open the file, and no path is a dead end.

## Roles for the work

- **Product:** every phase is judged by "the user never leaves Ephe to read their own
  output"; each phase names what still requires an external program.
- **Security:** editors are third-party code. They run in the same frame policy as the
  previews (`previewSandbox`), never with same-origin, and an editing session gets the
  file through the artifact route only. A WASM office runtime is a network surface
  change and needs the same review as a new engine.
- **Frontend:** one dispatcher (`previewMode`) stays the single source; editors mount
  behind it, so a new kind is one table row and one component.
- **Backend:** extractions stay dependency-light and total-time bounded; a new parser
  needs a test with a real file of that kind.
- **Docs:** `docs/ARTIFACTS.md` records the matrix per phase, with the option and its
  licence.

## What this page is not

It is not a promise of a full office clone inside the window. The owner's bar is that
the user can open and finish their file in Ephe; where a format needs a program Ephe
does not carry, the card says which one and offers the handoff.
