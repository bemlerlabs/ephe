# Walkthrough captures

The specs in this directory drive the running product and write down what they
measured: screenshots, `observations.json`, `measurements.json`, `timing.json`,
per-step notes. A run writes to an ignored capture root; nothing from a run is
committed, and no file in the tree cites a run's output as evidence. Where a
spec states what a walkthrough found, the spec itself — its selectors, its
expectations, its prose — is the record.

## Where a run writes

`walkthroughOutDir(slug)` (`walkthrough-out.ts`) resolves the directory:

| `EPHE_WALKTHROUGH_OUT` | output |
| --- | --- |
| unset | `app/.walkthrough-out/<slug>/` (git-ignored) |
| set | `<EPHE_WALKTHROUGH_OUT>/<slug>/`, repo-relative or absolute |

Every spec calls it, so an ordinary verification run leaves `docs/media`
untouched. The run prints the directory it wrote to.

## Producing a fresh dated set

A release engineer produces a set before a release read-out, as run output only:

    cd app && EPHE_WALKTHROUGH_BASE=http://127.0.0.1:8765 \
      EPHE_WALKTHROUGH_OUT=/tmp/ephe-walkthrough-$(date +%F) \
      npx playwright test e2e/walkthrough/persona-07-handy.spec.ts --workers=1

Read what came out before quoting any of it; nothing enters the tree from it.
A run that is not meant to write anywhere else needs no variable at all.
To check a produced round's media files with the browser gate, name the directory
to it: `EPHE_Q_MEDIA_ROUND=<dir> pnpm exec playwright test -c
tests/playwright/playwright.config.ts tests/playwright/q-quality.spec.ts -g QG6`.

`EPHE_WALKTHROUGH_BASE` must name a server that serves the build under test —
the app under `dist/` of the checkout you are verifying, not a server another
checkout happens to have left on the port.

All fifteen specs in this directory write captures: `deny-visible`,
`modes-matrix`, `persona-01-erstnutzer`, `persona-02-erste-frage`,
`persona-03-datei-auftrag`, `persona-04-tool-freigabe`,
`persona-05-einstellungen-suchen`, `persona-06-tastatur`, `persona-07-handy`,
`persona-08-speicher`, `persona-09-werkbank`, `persona-10-fehlerfaelle`,
`plan-accept`, `session-deep`, `what-it-tells-you`.
