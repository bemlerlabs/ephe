# Demos

The tree publishes no recorded clips. The ten WebP clips that this page tabulated and the
Film Studio film beside them were retired on 2026-11-24 by owner decision, and nothing was
recorded or generated to stand in for them. What a reader can look at is listed here, and
what it takes to add to that list is the same rule the tree already holds for every image.

## What is here

| material | where | what it shows |
| --- | --- | --- |
| three product captures | [`screenshots/`](screenshots/): `readme-chat-1280.png`, `readme-chat-390.png`, `readme-settings-1280.png` | the built PWA at a desktop and a phone viewport; [`screenshots/PROVENANCE.md`](screenshots/PROVENANCE.md) names the build, the server and the date behind each frame |
| the first-run film | `app/public/onboarding/`, played by the product itself on a machine that has not run it before | the awakening sequence, before the desk appears |

## What earns a place

Root `AGENTS.md`, "Generated media", is the rule and this page does not restate it beyond
the one consequence that matters here: a capture is published when a committed document
names, for that file, the surface it targets and the decision it is evidence for, and when
its pixels come from the product. A clip of a surface that has since moved is a clip of an
older product, which is what the retired clips had become.

## Recording one

`scripts/record_demo.py` is tracked in this checkout. It drives a cached Chromium against
the product server on `127.0.0.1:8765`, takes the cases named on its command line
(`chat`, `shell`, `help`, `edit`), and writes its output under `/tmp/ephe_demo/` — nothing
into the tree. Its `preflight()` refuses before a browser opens and names the command that
would fix the machine, so a capture is a decision made afterwards, not a side effect of
running the script.
