# Skills

51 built-in skill packs ship in `skills/` as versioned skill packs (`skills/{name}/SKILL.md` plus
examples and references). They cover writing, business analysis, and real office artifacts; the
common ones also appear as chips in the composer, and typing `/` opens the full list.

Two of them are factories: `/factory` builds a complete, runnable project (scaffold, tests, docs,
git) and `/doc-factory` delivers report-grade briefing PDFs. Both run only after the evidence gate
has verified the artifact.

| Skill | Behavior |
|---|---|
| `/write` | Draft emails, notes, summaries, and structured text |
| `/review` | Review code, plans, or documents |
| `/files` | Work with local files through approved tools |
| `/pdf` | Analyze and create PDF-oriented content |
| `/scan` | Analyze screenshots or images; approval is required for risky actions |
| `/svg` | Draft SVG assets |
| `/chart` | Create chart-ready output |
| `/shell` | Prepare shell commands; execution requires approval |
| `/research` | Optional online research; confirmation required before sending |
| `/image` | Generate real PNG/JPEG images through an OpenAI-compatible image endpoint you configure (free & local via [LocalAI](LOCAL_IMAGE_ENGINE.md)) |

Settings → Skills installs your own packs (zip/tar.gz, path-traversal-guarded), toggles skills off,
and removes user packs.

Beyond the slash shortcuts, artifact skills route deterministically to **real local tools** that
generate files on your machine: Excel sheets (`xlsx-creator`), Word documents (`docx-creator`), QR
codes (`qrcode-creator`), diagrams (`diagram-creator`), decks (`deck-creator`), and PDFs
(`pdf-creator`). The full list lives in [`skills/`](../skills).
