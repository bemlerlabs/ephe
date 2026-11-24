# docs/ — the index

The documentation that ships with this repository. Every page here is written for the
release it sits in: there is no second copy to fall out of date. Nothing here is needed to
run Ephe — that is [QUICKSTART.md](QUICKSTART.md) and [INSTALL.md](INSTALL.md).

## Get started

| File | Content |
|---|---|
| `QUICKSTART.md` | Install, start, choose an engine, first answer — one page |
| `INSTALL.md` | The install guide the root README references |
| `INSTALL_OPTIONS.md` | Every install path, the flags, Docker, uninstall, what the installer checks |
| `FIRST_RUN.md` | The same walkthrough at length, with the screens and the measured sequence |
| `SWITCHING.md` | Import an existing local-agent setup into Ephe |
| `CLI.md` | `ephe` command reference and the engine-resolution rule |
| `UPDATES.md` | The three update paths: desktop app, PWA, terminal; release vs commit channels |
| `OPERATIONS.md` | Starting, stopping and owning the backend, and the one promise about this machine |
| `RELEASE_POLICY.md` | What earns a release tag and what rolls untagged: milestones are tagged, QoL and fixes ride the rolling channel |
| `MOBILE.md` | Pairing a phone over the LAN, the QR walkthrough and the public-access rule |
| `TELEGRAM.md` | The Telegram channel: gateway status, pairing, hardening |
| `VOICE.md` | The offline voice loop (Piper TTS) |
| `LOCAL_IMAGE_ENGINE.md` | Local image generation |

## Product and behaviour

| File | Content |
|---|---|
| `FEATURE_STATUS.md` | What is active, experimental and planned, with the limits the table does not capture |
| `ARCHITECTURE.md` | Topology, module map and the contracts between them |
| `CONTEXT_CONTRACT.md` | The workspace context layers, their precedence, caps, status words and `paths:` rules |
| `SECURITY_AND_PRIVACY.md` | The security and privacy mechanisms in one table |
| `BRAND.md` | The name, the marks, the palette and the claim boundary, each named with the file that enforces it |
| `SECURITY_THREAT_MODEL.md` | STRIDE threat model, including the engine-token paths |
| `TCC.md` | Why a rebuild can lose a macOS privacy grant, and what a stable signature changes |
| `SANDBOX_EXECUTION.md` | The Ephemora cell sandbox (opt-in) |
| `COMPOSER_MODES.md` | The four response modes, the header control and what each mode sends |
| `COMPOSER_MOBILE.md` | The composer's mobile lane and its measured floors |
| `ACCESSIBILITY.md` | The target-size floor, the 44 px desktop assessment and the gates that hold both |
| `EPHEMERIDES.md` | The Ephemerides |
| `PERSONA_PACKS.md` | Persona packs: versioned markdown bundles behind `~/.ephe/persona.md` |
| `MEMORY.md` | The long-term store Kepta, its vectors and the re-embed path |
| `SKILLS.md` | The built-in skill packs and the artifact tools they route to |
| `SKILL_PACKS.md` | How a skill pack is put together |
| `WEB_INTAKE.md` | The `web_research` tool, its two evidence routes, hybrid workspace evidence and the citation check |

## Extending

| File | Content |
|---|---|
| `PLUGINS_OVERVIEW.md` | The first-party plugin bundles |
| `PLUGINS.md` | The plugin manifest format, v1 and v2 |
| `PLUGIN_SDK.md` | Guide for plugin authors |
| `PLUGIN_PRACTICES.md` | Patterns a bundle follows once it ships |
| `PLUGIN_COVERAGE.md` | What a bundle can extend today, one decision line per capability class with `file:line` evidence |
| `PLUGIN_EXPORT.md` | How a made bundle is packed, signed, and checked against an installed identity, and where the lockfile is written |
| `DISCOVER_MARKETPLACE_DESIGN.md` | The design behind the Discover shelf — the shelf ships (`/discover`, `server/routes/discover.py`), the document is what it was designed against |

## Measurement and project

| File | Content |
|---|---|
| `DEMO_VIDEO.md` | The 40 second Film Studio film in the README, and where each of its frames came from |
| `PERFORMANCE_BASELINE.md` | Measured start-up and window-memory numbers, with the commands that take them |
| `E2E_CI.md` | What the browser legs of the frontend build run, the numbers measured locally on 2026-11-24, and the coverage this tree cannot claim |
| `benchmark-mapping.md` | Why Ephe measures its own harness instead of attaching to an external suite |
| `DEMOS.md` | The demo clips and how they were captured |
| `HISTORY.md` | The product's own account of how it came to be, written for the release it ships in |
| `DEVELOPMENT.md` | Dev setup, project structure, the CI gates and repository hygiene |
| `RELEASE_RUNBOOK.md` | Branch, required checks, fast-forward, tag and publish; no export or snapshot |
| `AI_CONTRIBUTION_POLICY.md` | How AI-assisted contributions are reviewed here |

## Where the pictures live

`docs/media/` holds the demo clips and the mark the README renders; `docs/screenshots/` holds
the three README captures, with `screenshots/PROVENANCE.md` naming the surface each one
documents and when it has to be re-shot.

## Decisions

The record behind the `(owner decision 2026-10-08)` lines the agent files and the comments carry.
Each page keeps the decision as it was taken; where the tree has moved since, the move is named at
the decision instead of folded into its text.

| File | Content |
|---|---|
| `decisions/owner-decisions.md` | The dated ledger of owner decisions the provenance lines point at |
| `decisions/workspace-authority.md` | Why one authority decides the workspace root |
| `decisions/PLUGIN_SURFACE_PAGE_STORAGE.md` | The page-storage shim a plugin surface gets, with the two options it rejected |
| `decisions/ci-capacity-and-runners.md` | Why the fork guard lives in the workflows, what the two runner lanes are, what one push costs and what the plan refuses |
