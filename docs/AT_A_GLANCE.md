# At a Glance

The figures the README quotes, each with the command that produced it. Every row was re-read on
2026-10-14 at commit `46122583`, from the build it describes.

| Metric | Measured |
|---|---|
| Agent tools (`TOOL_MAP`) | 73 |
| Built-in skill packs | 51 |
| First-party plugin bundles | 14 (manifest v1, sha256-hashed) |
| REST endpoints (OpenAPI) | 149 paths / 170 operations |
| Vitest unit tests | 2438 in 357 files |
| Pytest suite | 6799 collected |
| Playwright tests | 116 (static build) · 130 (dev dogfood) |

Each row is the reading of one command:

| Metric | Read with |
|---|---|
| Agent tools | `len(TOOL_MAP)` |
| Skill packs | `SkillLoader().load_all()` |
| REST endpoints | `create_app().openapi()` paths and operations |
| Vitest | `cd app && npx vitest run` |
| Pytest | `python3 -m pytest tests --collect-only -q` |
| Playwright | `npx playwright test --list` per config |

Three rows need their unit said out loud:

- The pytest row is a **collection** count. A pass total belongs to a run on a clean tree, and this
  table is not where a stale one should sit.
- The two Playwright figures are two configs over partly the same specs
  (`app/tests/playwright/playwright.config.ts` lists the static build,
  `app/tests/playwright/dogfood.config.ts` the dev-dogfood stack), so they are listed side by side
  and never added.
- The vitest row is read in `app/`, where the app's own vitest resolves. The root `vitest.config.ts`
  mirrors the same include set, and CI runs `cd app && pnpm exec vitest run`.

Six of the seven rows are **volatile** and move with the tree: the two test counts and the
Playwright figures grow with every test added, and `TOOL_MAP`, the OpenAPI paths/operations and the
skill-pack count move with every tool, route or skill that ships. The plugin-bundle row is the
stable one; it changes only when a bundle is added. A volatile row is the count at `46122583`, and
its command above is how to re-read it.

The release version has one home, `pyproject.toml` (`[project].version`). `core/_version.py` reads
it back, `ephe --version` prints it, and `tests/test_version_sync.py` pins the build carriers to
that file, so the README points at the source and no second copy of the number can drift.

## Installation Matrix

Measured on the clean-install path (`uv venv` + wheel install, CLI `--version` check), OS: macOS (Apple Silicon):

| Python | Ollama | OpenAI-compat (vLLM) |
|---|---|---|
| 3.11 | yes | yes |
| 3.12 | yes | yes |
| 3.13 | yes | yes |

6/6 combinations green on that host. CI is a wider grid and a different instrument: it builds four
interpreters (3.10, 3.11, 3.12, 3.13) on Linux for the pytest and integration legs, plus one macOS
3.12 leg. Read the workflow files for what runs on every push; this table is the clean-host reading.
`engine.example.json` is one template, the OpenAI-compatible one; the local-Ollama path is chosen by
`ephe configure` or by `EPHE_MODEL_PROVIDER=local_ollama`. Which start path really waits for that
choice, and which one does not yet, is spelled out in [CLI.md](CLI.md) under "Engine choice (no silent default)".

## Feature Parity

Measured against the two reference clients (anonymized per product policy); a state is **Present** or **Partial**. See [`FEATURE_PARITY_AUDIT_2026-09-04.md`](FEATURE_PARITY_AUDIT_2026-09-04.md) for the full audit trail.

| Gap | Area | State now |
|---|---|---|
| G1 | Terminal panel (shell output in UI) | Present — `ToolCallDisplay` streams shell output |
| G2 | Live preview pane next to chat | Present — Agent-panel `preview` tab (iframe) |
| G3 | Git integration (status/diff/commit) | Present — `git add` + `git commit` routes + panel tabs |
| G4 | Goal mode (plan → execute → verify) | Present — Ephe-Plan card with gate, budget `MAX_TOOL_ITERATIONS` |
| G5 | Bot channels (remote control) | Present — Telegram + Discord outbound adapters |
| G6 | Command-palette recents + key hints | Present — Recent sessions + shortcut badges |
| G7 | Per-task model routing | Partial — provider switch (single active model) |
| G8 | File/workspace browser in UI | Present — Agent-panel `files` tab |

| Property | What it means |
|---|---|
| Local by architecture | A local-first PWA and a FastAPI server on your machine. No account, no telemetry. Optional online features (web research, remote engines) are explicit opt-ins. |
| You pick the engine | Local Ollama, remote Ollama, or any OpenAI-compatible endpoint (DGX Spark, vLLM, SGLang). There is no silent default; until you choose, the app says so. |
| A learning loop that stays yours | 51 built-in skill packs with rubric and golden verification, deterministic skill routing onto real local artifact tools, a personal memory store, and full-text session search. |
| Approval-gated tools | Filesystem, shell, browser, and document tools behind a security profile you control (strict / session / plan / full). Writes need consent; Ask mode runs no tools at all. |
| Measured and reproducible | A reproducible agent benchmark (a 60-task matrix with a TAU/GAIA-inspired pass³ mapping) runs against the real streaming endpoint on every round, and every recorded number names the engine that produced it. |

## Why Use It

- **Local by default:** no account is required for the default local path.
- **Clear online boundaries:** web research, public phone access, API providers, and external TTS are labeled as opt-in.
- **Useful beyond chat:** images, files, PDFs, Excel/Word artifacts, memory, tasks, skills, and browser/tool workflows are exposed in one PWA.
- **Phone access without an app store:** scan a QR code to use the mobile PWA on the same network.
- **Repairable setup:** `ephe doctor` explains missing Ollama/model states and prints concrete recovery commands.
- **Memory that is not locked in:** export/import in Settings, plus `ephe memory-mcp` — another MCP agent can read one workspace's memory over stdio, and writes only happen if you start the server with `--allow-write`.
