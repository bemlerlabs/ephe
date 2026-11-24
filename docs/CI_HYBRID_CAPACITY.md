# The scheduled legs, and which lane they actually run on

Seven workflow headers point here for "Wave I" or "Wave II" of a capacity plan. What the two lanes
mean, what one push costs and why a fork never reaches a runner this project controls lives in
[`decisions/ci-capacity-and-runners.md`](decisions/ci-capacity-and-runners.md); this page does not
restate those facts, it records what each leg enforces and what the lane state measured on 2026-11-24
actually is.

## The legs, their cadence and their instrument

Read out of the workflow files on 2026-11-24. Every Linux job here carries
`runs-on: ${{ vars.CI_LINUX_RUNNER || 'ubuntu-latest' }}`, so the repository variable is the only
thing that could move one to a runner this machine hosts.

| workflow | fires on | runs | what it refuses |
|---|---|---|---|
| `hygiene.yml` | push, pull_request | `scripts/hygiene_check.py`, `scripts/tauri_parity.py`, `scripts/attribution_check.py` | case collisions, a tracked artifact, a Tauri plugin missing from the parity list, a new commit whose author or committer address is not registered |
| `lint.yml` | push, pull_request | `scripts/lint_policy.sh` plus `scripts/ci_local.sh` | ruff's blocking subset over the whole tree; ruff's advisory set and mypy over the files the change touched |
| `lockfile.yml` | `30 3 * * *`, dispatch | `scripts/lockfile_check.py`, `uv sync --frozen`, `pnpm install --frozen-lockfile` | a manifest that no longer agrees with `uv.lock` or `pnpm-lock.yaml`, a pnpm pin that drifted, a merge that moved the lock without saying so |
| `docklint.yml` | `0 3 * * *` | `hadolint`, `shellcheck`, `scripts/docker_lint.py` | a container or shell finding above the recorded ceiling; the tools are resolved through `checksums.sh` rather than pulled unpinned |
| `timing.yml` | `30 2 * * *`, dispatch | `scripts/ci_preflight.sh`, `scripts/ci_timing_report.py` | a distribution whose budget broke, a leg named in the budget file that no longer exists |
| `catalog-freshness.yml` | `1 4 * * *`, dispatch | `scripts/catalog_freshness.py`, `scripts/generate_plugin_catalog.py` | a committed `skills-lock.json`, `plugin-catalog.json` or `marketplace/index.json` that is not what its sources generate |
| `asset-checks.yml` | `30 4 * * *`, dispatch | `scripts/asset_check.py` | a broken reference in the shipped surface, a missing header, an icon that fails the 16 px proof |

Five of the seven are scheduled or dispatch-only: they are not required checks, so a red one does not
stop a merge and nobody is paged. Two (`hygiene.yml`, `lint.yml`) gate every push and pull request.

## The lane state, measured 2026-11-24

Taken on this machine with the `gh` CLI against `bemlerlabs/ephe` at 00:53 +01:00:

```bash
gh api repos/bemlerlabs/ephe/actions/runners --jq '.total_count'      # 0
gh api repos/bemlerlabs/ephe/actions/variables --jq '.variables | length'   # 0
pgrep -fl 'config.sh|runsvc|run.sh'      # nothing
ls -d ~/actions-runner                   # absent
```

No runner is registered, no repository variable is set, and no runner process exists on this machine.
`CI_LINUX_RUNNER` therefore resolves to nothing for every leg, so **the workshop lane is not in
operation**: any job that ran ran on a GitHub-hosted runner, because there is no other runner it
could have been given. The decision behind that lane, and the cost of the hosted alternative, are in
the decision record linked above.

Whether the hosted lane is running is a separate question, measured separately. Between 2026-11-21 and
2026-11-24 the repository recorded 250 workflow runs. The scheduled legs did execute — the newest run
of `asset-checks.yml` (2026-11-23T15:10:37Z) concluded success with 11 steps — while the newest push
(`0405b51`, 2026-11-23T23:44:57Z) produced jobs that concluded failure or cancelled two to three
seconds after they started, with 0 steps recorded. A job that never reached a step ran nothing, so a
green scheduled leg and a red push at the same minute describe the account's Actions budget, not the
state of the code.

## The wave numbering the headers quote

`hygiene.yml` and `lint.yml` call themselves Wave I, the other five Wave II, and three of those quote
"rows 6 and 36", "rows 19 and 20", "rows 40 and 41" and "row 12" of a residue list. That numbering
came from a working list kept outside this repository, and the list is gone: a scan of the plan tree on
2026-11-24 (33 entries, searched for `hybrid`, `residue`, `wave`) found no such table, and `git log
--diff-filter=A` puts all seven files in `2942348` (2026-11-21, the initial public tree), so the tree
never carried the assignment either.

The wave words and row numbers stay in the headers as the names the citations already use. What a
reviewer needs from them — what each leg enforces and how often — is the table above, measured from
the files themselves. Nobody should read a row number as a reference to a document that exists.
