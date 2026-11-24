# Development

Set up the backend in a venv (Python 3.11 or newer; `.python-version` pins the 3.13 series):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run the app locally:

```bash
python run_server.py
```

## Frontend (PWA, `app/`)

The root PWA is the main product: React 19 + Vite 6 + TypeScript + Tailwind. The product server on
`:8765` serves the static `app/dist/`, so a `src/` edit stays invisible until `pnpm build` runs in
`app/` (hard-reload with Cmd+Shift+R afterwards); the dev server on `:5173` compiles from `src/`
live and needs no rebuild.

```bash
cd app
pnpm install --frozen-lockfile   # or: corepack enable && pnpm install
pnpm dev     # Vite dev server
pnpm build   # tsc -b && vite build (type-check + production build)
pnpm preview # Vite preview
```

Frontend unit tests use Vitest (`pnpm test`); Playwright specs live in `app/tests/playwright/`.

## Demo videos

The tree publishes no recorded clips; [`DEMOS.md`](DEMOS.md) lists what a reader can look at
instead. A clip is made by the recorder that lives in this tree — `scripts/record_demo.py`,
not a maintainer-only tool kept outside it. It drives Playwright's `record_video` against the
built app the product server serves on `:8765`, films the cases `chat`, `shell`, `help` and
`edit`, and converts each recording to an animated WebP with ffmpeg, into `/tmp/ephe_demo`.
It needs ffmpeg on `PATH` (or `EPHE_FFMPEG_BIN`) and a cached Playwright Chromium (or
`EPHE_CHROME_BIN`), and it says so and stops when either is missing. Running it puts nothing
in the repository: a generated image enters the tree only when a committed document names,
for that file, the surface it targets and the decision it is evidence for.

## Project Structure

```text
app/                React + Vite + TS PWA (main product), Tauri shell in app/src-tauri/
app/tests/playwright/  Playwright specs (frontend, CI-validated)
core/               Python core: chat, tools, vision, memory, skills, scheduler, profile
server/             FastAPI server + routes (chat, memory, mobile, tasks, vision, ...)
ui/                 Textual TUI / text UI
docs/               design docs, mockups, screenshots, demo media
scripts/            dev/demo/eval helpers
skills/             built-in skill markdown (prompts, rubrics, examples)
plugins/            first-party plugin bundles (ephe-plugin.json manifests, sha256-hashed)
knowledge/          offline knowledge base (German survival/medical/engineering)
.github/workflows/  CI: tests.yml (pytest subset + integration + docker) + frontend-build.yml + release.yml (tagged builds) + bench-trend.yml (dispatch-only pass³ trend)
install.sh          one-command installer (macOS/Linux)
install.ps1         one-command installer (Windows PowerShell)
uninstall.sh        removes the checkout and ~/.ephe (--dry-run, --keep-data)
```

## Testing

Quality gates run in CI on every push and pull request:

| Workflow | What it runs |
|---|---|
| `tests.yml` — pytest | the tracked offline test subset (repo hygiene, security guards, routes, engine defaults) across Python 3.11–3.13 |
| `tests.yml` — integration | package import integrity, installer syntax (bash + PowerShell), security-default audit (conservative server binding), Docker image build |
| `frontend-build.yml` | TypeScript type check, Vite production build, ESLint |

The full local test suite is maintainer-side and is run with `pytest tests/ -q` before release.
Contributors validate their changes with the checks listed in [CONTRIBUTING.md](../CONTRIBUTING.md).

## Repository Hygiene

Tracked files should not include generated dependency folders, local databases, WAL/SHM sidecars, secrets, caches, or generated media frames. Final README media files in `docs/media/` are intentionally tracked.

## Commit pointers and the public history

This repository's published history begins with the snapshot this tree ships. Work that predates it,
and work that never merged, lives in the owner's private archive. A clone of this repository cannot
open those commits: `git show <sha>` answers `unknown revision`.

A pointer to such a commit therefore names the tree a number was measured on, not something the reader
can fetch. Two rules follow, and `tests/test_commit_pointers.py` holds them:

- The sentence carries the substance. A figure cited from a tree nobody can open has to be readable
  without the tree: what was measured, when, and on which engine or input. A pointer that only says
  "see this commit" is not a citation.
- A citation that does not resolve from `HEAD` is named in that test with one line of reason —
  pre-snapshot work, a branch that never merged, or a commit in somebody else's repository. The test
  fails an entry no file cites any more, so an allowance cannot outlive the pointer that earned it.

The test resolves shas against the checkout's own history, so its resolvable half runs where history
is present; a shallow CI checkout skips that half and says so, while the allowlist half runs
everywhere.
