# Ephe agent instructions

This is the hub. A directory with its own `AGENTS.md` adds to these rules, and the table under
[Areas](#areas) says which one applies. A checkout may carry `AGENTS.override.md` beside this file:
personal notes, gitignored, never committed, not part of the repository's own instruction set.

## What Ephe Is

Ephe is a local-first AI workbench: a Python product server, the React PWA it serves, a terminal app, and a Tauri shell around the same PWA.
A turn runs against the engine the user chose, and nothing leaves the machine unless that choice names a remote endpoint.
There is no account and no credential in the tree, and the PWA and the desktop app are equal surfaces.

## Invariants

### No silent engine default

Ephe starts only with a persisted `~/.ephe/engine.json` (written by `ephe configure`) or an explicit
`EPHE_MODEL_PROVIDER` plus its endpoint. Without one of the two the server starts in setup mode with
the chat closed, the terminal app opens its own provider setup, and the headless verbs stop with an
actionable hint. A remote provider named without an endpoint counts as no choice (owner decision
2026-10-29). Ollama and any OpenAI-compatible endpoint are first-class; which model tag runs is the
user's choice, and the product never picks one. The access token comes from
`EPHE_OPENAI_COMPAT_API_KEY`, Ephe's own keychain entry, or the user's `~/.ephe/engine.key`
(owner-only, one line), and from no other program's credential store (owner decision 2026-10-10).
The one named exception is the onboarding `/models` probe
(`core/model_probe.py::resolve_probe_key`): it may authenticate a reachability check with a key it
found beside Ephe, never a chat turn, and it has to report `key_source: "foreign"` instead of letting
"reachable" stand as if the user's own key answered (owner decision 2026-10-18).

### English in the tree, German only in the product surface

Commit messages, code, comments, docstrings, docs, script and CLI output, log lines, identifiers and
the text the engine is instructed with are English. German lives in exactly the product's German
surface: `app/src/locales/de.json`, German-targeted skill packs, and deliberately German content such
as `knowledge/survival/*.md`. A refusal that reaches both the tool card and the model context is
English in code and German only behind its reason code in the locale bundle. Never translate German
product text during a sweep, and never let a fixture that carries it drift. Our artifacts carry our
own names: a third-party product name stays out of filenames, module paths, identifiers, setting keys
and commit messages, and appears in prose only as the cited prior art it is. The decision layer is
**Ephe Decision** (`core/decisions.py`), and a vendor is cited only where a number came from it.

### Writing quality

No generated-code tells: no docstring that restates its function name, no comment narrating the next
line, no `Note:`/`Important:` filler, no repeated banner headers, no decorative separators, no emoji,
no rhetorical turns stacked for effect, no adjectives about our own code. A comment earns its place
by stating a constraint, an invariant, a measurement or a workaround; one short line is the norm.
Provenance lines are allowed when a decision is not visible in the code (`owner decision 2026-10-08`)
and are not house style. A prose sweep stays line-neutral and does not reformat, reorder or rename
along the way. `scripts/prose_tells.py` holds the count against a baseline that only ever lowers.

### Both surfaces ship

The PWA (`app/src`, built into `app/dist`) and the Tauri desktop app (`app/src-tauri`) are equal
product surfaces. A wave is done only when both build and run from the latest sources. A `src/` edit
stays invisible to the product server until `pnpm run build` runs in `app/`; a `src-tauri/` change
needs a release build (`npm run tauri build` in `app/`, or `ephe desktop`) and one launch of the
resulting `.app`, because the shell bundles `app/dist/` through `frontendDist` and a stale binary
ships old UI. The desktop build rebuilds the PWA through `beforeBuildCommand`, so it covers both
halves. Root-PWA changes also get a desktop and a mobile visual check.

## Commands

```bash
make verify          # pytest, vitest, the production build and the agent check
make test            # the two suites without the type check
.venv/bin/python -m pytest tests/ -q -p no:cacheprovider
cd app && pnpm exec vitest run
pnpm run build       # in app/: type check and production build into app/dist
cd app && pnpm exec playwright test -c tests/playwright/playwright.config.ts
cargo test --manifest-path app/src-tauri/Cargo.toml
```

The gates, run before a pull request:

```bash
python scripts/language_gate.py
python scripts/prose_tells.py
python scripts/readme_check.py --root .
cd app && python scripts/bundle_budget.py dist   # needs pnpm run build first
```

Each gate reads this checkout only: the budget gate needs `pnpm run build` first, the other three
need no service. Start narrow: read the failing test, run that file, then widen. Search with `rg`,
never with a recursive `grep`.

## Structure

- `core/` — engine adapters, tools, memory, skills and decisions; `server/` imports it and
  never the reverse.
- `server/` — the FastAPI app and its routes; the product server on `:8765` also serves `app/dist`.
- `app/` — the React PWA; the Tauri shell lives in `app/src-tauri/`.
- `plugins/` — first-party plugin bundles (`ephe-plugin.json`, sha256-hashed).
- `evals/` — offline evaluation harnesses and their manifests.
- `scripts/` — gates, generators and benchmarks; CI and contributors call the same files.
- `docs/` — policies, architecture and runbooks.
- `tests/` — the pytest suite the gates run.

## Areas

| Path | File | Read it when |
|---|---|---|
| `app/` | [`app/AGENTS.md`](app/AGENTS.md) | adding a component, route, hook or locale key |
| `app/src-tauri/` | [`app/src-tauri/AGENTS.md`](app/src-tauri/AGENTS.md) | touching the shell, readiness, updater or bundle |
| `server/` | [`server/AGENTS.md`](server/AGENTS.md) | adding or changing a route, refusal or guard |
| `tests/` | [`tests/AGENTS.md`](tests/AGENTS.md) | adding, moving or debugging a test |
| `.github/` | [`.github/AGENTS.md`](.github/AGENTS.md) | editing a workflow or release automation |

## Rules that apply everywhere

- **Attribution.** A commit's author and committer addresses come from `.github/identities.json` and
  are the GitHub noreply form (`<account-id>+<login>@users.noreply.github.com`).
  `scripts/attribution_check.py` refuses a bare mailbox, because a domain this project does not hold
  is a claim anyone can acquire later. Set it once per machine with
  `git config --global user.email <account-id>+<login>@users.noreply.github.com`; never copy an
  employer or retired-brand address into `user.email`.
- **Hooks stay on.** No `--no-verify` and no `core.hooksPath` shortcut: the hook runs the same checks
  CI runs, and a skipped hook is how a rule reaches main broken.
- **Both surfaces.** A change under `app/src` or `app/src-tauri` ends with both builds recorded in the
  report. A report that names one build and assumes the other is not a report.
- **One home per fact.** Documentation is linked, never copied. If a rule already has a document, the
  agent files point at it; a second copy is the version that goes stale.
- **Inspect before editing.** `git status --short` first, then read the code you are about to change.
  Keep the edit focused and leave unrelated local changes alone.
- **One-command install.** `install.sh` and `install.ps1` are first-class product surfaces; a change
  that breaks the install path blocks a release.
- **Optional integrations stay opt-in.** Custom Ollama, public mobile access, web search, TTS APIs
  and OpenAI-compatible endpoints are optional paths, and the README and the UI label them that way.
- **A recorded number names its engine.** Verification does not run on a local Ollama model (owner
  decision 2026-10-11): bench, endstate and browser proofs use the engine from `ephe configure`, and
  every number we publish says which engine produced it.
- **Generated media.** A generated image enters the tree only when a committed document names, for
  that file, the surface it targets and the decision it is evidence for. It is reference only and
  carries no layout, icon, glyph, wordmark, control or spacing decision. Every mark, icon and
  screenshot comes from the product: the vector generator for the marks, a capture of the built app
  for a screenshot.
- **Public copy.** Company, CEO, CTO, crisis-team and "Zero Human" positioning stays out of the
  README and the UI.

## Boundaries

Ask before:

- adding a dependency, an engine class or a new `/api/*` route (the contract freeze in
  `tests/test_w3_68_api_contract_frozen.py` must move in the same patch);
- changing a security default: server binding, CORS, mobile pairing, tool approval;
- raising or lowering a gate baseline, a bundle budget or a coverage floor;
- touching a version carrier outside a release bump.

Never:

- commit a secret: `~/.ephe/engine.key`, a token, a `.env` value, a signing key. Presets are
  templates (`engine.example.json`, `.env.example`), and no hostname or endpoint is hardcoded;
- commit `node_modules`, `app/dist`, `app/src-tauri/target`, a local database or its WAL/SHM
  sidecars, a cache, a log, or a generated image no committed document names;
- add an engine default, a hidden fallback or a provider the user did not choose;
- edit `pyproject.toml`, `app/package.json`, `app/src-tauri/tauri.conf.json` or
  `app/src-tauri/Cargo.toml` version fields by hand. A version moves through the release bump, and
  the tag is cut from `main`.

## Further reading

- [`docs/AI_CONTRIBUTION_POLICY.md`](docs/AI_CONTRIBUTION_POLICY.md) — what a contribution discloses
  and which check enforces each rule.
- [`docs/RELEASE_POLICY.md`](docs/RELEASE_POLICY.md) — what earns a tag and what ships rolling.
- [`.github/RELEASE_PROCESS.md`](.github/RELEASE_PROCESS.md) — the release runbook.
- [`docs/CONTEXT_CONTRACT.md`](docs/CONTEXT_CONTRACT.md) — what enters model context, in which order
  and under which caps.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — module boundaries and the import rules behind them.
