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
| `SECURITY_THREAT_MODEL.md` | STRIDE threat model, including the engine-token paths |
| `SANDBOX_EXECUTION.md` | The Ephemora cell sandbox (opt-in) |
| `COMPOSER_MODES.md` | The four response modes, the header control and what each mode sends |
| `COMPOSER_MOBILE.md` | The composer's mobile lane and its measured floors |
| `EPHEMERIDES.md` | The Ephemerides |
| `PERSONA_PACKS.md` | Persona packs: versioned markdown bundles behind `~/.ephe/persona.md` |
| `SKILLS.md` | The built-in skill packs and the artifact tools they route to |
| `SKILL_PACKS.md` | How a skill pack is put together |

## Extending

| File | Content |
|---|---|
| `PLUGINS_OVERVIEW.md` | The first-party plugin bundles |
| `PLUGINS.md` | The plugin manifest format, v1 and v2 |
| `PLUGIN_SDK.md` | Guide for plugin authors |
| `PLUGIN_PRACTICES.md` | Patterns a bundle follows once it ships |
| `PLUGIN_EXPORT.md` | How a made bundle is packed, signed, and checked against an installed identity, and where the lockfile is written |
| `DISCOVER_MARKETPLACE_DESIGN.md` | The design for the Discover shelf (not shipped) |

## Measurement and project

| File | Content |
|---|---|
| `BENCHMARKS.md` | The published figures and how they are produced |
| `PERFORMANCE_BASELINE.md` | Measured start-up and window-memory numbers, with the commands that take them |
| `benchmark-mapping.md` | Why Ephe measures its own harness instead of attaching to an external suite |
| `DEMOS.md` | The demo clips and how they were captured |
| `DEVELOPMENT.md` | Dev setup, project structure, the CI gates and repository hygiene |
| `RELEASE_RUNBOOK.md` | Branch, required checks, fast-forward, tag and publish; no export or snapshot |
| `AI_CONTRIBUTION_POLICY.md` | How AI-assisted contributions are reviewed here |

## Where the pictures live

`docs/media/` holds the demo clips and the mark the README renders; `docs/screenshots/` holds
the three README captures, with `PROVENANCE.md` naming the surface each one documents and when
it has to be re-shot.
