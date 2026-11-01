# Discover Marketplace — Design (2026-10-30)

The one page `/discover` becomes a full-breadth capability shelf: every
publicly readable skill, connector, add-on and tool the user's sources offer,
with a per-item detail overlay, built-in verification before enabling, and a
provenance label that never lets third-party content pass as ours.

## 1. What is measured today

- The shelf reads eight endpoints in one round (DiscoverPage.tsx:45): skills
  list, MCP settings, MCP health, MCP catalog, market home, market index,
  market installed, tool usage.
- Breadth: the bundled index holds 22 entries (9 plugin, 7 preset, 6
  skill-pack) over 11 categories; the repo carries 51 skill dirs and 16 plugin
  manifests; the offline collector queries the public connector registry with
  15 hardcoded search terms.
- The public connector registry answers live (HTTP 200) and paginates roughly
  2,500 versioned listings; its metadata is CC0. Aggregated directories exist
  in the tens of thousands of entries, with per-source rights and provenance
  that vary — some forbid automated reuse, some are paid.
- Vendor skill and plugin sets are federated JSON-in-git files with no global
  index (one official set is 315 plugins, another 19 skill dirs).
- The surface has no detail view: the card is the whole item.
- `server/routes/marketplace.py` deliberately hides federation: every read is
  filtered to the bundled source and no add/refresh route exists. The source
  engine behind it already supports local and https sources with signature
  verification and a cache in `~/.ephe/marketplace-cache`.

Honest ceiling: "everything that exists" is not a shippable set. The
defensible claim is "N sources, M items, known gaps", per-source freshness,
and no copy of anything we may not redistribute (README text is copyrighted;
registry metadata is CC0).

## 2. Approach (approved by the owner 2026-10-30)

Hybrid: a shipped snapshot for offline start plus user-provisioned live
sources, with verification built into the install path.

- The bundled index becomes a generated snapshot: our own items first
  (labelled "ours", never third-party items), then CC0 registry metadata,
  refreshed by a repo script and carried by the build. Hundreds of connector
  entries instead of 15 search queries; the script reads only public network
  indexes and files this repository owns. Nothing from local installs on a
  developer machine ever enters the repo.
- Sources become user-visible: a sources row on `/discover` lists each source
  with kind, trust, last-read stamp and last error; the user adds or removes
  sources, and each read is a visible, interruptible, opt-in network act.
  Offline start still serves the snapshot; a source failure shows "source
  unreachable" beside the source, never a blank page.
- Install verifies before it enables. One click plans: hash and signature
  against the index, then a static check of the package for tool-description
  injection, unpinned code-download starts (`npx` without version, `curl | sh`)
  and required environment variables. The permission sheet then lists exactly
  the new tool families and required secrets. Only confirmation enables.
  Verification outcome becomes the badge: unverified / signed / checked /
  checked clean.
- Third-party names appear only where the user must see them to install
  knowingly (publisher, title, source); nothing is labelled as ours that we
  did not build. Paid or non-public items are out of scope.

## 3. Data

- `core/marketplace_sources.py` gains a registry-source kind: cursor
  pagination, `updated_since` incremental sync, size caps, per-source
  last-read/last-error already modelled in `marketplaces.json`.
- The snapshot script (currently `scripts/catalog_discover.py`) gains one
  mode: emit the full CC0 mirror instead of 15 queries; the acquisition plan
  doc already separates discovery from publication.
- Each entry carries: kind, id, title, publisher + verification method,
  versions with pinned source (url, sha256, signature), license, categories,
  permissions, required env names (values never stored), icon, install
  count where a source offers one, freshness stamp, provenance badge.

## 4. Surface

- Four areas as tabs with persistent counts: Skills, Connectors, Add-ons,
  Tools (tools keep the audit-log bench as their evidence panel).
- Category facet rail as chips with a `+N` overflow; Source facet beside it;
  search scoped to the active area with a rotating suggested query as the
  placeholder.
- List organised as category sections with a "See all" row; each card shows
  the publisher eyebrow, icon, title, two-line description, verification
  badge, and a `+` / installed state.
- Hero: one carousel of our own items only, each slide a product claim with a
  measured number; third-party items never enter the hero.

## 5. Detail overlay

A centred modal per item, chosen because the chat surface keeps exactly one
right sidebar and a marketplace detail is catalogue, not a work artifact.
Tabs inside: Overview (description, publisher + how verified, license,
repository link, install count, last update), Versions (pinned version to
install, changelog), Permissions (tool families, required env names, what the
static check found), Source (which source supplied it, freshness, signature
status). Actions: add / enable / disable / remove, each through the existing
plan-and-review path.

## 6. Failure and edge states

- Empty: per-area direction text; never "everything failed" without naming
  the failed source.
- Stale vs unreachable are two different rows: last-success stamp against
  per-source freshness.
- Poisoned entry: the static check downgrades the badge and blocks enable.
- Revoked entry: the index revocation path already exists (revocations.json,
  renames); foreign sources get a per-source revocation list.

## 7. Verification and tests

- Backend: registry pagination and sync (unit, with a stub feed), snapshot
  generator (fixtures, licence gate), source add/remove routes with the
  XHR-marker rule, plan/install refusal codes unchanged.
- Frontend: DiscoverPage tests extend with sources row, facet overflow,
  detail modal, verification badge states; locale budgets re-measured.
- Release bar: Tauri parity manifest entry for any new route, bundle budget
  re-measured, four-surface visual check (CLI, TUI, PWA, desktop) after land.

## 8. Out of scope for this design

Paid or non-public items, hosting our own proxy domain, search-index
infrastructure beyond the source's own search, and any claim stronger than
"everything these sources publish".

## 9. Settings parity (walkthrough 2026-10-30)

The reference settings modal is two columns: an area list on the left, the
active area with breadcrumb, description and form on the right. Its areas,
captured from the running app:

- Model group with five sub-areas: main model, fallback models, helper
  models, subagents, mixture of agents.
- General: chat, appearance, workspace, security, browser, passwords and
  login, storage and accounts, language, advanced, notifications, billing,
  providers, gateways, keyboard shortcuts, tools and keys, sessions,
  plugins, about.

Ephe already covers most of these as areas with sub-sections; the parity
gaps to add per area are: model sub-area pages (fallback, helper, mixture),
the two judged-but-open areas (notifications, browser), and the
shortcut/session listings as first-class pages. Each new area follows the
existing PageHeader + section-row pattern and the settings save-surface
invariant tests. No third-party content is adopted; this is structure only.

## 10. Decisions taken (owner delegated 2026-10-30)

- Snapshot cadence: per build, plus `scripts/catalog_discover.py --mirror` /
  `--curated` on demand. The mirror is committed; the runtime never fetches.
- Two preset sources ship as one-click rows: the public connector registry
  and the official plugin catalog, with descriptive titles in the repo's
  preset file; every other source is user-provisioned.
- Tier model (the owner's 300–400 / 30–40 wish): the surface shows a curated
  tier by default — named picks plus the 20 most recently published entries
  per category (measured: 448 of 6,613) — and the full mirror stays behind
  the per-category "See all" and search. No raw dump on the landing view.

## 11. Status of implementation (2026-10-30)

- S1 done: mirror generator with cursor pagination (6,613 entries, 12
  categories), curated tier (448), runtime loaders, `/api/mcp/catalog` now
  answers `entries` + `curated` + `registry`.
- S2 done: `GET /api/market/sources`, `POST /api/market/sources`,
  `POST /api/market/sources/remove` with the XHR-marker rule and stable
  refusal codes; FROZEN_ROUTES extended.
- Open: S3 surface v2 + detail modal, S4 verification before enable, S5
  settings parity gaps, S6 rebuild both shipping surfaces and the
  four-surface visual check.

## 12. Publisher marks

A listing may name the icon of whoever publishes it. Two rules keep that honest.

- **The mark travels inside the repository.**
  `scripts/fetch_marketplace_icons.py` asks the publisher's own domain once,
  resizes what comes back to a 64 px tile, writes
  `marketplace/icons/providers/<slug>.png`, and records the URL, the fetch date
  and the SHA-256 of those bytes in `SOURCES.json` beside them. The surface reads
  `GET /api/discover/icon/<slug>` and that route serves only from this directory,
  so a render never calls a third party and an offline install still shows the
  marks it shipped with.
- **A row can name a mark only in one shape.** `ICON_SLUG` in
  `core/mcp_catalog.py` is the single rule, shared by the loader (which drops a
  value the route could never resolve) and the route (which refuses it again).
  `marketplace/featured.json` carries the slug per row; a curated row takes its
  slug from the host in its own install line, so the weekly re-sync keeps the
  field rather than erasing it.

Where a row names no mark, the card, the detail sheet and the hero each render the
subject glyph for its category. A mark and a glyph sit in the same plate at the
same size, so turning between a pick with a logo and one without keeps the title
where it was.

The marks belong to the publishers they identify. They are fetched to label the
listing of that publisher's own server, and nothing here grants a licence or states
that Ephe endorses a publisher or is endorsed by one.
