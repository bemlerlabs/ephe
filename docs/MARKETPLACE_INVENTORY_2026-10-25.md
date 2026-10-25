# Marketplace inventory — 2026-10-25 (S20)

Read-only survey of every catalog in the tree, the merged index, and the P1
branch. Counts come from the files; every number below is reproducible with the
command in its row.

| Source | Entries | What it is | Command |
|---|---|---|---|
| `ephe-marketplace.json` | 17 | generated metadata manifest (names, German copy, icon paths) | `python3 -c "import json;print(len(json.load(open('ephe-marketplace.json'))['plugins']))"` |
| `plugin-catalog.json` | 16 public, 0 personal | store catalog with directory hashes | same, key `public` |
| `plugin-marketplace.json` | 3 | legacy install listing | same, key `plugins` |
| `marketplace/first-party.json` | 16 | v2 first-party catalog | same, key `plugins` |
| `marketplace/third-party.json` | 1 | v2 third-party catalog (Superpowers) | same |
| `marketplace/index.json` | **22** | the one index this wave consolidates | `python3 -m core.marketplace_catalog --check` |

`marketplace/index.json` is the target document. The three root catalogs remain
as sources: the generated manifest carries German copy and icon paths, the store
catalog carries directory hashes, the legacy listing carries three entries no
other file names.

## Duplicates

16 ids are named by both `ephe-marketplace.json` and `plugin-catalog.json`:
browser-use, code-shell, documents, guide, image-studio,
local-document-factory, mcp-connector, memory, plugin-creator, presentations,
private-research-notebook, skill-creator, spreadsheets, vision, voice,
web-research. `plugin-marketplace.json` adds three names that the index does not
carry as separate entries.

The index resolves the overlap by making the built artifact identity the source
of truth: one row per id, with the metadata merged in. `core.marketplace_catalog`
reports the duplicate list instead of silently collapsing it.

## Aliases

Three legacy names resolve to the entry that carries the same function:

| Alias | Canonical |
|---|---|
| `web-search` | `web-research` |
| `coding-suite` | `code-shell` |
| `document-factory` | `local-document-factory` |

`marketplace_index.canonical_name` resolves them; an alias that shadows a real
entry or points at a missing one is refused at validation time.

## Coverage against the target

22 entries, all 22 pass the six-field contract (publisher, licence, version,
SHA-256, source URL, content). The target is 25, so the honest report is
**22 verified, gap 3** — not 25. The three missing entries are not invented.

## Metadata gaps left open

- Icons: `business-pack`, `dev-pack`, `office-pack`, `research-pack`,
  `writing-pack` have no `marketplace/icons/<name>.svg`. Superpowers received
  one in this wave.
- German description: `business-pack`, `dev-pack`, `local-document-factory`,
  `office-pack`, `private-research-notebook`, `research-pack`, `writing-pack`
  carry English only. Superpowers received a German line in this wave.
- Signature: every third-party entry is `unsigned`. Publisher status is
  `verified` only where the catalog sets it; Superpowers is `reviewed`
  (upstream MIT author plus this project's adaptation).

## Superpowers

| Field | Value |
|---|---|
| skills | 10 (dispatching-parallel-agents, executing-plans, finishing-a-development-branch, receiving-code-review, requesting-code-review, test-driven-development, using-git-worktrees, using-superpowers, verification-before-completion, writing-plans) |
| exclusions | 4, recorded with the reason in `PROVENANCE.json` |
| licence | MIT (`PROVENANCE.json` → `license.id`, file digest recorded) |
| provenance | upstream archive URL, commit `b36e082`, SHA-256 of the archive |
| copy | English + German (`ephe-plugin.json` → `description_i18n`) |
| icon | `marketplace/icons/superpowers.svg` |
| publisher | `Jesse Vincent (MIT), pack by Ephe`, review status `reviewed` |
| install | one component tree, no tools, no commands, no permissions → one click, no permission prompt |

## P1 branch

`rc/plugin-p1-2026-10-21` (one commit, `354c21c`, **38 commits behind main**) is
a plugin-platform UI candidate: workflow pins, the `PluginSwitch` component, the
plugin settings section and their tests. It carries **no**
`marketplace/index.json`. A blind merge would either conflict across 38 commits
or resurrect the older settings wiring, so it stays unmerged until its changes
are replayed onto the current tree one slice at a time.
