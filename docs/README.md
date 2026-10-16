# docs/ — the index

Engineering documentation, audits, and design notes for Ephe. Every file here is
one of three things: product documentation, a dated audit trail, or a working
plan. Nothing here is required to run Ephe — the install guide is `INSTALL.md`
and the project overview lives in the [root README](../README.md).

## Get started

| File | Content |
|---|---|
| `INSTALL.md` | Install guide, referenced from the root README |
| `SWITCHING.md` | Import an existing local-agent setup into Ephe |
| `CLI.md` | `ephe` command reference |
| `CLI_ROADMAP.md` | Roadmap to a world-class CLI |
| `VOICE.md` | Offline voice loop (Piper TTS target) |
| `LOCAL_IMAGE_ENGINE.md` | Free local image generation |
| `FEATURE_INVENTORY.md` | Inventory of interactive UI elements (wave W1) |
| `EPHE_VISION_2026.md` | Product vision |
| `EPHEMERIDES.md` | The Ephemerides |
| `AT_A_GLANCE.md` | Figures, installation matrix, feature parity and the case for Ephe (carried from the README front page) |
| `FEATURE_STATUS.md` | Feature status with its known limits |
| `SKILLS.md` | The built-in skill packs and the artifact tools they route to |
| `PLUGINS_OVERVIEW.md` | First-party plugin bundles; the manifest format itself is `PLUGINS.md` |
| `BENCHMARKS.md` | Benchmark rounds, the pass³ mapping and the published figures |
| `INSTALL_OPTIONS.md` | Install paths, requirements, Docker and the uninstall flags (with `INSTALL.md`) |
| `MOBILE.md` | Phone pairing over the LAN, the QR walkthrough and the public-access rule |
| `TELEGRAM.md` | The Telegram channel: gateway status, pairing and the hardening it runs on |
| `SECURITY_AND_PRIVACY.md` | The security and privacy mechanisms in one table |
| `DEVELOPMENT.md` | Dev setup, project structure, CI gates and repository hygiene |
| `DEMOS.md` | The demo GIF clips |

## Architecture & internals

| File | Content |
|---|---|
| `ARCHITECTURE.md` | Module map and status, 2026-10-11 |
| `CORE_ANALYSIS_REPORT.md` | Core backend and deployment status analysis |
| `SPLIT_TOOLS_CORE.md` | Split plan for the four >400-line core files |
| `TASK_LIST_TDD.md` | TDD backlog |

## Engine, memory & routing

| File | Content |
|---|---|
| `EPHE_DECISION_LAYER_2026-10-10.md` | The decision layer, measured against the products it resembles |
| `HYBRID_ROUTER_DESIGN_2026-10-11.md` | Hybrid router: small local models for the loop (F4) |
| `MODEL_ROUTER_TIER_TAGS.md` | Router tier tags and their validation |
| `routing-design.md` | Routing design for multi-file arithmetic (bench G2/G4) |
| `MODALITY_CONDUCTOR_2026-10-11.md` | Modality conductor (F3) |
| `MEMORY_KEPTA_DESIGN.md` | Memory provider: Chroma facade and Kepta core |
| `MEMORY_GATE_AB_SPEC_2026-10-10.md` | Memory injection A/B spec |
| `ENGINE_TEXT_CENSUS_2026-10-10.md` | Count-only census of engine-facing text (wave 16) |
| `TOOL_ARRAY_COST_2026-10-10.md` | Tool-array cost of the named-tool coverage fix |
| `LATENCY_BUDGETS.md` | Latency budgets (R25) |
| `PERF_REGRESSION_2026-10-11.md` | Perf regression dashboard |
| `EPHEMERAL_PROOF_2026-10-11.md` | Ephemerality as proof (F1) |
| `EPHEMERAL_DEMO_2026-10-11.md` | One Cell through its whole life, run and recorded (`scripts/ephemeral_demo.py`) |

## Plugins, skills & extensions

| File | Content |
|---|---|
| `PLUGINS.md` | Plugin manifest format v1 spec |
| `PLUGIN_SDK.md` | Guide for plugin authors |
| `SKILL_PACKS.md` | Skill packs (R16) |
| `EXTENSIONS_DESIGN.md` | Extensions 1.0 design doc (waves E1-E6) |
| `EXTENSIONS_PRFAQ.md` | Extensions 1.0 PR/FAQ |
| `EXTENSIONS_V2_PLAN.md` | Extensions v2: plugin portfolio, MCP marketplace, enterprise tier |
| `PERSONA_PACKS.md` | Persona packs: versioned markdown bundles behind `~/.ephe/persona.md` |

## Security & boundaries

| File | Content |
|---|---|
| `SECURITY_THREAT_MODEL.md` | STRIDE threat model |
| `SECURITY_GATE_REPORT.md` | Security release gate report (P0-3) |
| `SANDBOX_EXECUTION.md` | Ephemora cell sandbox (opt-in) |
| `HOST_EXEC_BOUNDARY_REVIEW_2026-10-11.md` | Host execution boundary: run_shell, docker backend |
| `REWARD_BOUNDARY_2026-10-11.md` | Reward boundary and its owner ruling |
| `ENDPOINT_SURFACE_AND_GUARD_CENSUS_2026-10-09.md` | Endpoint surface and guard census |
| `ENGINE_ENDPOINT_AUTH_RUNBOOK.md` | Engine endpoint exposure and how to close it |
| `FAIL_CLOSED_PROVIDER_AUDIT.md` | Every path that fixes a model, against the no-silent-default rule (WH-51) |
| `AI_CONTRIBUTION_POLICY.md` | AI contribution policy: disclosure, rejection reasons, the CI gate |

## Benchmarks & evaluation

| File | Content |
|---|---|
| `benchmark-mapping.md` | TAU-bench / GAIA / SWE-bench / WebArena decision (Option B) |
| `BENCHMARK_GAP_2026-10-08.md` | Benchmark gap dossier against peers |
| `BENCH_RUNBOOK_2026-10-10.md` | Fresh 60x3 baseline runbook |
| `SUITE_PASS3_2026-10-10.md` | Suite pass^3 measurement |
| `SUITE_SIGNIFICANCE_2026-10-10.md` | How big the matrix must be before "we are better" is a number |
| `JUDGE_EVAL_2026-10-11.md` | The rubric judge (reflexion reviewer) scored against human labels: precision/recall |
| `T14_JOIN_2026-10-11.md` | The one loser in the 60x3 cohort |
| `WAVE16_TEXT_BENCH_2026-10-11.md` | Wave 16 text axis against the frozen baseline |
| `HARNESS_LAB_RRSI_DESIGN.md` | Harness Lab: regularised self-improvement of the harness |
| `REPO_VERIFY_DESIGN_2026-10-10.md` | repo-verify held-out repository environment |
| `CODING_AGENT_BUILD_2026-10-11.md` | Coding agent build (C1) |
| `CODING_AGENT_VS_PI_DESIGN.md` | Coding agent versus pi: measurement and capability design |
| `EPHE_AGENT_PLAN_2026-09-07.md` | Coding-agent plan, 2026-09-07 |
| `RSS_PROFILE_1000_2026-10-11.md` | Server RSS across a 1000-turn session, sampled |
| `BENCH_PUBLICATION_2026-10-11.md` | The Option-B harness publication: Ephe scored end to end on the fixed matrix |
| `ENDSTATE_EVAL_2026-10-11.md` | End-state eval over the containerised stack (W3-78) |
| `ERROR_ANALYSIS_W3_2026-10-11.md` | Failure labels across the bench cohort (W3-77) |
| `FRONTEND_COVERAGE_2026-10-11.md` | Frontend test coverage of `app/src` (W3-3) |

## CI, release & gates

| File | Content |
|---|---|
| `CI_EXPANSION_2026-10-10.md` | CI expansion from 6 workflows to full process coverage |
| `CI_CAPACITY_RUNNER_DECISION_2026-10-09.md` | Runner decision after hosted minutes ran out |
| `CI_HYBRID_CAPACITY_2026-10-11.md` | CI hybrid capacity, measured per host |
| `CI_CLEAN_ROOM_2026-10-11.md` | Clean-room install |
| `DEPENDABOT_TRIAGE_2026-10-09.md` | Dependabot triage |
| `DEPENDENCY_LOCK_PATH_2026-10-11.md` | How a constraint change becomes a lock change |
| `RELEASE_CHECKLIST.md` | Release checklist (R25) |
| `RELEASE_RUNBOOK.md` | Release runbook |
| `RELEASE_READINESS_2026-10-10.md` | Release readiness, counted |
| `SOAK_GATE_2026-10-11.md` | The endurance window the release gate cannot see into |
| `STARTUP_GATE_LOAD_ROBUST_2026-10-11.md` | Load-robust startup decision |
| `EVIDENCE_DURABILITY_2026-10-11.md` | Keeping a fourfold number from quietly becoming two |
| `VALUE_OWNERSHIP_CONVENTION_2026-10-11.md` | A test asserts a contract of an owned value, never its current literal (W3-64) |
| `LINUX_SHAPE_PROBE_2026-10-10.md` | Reproducing Linux-only test shapes on a Mac |
| `THIRD_SHAPE_PROBE_2026-10-11.md` | Third-shape probe |
| `CHANGELOG_AUTOMATION.md` | Keeping the `[Unreleased]` block current from commit subjects |
| `SUPPLY_CHAIN_FLOOR_REVERIFY_2026-10-11.md` | Advisory floors re-verified against the published fix versions and the lock |
| `RELEASE_SIGNING_DRY_RUN_2026-10-11.md` | What a signed local release produces, and which steps are owner-only |
| `CI_CAPACITY_REFRESH_2026-10-11.md` | What one push costs, read from the Actions API |
| `INSTALL_VERIFY_2026-10-11.md` | The one-command installer verified on clean machines |
| `FLAKE_HUNT_ORDER_DEPENDENCE_2026-10-11.md` | Tests whose verdict depends on which other test ran first |
| `OPS_RUNBOOK_2026-10-11.md` | What to do when a CI leg goes red |
| `REBRAND_RESIDUE_2026-10-11.md` | The retired names still present in the tree (W3-11) |
| `ATTRIBUTION_REPORT_2026-10-11.md` | The author register measured against commit history (W3-83) |

## Language & prose quality

| File | Content |
|---|---|
| `LANGUAGE_SWEEP_RULEBOOK.md` | Worker rulebook for the language sweep |
| `ENGLISH_FIRST_AUDIT_2026-10-11.md` | Hardcoded German in string literals |
| `GERMAN_LITERALS_2026-10-08.md` | German string-literal inventory |
| `SERVER_SURFACE_LANGUAGE_DECISION_2026-10-09.md` | Server surface language decision |
| `PLURALIZATION_READINESS_2026-10-11.md` | Count-based strings and plural readiness |
| `PROSE_TELLS_2026-10-09.md` | Census of prose tells |
| `I18N_RTL_READINESS_2026-10-11.md` | RTL readiness and locale file weight |

## UI & UX

| File | Content |
|---|---|
| `PWA-CHAT-UX-PLAN.md` | PWA chat UX: AI-client style streaming (canonical plan) |
| `UX-PLAN-DESKTOP-CHAT.md` | Desktop chat UX/UI design plan |
| `UX_DESKTOP_DESIGN_PLAN.md` | Desktop UX design plan |
| `UX_DESKTOP_REDESIGN_PLAN.md` | Consolidated and refreshed desktop redesign plan |
| `UI_3X_RESEARCH_2026-10-10.md` | UI 3x research dossier |
| `UI_4X_PROGRAM_2026-10-11.md` | UI 4x programme |
| `UI_STATE_INVENTORY_2026-10-11.md` | UI state inventory for wave 6 |
| `COMPOSER_MODES.md` | Composer modes SSoT matrix |
| `COMPOSER_MOBILE.md` | Composer mobile layout contract (breakpoints below lg) |
| `SHELL_PLAN.md` | App shell rollout and plugin icon system |
| `schwarzwald-landing-plan.md` | Schwarzwald landing page redesign plan |
| `ARTIFACTS_PAGE_SCREENSHOTS_2026-10-11.md` | Browser receipts for the artifacts page (WD-27), each capture beside its DOM facts |
| `MOBILE_390_RECEIPTS_2026-10-11.md` | Real 390x844 captures of every main screen |

## Planning, roadmaps & decisions

| File | Content |
|---|---|
| `ROADMAP.md` | Roadmap R15-R25 |
| `ROADMAP_R6-R9.md` | Roadmap rounds 6-9 |
| `ROADMAP_R27-R36.md` | Roadmap R27-R36 |
| `EXECUTION_PLAN.md` | Execution plan |
| `BUILD_PLAN_2026-10-10.md` | Build plan for executors who were not in the conversation |
| `EPHE_REDESIGN_PLAN_2026-10-04.md` | Redesign plan, 2026-10-04 |
| `EPHE_PLAN_R2_2026-10-05.md` | Replan R2 |
| `EPHE_PLAN_R3_2026-10-06.md` | Replan R3 |
| `EPHE_PLAN_R4_2026-10-06.md` | Replan R4 |
| `PLAN_GAP_2026-10-11.md` | CLI_ROADMAP + EPHE_PLAN_R4 against the tree |
| `PLAN_SURFACE_2026-10-11.md` | Plan surface and produced output |
| `DECISIONS_2026-10-10.md` | Decision register |
| `OWNER_DECISIONS_2026-10-11.md` | Ten items that can be ruled in one sitting |
| `ENDSTATE_DELTA_2026-10-10.md` | Endstate delta |
| `CO_AUTHOR_LANES_2026-10-11.md` | Lane plan for a second author |
| `AGENT_PANEL_CONDUCT_2026-10-11.md` | Agent panel conduct |
| `ROADMAP_W4_2026-10-11.md` | Wave 4 roadmap: the ranked input the launch wave works from |

## Launch & positioning

| File | Content |
|---|---|
| `LAUNCH_PLAYBOOK.md` | Open-source launch playbook |
| `PRFAQ_EPHE_LAUNCH_2026-10-11.md` | Launch-train PR/FAQ |
| `whitepaper-ephe.md` | Ephe whitepaper |
| `document-quality-roadmap.md` | Roadmap to NotebookLM-level PDF, slide and infographic output |
| `BRAND.md` | Brand (working backwards) |
| `AUDIT_COMPETITIVE_ANALYSIS.md` | Full audit and comparative analysis against the reference clients |
| `SHOW_HN_2026-10-11.md` | Show-HN draft, maker comment and FAQ |
| `POSITIONING_2026-10-11.md` | The positioning sentence and the evidence under it |
| `SOCIAL_PREVIEW_2026-10-11.md` | The share card and the Open Graph tags that point at it |
| `LAUNCH_GATE_2026-10-11.md` | The launch gate: every row with its receipt |
| `LAUNCH_ASSETS_2026-10-11.md` | Launch asset inventory with each capture |
| `LAUNCH_DECISION_2026-10-11.md` | The two owner-gated launch decisions (notarization, the public flip) |

## Audits (dated snapshots)

| File | Content |
|---|---|
| `CAPABILITY_AUDIT_2026-09-07.md` | Capability audit |
| `COVERAGE_GAPS_2026-10-11.md` | Ranked coverage gaps |
| `POSTMORTEM_W2_INDEX_2026-10-11.md` | Wave-2 postmortem index |
| `CLAIM_AUDIT_2026-10-11.md` | The launch claims, attacked before the public does |
| `WAVE4_EXIT_2026-10-11.md` | The wave's exit bar, measured |
| `DEEP_DIVE_AUDIT_2026-09-07.md` | Deep-dive UI/UX audit |
| `FEATURE_PARITY_AUDIT_2026-09-04.md` | Feature-parity audit against the reference clients |
| `FEATURE_PARITY_2026-09-07.md` | Complete side-by-side parity comparison |
| `findings.md` | Ten-persona live audit |
| `POWERUSER_AUDIT_2026-09-05.md` | Power-user audit |
| `QA_FIRST_RUN_2026-09-04.md` | First-user QA report |
| `STRESS_1000_2026-09-06.md` | 1000-message sustained stress campaign |
| `skill-tool-audit-2026-09-13.md` | Skill and tool output-quality audit |
| `UX_PERSONA_AUDIT_2026-10-10.md` | Persona UX audit |
| `UX_ROLES_REVIEW_2026-09-05.md` | UX role review and load analysis |
| `VOLL_AUDIT_FINISH_GATE_2026-09-18.md` | Full audit finish gate (waves 2-4) |
| `UNBACKED_CLAIMS_2026-10-10.md` | Unbacked surface claims, re-measured |
| `RESEARCH_ADOPTION_2026-10-09.md` | Research adoption dossier |
| `RESEARCH_TARGETED_2026-10-10.md` | Targeted research, five blocks |
| `EU_EVIDENCE_SURFACE_2026-10-11.md` | EU evidence surface design doc |
| `QUICKSTART_VERIFICATION_2026-10-11.md` | The README install and run paths, executed end to end |

## Media & assets

| Path | Content |
|---|---|
| `screenshots/` | README hero image, desktop and mobile shots |
| `media/` | The README demo GIFs, the 1200x630 social preview card, plus a local-only QA screenshot dump (gitignored) |
| `demo/` | Short screen recordings (webp) |
| `mockups/` | Early UI concept mockups |
| `brand/` | Logo master and candidate marks |
| `concept/` | Working-backwards concept documents |
| `superpowers/` | Plans and ledger entries from an earlier workstream |

`gen_pdf.py` and `generate_whitepaper.py` are the Playwright renderers behind
`whitepaper-ephe.md`. `NOTES.md` holds ad-hoc operational notes.

## Conventions

- Audit files are dated `YYYY-MM-DD` and never edited after the fact; follow-ups
  live in new files.
- English-first for code, comments, docs, and engine prompts. German appears only
  in the app locale files (`app/src/de.json`, `en.json`) and deliberately German
  content files.
- Demo/GIF regeneration: `scripts/create_demo_media.py` keeps the README-referenced
  clip names stable.
