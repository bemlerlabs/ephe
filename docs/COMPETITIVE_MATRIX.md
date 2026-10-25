# Competitive matrix — evidence only

Wave S21 W0, 2026-10-25. A cell says what we observed and where. `unmeasured`
means exactly that: nobody ran the check. No cell claims "better" — a
comparison earns that word only with a number beside it.

| Axis | Ephe | Hermes CLI | Hermes Desktop | Qoder Desktop | pi coding agent |
|---|---|---|---|---|---|
| Installation | One command from a public checkout; the app updates itself. Evidence: `install.sh`, this receipt | not installed here; unmeasured | not installed here; unmeasured | installed and in use on this host; version not read for this table | not installed here; unmeasured |
| Engine ownership | Persisted `~/.ephe/engine.json` or an explicit env; no default; fail-closed. Evidence: `core/engine_config.py`, `/api/health` | unmeasured | unmeasured | vendor-hosted models; no local engine choice observed | unmeasured |
| Chat continuity | Abort at 1,152 chars, no terminal frame; the same session's next message reached `done` in 1.99 s. Evidence: S21 receipt, wire log | unmeasured | unmeasured | not exercised for a forced mid-stream close | unmeasured |
| Web research | `web_search` + `fetch_url`; fetch is a pure page read since this wave. Evidence: tool code, live turn | unmeasured | unmeasured | has web access in the agent; not measured for source display or failure status | unmeasured |
| Images | Composer: thumbnail, name, size, lightbox; history: artifact route. Evidence: S21 tests, `/images` 200 | unmeasured | unmeasured | attaches images; not measured for preview/lightbox | unmeasured |
| Artifacts | Artifact workbench with birth session and a 30-day question; route tested | unmeasured | unmeasured | has an artifact/task panel by vendor documentation; not measured here | unmeasured |
| Skills / plugins | Skills with a tool whitelist, plugin marketplace with a six-field contract; 22 entries | unmeasured | unmeasured | Skills and MCP connectors in the product; counts not read | unmeasured |
| CLI / TUI | `ephe` CLI plus a Textual TUI; JSON seams tested (`update --json`, `plugin list --json`) | the product is a CLI; features not measured | unmeasured | desktop-first | the product is a CLI; not installed |
| Design | Dark agentic workbench; chrome budget and contrast rules in the repo | unmeasured | unmeasured | polished desktop product; not compared pixel-wise | unmeasured |
| Error behaviour | Tool failures carry a reason code and a translated sentence; a fetch failure is `failed`, not `Completed` | unmeasured | unmeasured | not exercised for a failed tool status | unmeasured |
| Measurements | Local numbers only where a command produced them (S19/S21 receipts) | none | none | none | none |

## What is missing before any claim

1. Install and version of every competitor on this host, with the command.
2. One identical task per axis, same engine budget, same time limit.
3. The raw logs (tool frames, status lines) of the competitor runs, not a
   summary.
4. A buyer-facing axis choice: web research, coding, design, or CLI. The order's
   recommendation is to measure web, coding and design first.

## Red team — the three strongest objections

1. **"Ephe ships a defect the competitor does not have."** The in-app update
   moved the shell and left the backend behind. Until the shell verifies the
   backend version, this is a real reliability gap.
2. **"The comparison is one-sided because only Ephe was measured."** Correct.
   The matrix documents Ephe's evidence and leaves the others unmeasured; it
   cannot support a positioning claim yet.
3. **"A local-first workspace without a benchmark is a preference, not an
   advantage."** Also correct. The release gate says a claim needs a number; the
   numbers are not there. The honest sentence today names the property, not a
   ranking.
