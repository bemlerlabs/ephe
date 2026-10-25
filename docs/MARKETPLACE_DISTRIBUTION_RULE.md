# Marketplace distribution rule

One page. What may enter `marketplace/index.json`, and what a user is owed
before a package runs.

## One index

`marketplace/index.json` is the only surface a client reads. Every entry carries
publisher, licence, version, SHA-256 of the artifact, a source URL and real
content (a description in at least one language). An entry that misses one of
these fields is not listed; it is not listed with a blank.

The root catalogs (`ephe-marketplace.json`, `plugin-catalog.json`,
`plugin-marketplace.json`, `marketplace/first-party.json`,
`marketplace/third-party.json`) are sources for the migration, not surfaces.
`core.marketplace_catalog.migrate` merges them deterministically and refuses an
index that breaks the field contract.

## First-party packages

First-party plugins ship bundled with the application and are covered by the
repository's build and release gates. They need no download consent because
nothing is downloaded: the bytes are part of the signed application bundle.

## Third-party text packs

A pack that contributes prompts, skills or documents — no executable code —
enters after a review that records its origin, licence and provenance:

- the upstream URL, tag, commit and archive SHA-256;
- the licence identifier and the licence file digest;
- the exact list of included and excluded components, with a reason per
  exclusion;
- copy in both product languages.

Installing a pack is one click. A permission prompt appears only when the pack
declares tool families or data roots; a pack that declares none installs with
that single click.

## Third-party executable plugins

A plugin that can execute code is held to a higher bar:

1. **Signature.** The artifact carries a signature that verifies against a
   publisher key the client trusts.
2. **Verified publisher.** The publisher identity is verified out of band; an
   unverified publisher may not ship an executable component.
3. **Revocation.** A published revocation in `marketplace/revocations.json` wins
   over any local install: the client refuses the version and does not
   reinstall it.
4. **Consent.** The permission delta (tool families, data roots) is shown inline
   before the plugin may run, and the user's allow is per delta, not global.
5. **Sandbox.** Execution happens inside the cell with the declared permissions
   only; a plugin cannot widen its own scope.

## Withdrawal

A package can be withdrawn by publishing a revocation that names the version
and, when known, the artifact digest. The client treats a revoked version as
absent: it does not update to it, does not install it, and keeps an audit line
for every refusal.

## What this rule refuses

- An entry without a publisher, licence, version, SHA-256, source or content.
- An alias that resolves to more than one entry.
- An executable plugin from an unverified publisher or without a signature.
- A revoked version offered again under the same number.
- A count reported as the target when the verified entries are fewer.
