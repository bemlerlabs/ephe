# Publishing the npm package

This page is the home of the publish path: what ships where, what a future publish job must
satisfy before it exists, and what is deliberately not set up. Security's short version is in
[SECURITY.md](../SECURITY.md); the tag policy is in [RELEASE_POLICY.md](RELEASE_POLICY.md).

## What ships today

Nothing is published to the npm registry. One npm package wraps the CLI; the registry owner
holds it under appeal after the incident named in SECURITY.md, and no workflow in this
repository publishes anything to the registry in the meantime. The distribution paths that do
exist are the source tree, `install.sh` and `install.ps1`, and the release bundles that
`release.yml` drafts as GitHub Release assets; the owner publishes that draft by hand.

This state is a decision, not a gap: the package reaches the registry only if the appeal
resolves and every condition below is met, each of them written here in writing before the
first publish step lands.

## What a publish job must satisfy before it exists

- **A protected environment with a human in front of it.** The step runs in the release
  environment — the workflow line that binds a job to it is the one `release.yml` already
  carries for its signing material — standing behind required reviewers: a run does not publish
  because a tag appeared, it publishes because a person approved that run on the commit it
  checked out. That reviewer does not exist today and cannot be configured on the plan this
  repository runs on: the repository declares no environments at all (owner-measured through the
  repository's environments endpoint on 2026-11-24, `total_count: 0`), and GitHub refuses the
  required-reviewer rule on the current plan with HTTP 422, as `.github/workflows/release.yml:22`
  records. The condition is bound to a plan decision, not to our diligence: as long as no
  environment with a human approval gate exists, no publish path exists, and that absence is the
  design. A workflow line naming an environment would not change this — a first reference to a
  missing environment creates it on the platform without reviewers, which is why the settings
  side, not the YAML, is what a publish step must wait for. The credential side fails closed on
  its own: the registry accepts the OIDC identity only for a publisher the package owner
  configured on its side, so until that trust relationship exists every publish attempt is
  refused by the registry rather than reaching the package.
- **Short-lived credentials only, minted for one job.** The step authenticates with the OIDC
  identity the runner can mint for this repository, environment and tag, requested with a
  step-scoped `id-token` permission and never at the workflow root. A long-lived registry token
  is the thing that must not exist: not in repository secrets, not in an environment, not on a
  laptop. It is the shape that turns one leak into arbitrary versions under our name.
- **The registry gate green over exactly what leaves.** `scripts/registry_guard.py` refuses a
  remote script piped into a shell and an unasked-for npm lifecycle hook in every file under
  `packaging/`, `scripts/`, `server/`, `core/` and `.github/`; it reports its own scanned-file
  count with its verdict, exits 1 on a finding and exits 2 when it could not read an input, so
  a missing verdict never arrives as a pass. It runs in the pre-commit hook (through
  `scripts/ci_local.sh`) and as its own step in the repository gates, and its allowlist
  (`scripts/registry-guard-allowlist.txt`) makes every acceptance a line a diff has to carry.

## What the dry run has to show first

There is no publish step today, so there is no publish dry run either; this is the contract the
first one has to meet. Before anything uploads, the packager's dry run prints the tarball's file
list, the file sizes and the resolved registry target and dist-tag, and that file list is read
by a person: what a package carries out is the same class of claim as what its install hooks
run, and the incident this page exists for was a package whose contents nobody read. The dry run
names no upload, and the upload happens only in the protected environment described above.

## What is revoked when something looks compromised

Act on suspicion, not on proof. The order: revoke the credential, revoke the trust relationship
behind the publish identity, unpublish the affected versions, and re-issue from an audited
commit whose tree the registry gate has read. The account is the scarcer asset, so it is
protected first and restored last; a version can be re-issued, an unblocked account cannot be
un-asked.

## Deliberately not set up

- No publish job and no publish step, while the package sits with the registry owner under
  appeal; publishing resumes by decision, on the conditions above, not by habit.
- No long-lived registry token anywhere, and no OIDC trust is requested by any workflow today
  — the first step that needs one adds the permission at that step, with its reason beside it.
- No scheduled or tag-triggered publish that bypasses the protected environment: a job that can
  reach the registry without a named human approving the run is the defect, not the convenience.
