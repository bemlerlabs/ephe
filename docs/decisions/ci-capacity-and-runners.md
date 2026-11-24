# Where the CI runs and what it costs

Status: accepted, in effect. The fork guard and the two lanes were decided in the
workshop on 2026-10-09; everything under "Appendix" is a measurement taken on 2026-11-23
and read back from the API named beside it.

| Field | Value |
|---|---|
| Recorded | 2026-10-09, committed to this tree 2026-11-23 |
| Decides | which pull requests may reach a runner, which legs run on which lane, and what the plan's refusals mean for the release path |
| Scope of this change | this record, the fork guards in five workflows, the runner variable every Linux job reads |
| Measured on | macOS 26.6 (build 25G5065a) arm64, 10 CPU, account `bemlerlabs`, 2026-11-23 |
| Evidence | `gh api` responses for `/repos/bemlerlabs/ephe`, its `/actions/permissions`, `/actions/runners`, `/actions/variables`, `/environments`, `/branches/main/protection`, `POST /merge_queue`, and the run/job/annotation records of the runs named in the appendix |

Six workflow comments cite this path: `frontend-build.yml`, `ci-gates.yml`, `tests.yml`
twice and `release.yml` twice. For a stretch they cited a file that lived outside the
repository, which is the state in which a rule goes stale without anyone noticing; the
home is in the tree now, and every number here names the machine and the API response it
came from.

## The rule a fork is held to

A fork pull request does not reach a runner this project controls. The job checks out the
pull request's own code, and these runners sit on a machine that also holds the engine
data and the tunnel keys, so "check out and run whatever a stranger pushed" is not a
trade anyone here accepted.

GitHub's own controls for that -- `allow_forking=false` and the fork-approval endpoint --
answered HTTP 422 on 2026-10-09 on a user-owned private repository. Recorded then and left
standing; the guard does not depend on the answer being re-taken, because the
`if:` condition in the workflow enforces the rule regardless of what the settings do.

Two consequences are accepted and stated where the rule lives. A fork pull request gets no
CI and is reviewed by hand, and because GitHub counts a skipped required check as success,
nothing shows that as a problem: the human review is the gate, which is exactly why a fork
guard must never be removed to make a fork's checks green. Dependabot branches are
same-repo branches, so they keep running, and every pull request this repository has seen
so far was one of those.

## The two lanes, and the variable that chooses between them

Two lanes, one file each, and the boundary is in the workflows rather than in a setting
because a setting on this plan cannot express it.

The workshop lane runs on a runner this machine hosts: the security and preflight legs,
which need the engine data and the tunnel keys to answer anything. The hosted lane runs on
GitHub's runners: the full frontend, the matrix, the timing gate and the release build.
`vars.CI_LINUX_RUNNER` is the single switch -- every Linux job reads
`runs-on: ${{ vars.CI_LINUX_RUNNER || 'ubuntu-latest' }}`, so the variable moves a leg to
the workshop and its absence moves it back to hosted.

Measured on this repository 2026-11-23, on the account `bemlerlabs` over the API:

| Fact | Answer |
| --- | --- |
| Repository variables | none, so `CI_LINUX_RUNNER` is unset and every leg reads `ubuntu-latest` |
| Repository runners registered | 0 (`/actions/runners` → `total_count: 0`) |
| Runner process on this machine | none running, no `~/actions-runner` directory |
| Repository secrets | 0 |
| Environments | none, so `release.yml`'s `environment: release` has no configuration behind it yet |

The workshop lane is therefore not currently wired up: a decision about its runner was
made in October and the registration is not present. Everything that ran since has run on
GitHub-hosted runners and spent hosted minutes.

## What one push costs

Taken from the run list of commit `419c2a3` on 2026-11-23 (10 workflow runs, 23 jobs) on
this account: **146.4 hosted Linux minutes for one push**, itemised by job.

| Job | Minutes |
| --- | --- |
| Coverage floor (per-module ratchet) | 35.4 |
| pytest-linux py3.13 | 21.1 |
| Python canonical (3.13.18) | 19.7 |
| pytest-linux py3.11 | 17.4 |
| pytest-linux py3.12 | 14.8 |
| Build & Lint (22.x) | 11.6 |
| cargo (rust-shell) | 11.0 |
| pytest-macos | 4.1 |
| Docker build | 2.8 |
| Web | 1.7 |
| README contract | 1.1 |
| npm fallback | 1.0 |

Two additions matter. The macOS job's 4.1 wall minutes are billed at a multiplier GitHub
publishes for macOS runners; the multiplier here was never read off a billing endpoint, so treat
it as an estimate at roughly 41 equivalent minutes. With that, one push is about 150 to 190
billable minutes, which is 11 to 13 pushes on the 2 000 free minutes of a Free plan and 26 to 34 on
the 5 000 of Pro. A repository that pushes more than twice a day needs either the workshop
lane back or a plan that matches the push rate.

## What this plan refuses

Three things the workflows would otherwise use, each measured rather than assumed:

- **Merge queue.** `POST /merge_queue` answers 404 on 2026-11-23. Not available at this
  ownership and plan; the workflows do not depend on it.
- **Branch protection.** The same read answered 403 while the repository was private and
  answered `404 Branch not protected` on 2026-11-23, after the repository became public --
  404 is "no rule exists yet", which is the API being available. `infra/branch-protection.json`
  holds the 25 required check names to POST.
- **A required reviewer on the release environment.** HTTP 422, recorded 2026-10-09 and
  confirmed by the release runbook on 2026-10-15. The signing key is therefore protected by
  scope alone: the secret exists only in the `release` environment, which is why no job
  outside that environment may hold a repository-scope copy. Measured 2026-11-23: the
  environment does not exist yet, so `release.yml` cannot read the key at all until it is
  created.

## Appendix -- 2026-11-23: minutes, the lock, and what public changed

The sequence, with the source of each statement being the API response named beside it.

1. Every job of every run since run `45256928736` carried the annotation "The job was not
   started because an Actions budget is preventing further use." with `steps: []` and no
   retrievable log. The budget was empty; the code was not the problem.
2. The repository became public on 2026-11-23 (`/repos/bemlerlabs/ephe` → `visibility:
   public`). That removes hosted-minute billing for this repository and is what makes the
   CodeQL leg in `codeql.yml` possible at all; the query engines are licensed for public
   repositories.
3. It did not restore CI. Ten reruns at `2d73b15` and the runs at `c0ffdb3` all failed in
   about two seconds with zero steps, and the annotation had changed: **"The job was not
   started because your account is locked due to a billing issue."** The lock sits on the
   user account `bemlerlabs` and covers its public repositories too -- measured by
   dispatching a known-good workflow in the other public repository of the same account,
   `foreman`, which also failed with 0 steps and the same annotation.
4. The lock is account-scoped and the service is reachable. A throwaway public repository
   inside the organization `bemlerlabs369` ran a GitHub-hosted job at the same minute: 3
   steps, conclusion success, runner `GitHub Actions 1000000001`. The probe repository was
   deleted afterwards.

What follows from that, in order of cost. Resolving the billing issue on the account is
the only move that restores CI where the repository now lives; nothing in this tree can do
it. Moving the repository into an organization whose Actions are not locked restores CI
without payment and costs a new canonical URL, which touches the README, the package
manifests, `SECURITY.md` and every `github.repository ==` guard in the workflows. Running
the cheap legs on a self-hosted runner avoids hosted minutes for them, but a runner that
executes other people's pull requests on this machine is a worse trade than the fork guard
above already refuses, so if a workshop runner comes back it carries only legs that need
this machine and none that check out stranger's code.
