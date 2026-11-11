# Release policy — milestones are tagged, everything else rolls

Ephe is far from 1.0 and the approach to it is deliberately slow: the product
has to be good before it gets a number that claims it is. This page is the rule
that keeps the version from doing bookkeeping. A patch release per fix is not
discipline, it is the absence of a delivery channel.

Two things move code to people, and only one of them is a release.

| What | Tag | Release notes | GitHub release | Who gets it |
|---|---|---|---|---|
| **Milestone** (user-visible step, shell change, contract break) | yes | yes | yes, signed bundles | release channel by default; the store listings |
| **Rolling** (QoL, patches, bugfixes, docs, plugin catalogue) | no | no | no | anyone whose surface follows the rolling channel, on their click |

## What a release is for

A release is cut only when at least one of these is true. The list is
exhaustive on purpose; "it has been a while" is not on it.

1. **The native shell changed.** Anything in `app/src-tauri` — window, updater
   key, capabilities, the bundled WebView. The shell is a signed `.app`, so it
   can only arrive through a signed release.
2. **A user-visible milestone is done.** A named step in the roadmap that a
   person could notice and would want to read about.
3. **A contract breaks.** A plugin manifest field the old shell cannot load, a
   route removed without a compatibility shim, an `api_contract` bump.
4. **A store listing has to move.** Homebrew, npm, Scoop, the release feed.
5. **A security advisory needs a new signed bundle.** Only when the fix has to
   ride the shell; a backend fix does not.

Everything else — and that is the overwhelming majority of commits — is
rolling. The version number on `main` names the *next milestone*; it does not
change with a fix, and an untagged build says so: `0.7.0+1a2b3c4d5e6f`.

## The rolling channel

The product already carries the mechanism; this policy only stops hiding it.

- A surface set to the rolling channel compares the installed backend commit
  against the tip of `main` and moves on the user's click:
  `POST /api/update/apply` for the backend and the PWA the backend serves,
  `ephe update --channel commit` for a terminal checkout.
- The comparison is ancestry-based, so a checkout that is ahead or has diverged
  is never walked backwards.
- No tag is cut, no release is drafted, no notes are written, and
  `releases/latest` is untouched. The signed shell stays where the last
  milestone left it and catches up at the next release.
- The build is named by what it is: the version the tree carries plus the
  commit it runs. The update surface shows that identity and nothing else — a
  rolling step is a fix, not an announcement.

The channel value stays `commit` in settings and environment; the name is
historical, the meaning is rolling. `release` stays the default: a person who
has not opted in is not moved without asking.

## What may ride rolling

May ride: the Python backend, the PWA assets it serves, plugin bundles and the
plugin catalogue, documentation, tests, skills and prompts, performance and
quality-of-life work, bug fixes that keep the routes and the manifest contract
they had.

Must not ride: the Rust shell, an `api_contract` break, a migration whose
downgrade path is not proven, a removal without a shim, anything that changes
the signed bundle's own behaviour. Those wait for a milestone.

If a fix cannot ride because the shell must change, that is the moment to ask
whether the next milestone is really far away — not to cut a patch release.

## How an intermediate release is avoided

The reflex this policy removes: a one-line fix goes to `main`, someone cuts a
tag, and the release workflow signs a bundle, writes notes and moves the feed.
That happened twice in one evening — `0.6.6` carried a single plugin-switch fix,
`0.6.7` a single stack-trace fix. Both would have shipped on the rolling channel
with no tag, no notes and no signed shell; the person who wanted the fix would
have had it one click earlier.

The routine for a fix:

1. Land it on `main` behind the gates (tests, ruff, prose, language, docs).
2. Merge. Nothing else. Rolling surfaces see it on their next click.
3. If someone needs it *now*: Settings → Appearance → **Update channel** on
   their surface, then "Check for updates". That is the whole procedure.
4. When a milestone item finishes, bump to the milestone version, write the one
   release note that names it, tag, publish, and let the default-release users
   catch up in one signed step.

The release runbook (`docs/RELEASE_RUNBOOK.md`) keeps the mechanics of step 4
and loses the assumption that a fix implies a release.

## Version numbers

- `main` carries the next milestone version from the day the previous one
  shipped. It does not move for fixes.
- An untagged build is `version+sha`. It never compares as newer than a release
  of the same version in the updater, so a rolling user and a release user do
  not fight over the same number.
- A milestone release takes the version from `main` and tags it. There is no
  separate "release branch version".

## Rollback

- One device goes back to releases: set the channel to `release` and run the
  release update; the checkout lands on the newest tag.
- One rolling build is bad: revert the commit on `main`. Rolling users get the
  revert on their next click; nothing signed has to happen.
- A milestone is bad: the previous tag stays installable, and a device can be
  moved to it with the release update's explicit tag argument.

## What this buys

- The version number means something again: a tagged release is a promise about
  the shell and the contract, not a timestamp.
- Fixes reach people in minutes instead of an hour of CI and a signed bundle.
- The release notes stay readable because they are written per milestone.
- The slow approach to 1.0 stays slow on purpose, without the product also
  being stale between milestones.
