# Workflows and release automation

Workflows, the repository gates and the release automation.

Applies on top of the root AGENTS.md.

## Actions are pinned

- Every `uses:` names a commit SHA, with the release in a trailing comment. A tag is mutable, so a
  pinned SHA is the only form the workflow audit and the supply-chain review accept, and Dependabot
  moves it.
- A job starts from `permissions: contents: read`. A scope it genuinely needs is added alone at the
  job, with the reason beside it.
- Every checkout sets `persist-credentials: false`, so a token does not stay in `.git/config` for the
  steps that follow.

## No hard network dependency at boot

- apt, rustup and browser downloads are best-effort. A bounded retry loop (two or three attempts)
  then a `::warning::` line and a skip or a fallback path: a runner image that lacks an optional
  package is not a broken change, and a red leg nobody can fix hides the next real one.
- A third call to the same host after two failed attempts spends runner time on the same outage.
  Say what was skipped and let the release job, which has the package it needs, remain the gate.
- A download that feeds `sh` or `bash` is refused: `curl | sh` is a Semgrep finding and the rule the
  supply-chain review applies. Fetch a pinned artifact, verify it, then run it, or use the pinned
  action.
- `zizmor` runs offline in its own job at `--persona=auditor`; a finding at medium or worse fails the
  build. Keep the workflows clean at that level rather than adding an exclusion.

## The repository gates

`ci-gates.yml` runs the rules that are checked in this tree: the architecture wall, the English rule,
the hand-written prose rule, the README contract, the provenance of released tags, the coverage
floor, and the agent instructions (`scripts/agents_md_check.py`). A gate that runs in `make verify`
alone is local-only; add the step here in the same patch, with the reason the step exists.

A fork pull request does not run the runner jobs: they check out the pull request's own code and
execute it on a runner this project controls, and GitHub offers no fork-approval control here. Do not
remove the fork guard to make a fork green.

## Release automation

`release.yml` builds on a `v*` tag on `main`. It reads the signing material from the release
environment, builds both bundles, and drafts the release; the owner publishes it. The runbook is
[`RELEASE_PROCESS.md`](RELEASE_PROCESS.md), the policy behind the tag is
[`docs/RELEASE_POLICY.md`](../docs/RELEASE_POLICY.md). The version agreement across the six carriers
is pinned by `tests/test_version_sync.py` and `scripts/version_carriers.py`, and the release gate runs the suite before it builds a
bundle, so a half-edited version stops the release instead of shipping a mislabeled one.
