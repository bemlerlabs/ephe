# Contributing to Ephe

Thank you for your interest in contributing. Ephe is built by [Bemler Labs](https://github.com/bemlerlabs/ephe) — external contributions are welcome as long as they align with our core principles:

> **Offline-first by default. Online integrations only by explicit opt-in.**

## Quick Start

```bash
git clone https://github.com/bemlerlabs/ephe.git
cd ephe
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Frontend (PWA). The package manager is pnpm, pinned by `packageManager` in `app/package.json`; `app/pnpm-lock.yaml` is the only lockfile:

```bash
cd app
pnpm install --frozen-lockfile
pnpm run dev      # Vite dev server
```

## Coding Standards

| Area | Standard |
|------|----------|
| **Python** | PEP 8, type hints everywhere, `async/await` consistently |
| **JavaScript/TypeScript** | ES2022+, TypeScript strict mode (PWA in `app/`) |
| **CSS** | Tailwind v4 (via `@tailwindcss/vite`) plus design tokens in `app/src/styles/globals.css`; no SCSS |
| **Commits** | [Conventional Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`, `docs:`, `test:`) |

### Commit attribution

Commits carry a registered GitHub noreply address
(`<account-id>+<login>@users.noreply.github.com`) in **both the author and committer fields**,
checked against `.github/identities.json`. A bare address is refused: it can later be claimed
by whoever registers that domain. Land changes with normal local commits pushed to the
existing branch; do not use the GitHub web merge, rebase or squash actions, because they
rewrite the author or committer field. A local merge must set `user.email`,
`GIT_AUTHOR_EMAIL` and `GIT_COMMITTER_EMAIL`. A commit that lands with a refused address is
fixed forward; this history is not rewritten.

## Validation

This repository runs the **CI quality gates** on every push to `main`/`develop` and every pull
request into `main`:

- **Tests** (`tests.yml`): the tracked pytest suite on three interpreters (3.11, 3.12, 3.13) on
  Linux and on a macOS 3.12 leg, plus **Integration checks** — package import integrity, installer
  syntax (bash + PowerShell), security-default audit (conservative server binding), Docker image build
- **Frontend build** (`frontend-build.yml`): TypeScript type check, vitest unit tests, Vite production
  build, ESLint
- **CI gates** (`ci-gates.yml`): workflow self-audit (zizmor) and the repository ratchets —
  architecture, language, prose (`scripts/architecture_check.mjs`, `scripts/language_gate.py`,
  `scripts/prose_tells.py`); the same file also runs weekly, so a rule cannot be broken by a
  dependency update alone
- **Supply-chain audit** (`supply-chain.yml`): advisory checks, triggered by the dependency files
  (`pyproject.toml`, `uv.lock`, `app/package.json`, `app/pnpm-lock.yaml`) rather than by every push
- **Release** (`release.yml`): only on a `v*` tag — the release-bar test gate, then the Tauri bundles
- **Bench trend** (`bench-trend.yml`): manual (`workflow_dispatch`) — the offline pass^3 trend over
  tracked manifests

> **Pull requests from a fork do not run CI.** The gates execute on a runner this project
> controls, and running a fork's code there is not acceptable; GitHub's fork-approval rule is
> not available here either. So fork PRs are skipped and reviewed by a maintainer by
> hand — open the PR, and ask for a manual run if you need one. Pushes and pull requests from a
> branch of this repository run normally.

Before opening a PR, verify locally:

```bash
# Backend: import integrity
python -c "import ephe; import ephe_cli; print('OK')"

# Installers: syntax
bash -n install.sh

# Frontend: type check + build
cd app && npx tsc --noEmit && pnpm run build
```

> **Note:** The Python suite is tracked here (`git ls-files tests` counted 572 paths on 2026-10-16)
> and CI runs it, so a change to it is reviewed like any other change. This repository is public,
> which is what lets the install one-liner in the README be fetched anonymously.

## Adding Features

### New Tool

1. Implement the function in `core/tools/<module>_tools.py` (async, type-annotated)
2. Register it in `TOOL_MAP` + the schema list in `core/tools/registry.py`
3. Update the README tool reference

### New API Endpoint

1. Create route in `server/routes/<name>.py`
2. Register in `server/main.py`
3. Update README API reference

### New Skill

Simply add a Markdown file to `skills/` — no Python required.

## Salvage: from bug report to credited fix

You do not need to write code to land in the release notes. The workflow
that credits community diagnoses:

1. **Diagnose an issue** — root cause, file, and a minimal reproduction
   beat a stack trace every time. Open it (or comment on an existing one).
2. **A maintainer salvages it** — turns the diagnosis into a fix PR, keeps
   your handle attached as `salvage #<issue> @you`.
3. **The next release notes credit you by name** in the campaign that
   closed your issue (see `.github/RELEASE_PROCESS.md`).

Issues labeled `good first issue` carry acceptance criteria and are
reserved for first-time contributors. If you want to take one, comment
"taking this" and it is yours for two weeks.

## Project Principles

| Do | Don't |
|----|-------|
| Local execution; the engine choice stays the user's | Add mandatory API keys or a silent engine default |
| Privacy by design | Add external analytics/telemetry |
| Async everywhere (no blocking calls in main thread) | Break cross-platform compatibility |
| Keep server binding conservative (127.0.0.1 default) | Bind to 0.0.0.0 without explicit opt-in |
| One reader per field, one code path per sentence | Ship a knob, string or endpoint nobody reads |

## Origin and disclosure

Ephe is written with AI tools in drafting and in review, and says so. The rule that makes that
claim worth something is a threshold, not a banner in the tree. The full policy — what must be
disclosed, what is rejected, and which CI gate enforces each rule — is
`docs/AI_CONTRIBUTION_POLICY.md`. In short:

- **Disclosure.** Release notes state the version was produced with tooling; individual commits
  carry no stamp. A pull request states in one line whether an AI tool drafted a substantial part
  of the change.
- **Understood is the bar.** Nothing lands that the responsible human cannot explain line by line,
  regardless of who or what wrote it. Unexplainable changes are rejected, not annotated.
- **Own voice.** Comments, messages and docs are terse and name the *reason* (a constraint, a
  number, a bug being guarded), never the intent of the change. No template prose, no placeholder
  text, no tool signatures in the tree.
- **Rejected on sight:** a field without a reader, a sentence the code does not hold, a test
  without an assertion, a fallback for a case that cannot occur.

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/my-feature`)
3. Run the local validation commands above
4. Commit with Conventional Commits
5. Open a Pull Request using our PR template

## License

Ephe ships under the [Business Source License 1.1](LICENSE) (BUSL-1.1), and a
contribution enters under those same terms: everyone who receives this repository
receives your contribution under BUSL-1.1.

You also grant Bemler Labs a perpetual, worldwide, non-exclusive, royalty-free,
irrevocable license to use, reproduce, modify, distribute, sublicense and relicense
your contribution, including under the commercial licenses this product is offered
with. That grant is what keeps those licenses offerable at all — without it, a single
contribution would bind every release that follows it. If you would rather not grant
it, open an issue with the idea instead of a pull request, and we will write the code
ourselves.

By opening a pull request you also confirm that you wrote the contribution or otherwise
have the right to submit it, and that no employer or third party holds rights in it that
would prevent the grant above. Sign your commits with `git commit -s`, which adds a
`Signed-off-by:` line under the Developer Certificate of Origin. That line is the record
that the confirmation was given; a promise made only in prose is one we cannot show.

*Ephe — Black Forest, Germany*
