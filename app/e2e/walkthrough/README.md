# Walkthrough captures

The specs in this directory drive the running product and write down what they measured:
screenshots, `observations.json`, `measurements.json`, `timing.json`, per-step notes. One
pass was run for wave 10 and its output is the dated record under
`docs/media/user-walkthrough-2026-10-12/<spec>/` — 346 tracked files that `FINDINGS.md`
and the per-spec notes cite by path.

## Where a run writes

`walkthroughOutDir(slug)` (`walkthrough-out.ts`) resolves the directory:

| `EPHE_WALKTHROUGH_OUT` | output |
| --- | --- |
| unset | `app/.walkthrough-out/<slug>/` (git-ignored) |
| set | `<EPHE_WALKTHROUGH_OUT>/<slug>/`, repo-relative or absolute |

Every spec calls it, so an ordinary verification run leaves `docs/media` untouched and the
dated record stays exactly as it was committed. The run prints the directory it wrote to.

## Producing a fresh dated set

Point the knob at the record, then read what came out before anything enters the tree:

    cd app && EPHE_WALKTHROUGH_BASE=http://127.0.0.1:8765 \
      EPHE_WALKTHROUGH_OUT=docs/media/user-walkthrough-2026-10-12 \
      npx playwright test e2e/walkthrough/persona-07-handy.spec.ts --workers=1

That rewrites the tracked files of that spec, so `git status docs/media` is the review
queue: keep the frames a finding cites, commit those, and check out the rest. A run that
is not meant to change the record needs no variable at all.

`EPHE_WALKTHROUGH_BASE` must name a server that serves the build under test — the app
under `dist/` of the checkout you are verifying, not a server another checkout happens to
have left on the port.

Specs that write into the record, and now into the capture root by default:
`deny-visible`, `modes-matrix`, `persona-01-erstnutzer`, `persona-02-erste-frage`,
`persona-03-datei-auftrag`, `persona-04-tool-freigabe`, `persona-05-einstellungen-suchen`,
`persona-06-tastatur`, `persona-07-handy`, `persona-08-speicher`, `persona-09-werkbank`,
`persona-10-fehlerfaelle`, `plan-accept`, `session-deep`, `what-it-tells-you` — fifteen of
fifteen in this directory.

The `Run` snippets inside the dated `notes.md` files predate this and name no variable;
they land in the capture root, which is the safe direction.
