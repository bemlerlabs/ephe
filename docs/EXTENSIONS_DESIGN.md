# Design Doc — Ephe Extensions 1.0 (Waves E1–E6)

> Playbook rule 3 skeleton. Companion to `docs/EXTENSIONS_PRFAQ.md` (the
> working-backwards anchor). Status: E0 — E1 not yet implemented when this
> was written.

## Context

Ephe's extension surface exists in four half-connected layers: 51 skill packs
(install/enable, lockfile, quality gates), an MCP client (env + `mcp.json`),
internal pre/post-tool hooks (priority, args/result transforms), and the
`spawn_agent` helper with a hardcoded read-only whitelist. On top sits a
plugin store (catalog + registry + settings UI) whose enable toggles persist
to `plugins.json` — **and nothing consumes that state at runtime** (verified
2026-09-26). The deep-settings `plugins` section now carries policy fields
(`plugins.plugin_autorun`, `plugins.plugin_signature_check`,
`plugins.toolset_preset`, `plugins.mcp_servers_count`) that are persisted but
not yet wired.

## Goals

1. **E1 — Runtime honesty:** plugin enable/disable gates real behavior
   (tools, skills); master switch returns stock Ephe; every gate decision is
   audit-logged.
2. **E2 — Manifest v1:** one `ephe-plugin.json` bundles skills, commands,
   agent profiles, hooks, MCP servers, permissions; skill packs remain valid
   single-component plugins (never break userspace: 67 tools, 104 REST paths,
   51 packs).
3. **E3 — Deep catalog:** 8–12 first-party plugins replace the 8 empty
   catalog slots; catalog entries get real artifacts + hashes.
4. **E4 — Marketplace + supply chain:** marketplace.json (local + URL), semver
   updates, `ephe plugin` CLI, ES256 (RFC 8785) signatures, store detail UI.
5. **E5 — User extension points:** user-defined agent profiles (replace the
   hardcoded whitelist), user-defined hooks file with events
   (pre_tool/post_tool/session_start/turn_end/pre_compact), the plugins
   deep-settings section wired to runtime.
6. **E6 — Switcher migration:** `ephe import` maps a reference client's
   config, persona, skills, and tool-server definitions onto Ephe formats —
   diff first, everything imported disabled.

## Non-Goals (scope hammer — list only shrinks)

- No third-party UI rendering (generative UI stays A2UI-internal).
- No background marketplace sync; refresh stays manual + throttled.
- No auto-updates; semver ranges require explicit user action.
- No plugin sandbox beyond the existing WASI cell + approval gates (reuse,
  don't reinvent).
- No paid/revenue mechanics, no telemetry.

## Design (per wave, keystone first)

### E1 — Runtime wiring (core/plugin_runtime.py)

- Single consumer module: loads catalog + registry + the deep `plugins`
  policy once per turn (cached, invalidated like the MCP tool cache).
- `gate_for(tool_name) -> visible|hidden` maps TOOL_MAP families to catalog
  plugins: web_search/fetch_url→web-search, generate_image→image-gen,
  mcp_*→mcp, run_shell family→shell, analyze_image→vision, memory
  family→memory, TTS endpoints→tts. Skills map by pack name.
- Master switch = `plugins.master_enabled` (registry-level, UI toggle);
  off ⇒ every gate visible except third-party plugins AND non-builtin packs
  (stock Ephe = built-in behavior).
- Audit: every hide/allow decision appends to the existing JSONL audit log.
- UI: the existing store toggles start working; no new components needed in
  E1 beyond the master switch row.
- **Tests first** (`tests/test_r60_plugin_runtime.py`): disabled plugin hides
  its tools from `get_tool_schemas()` and its pack from skill routing; master
  switch restores stock; unknown plugin ids fail closed; audit lines written.

### E2 — Manifest v1

- `ephe-plugin.json`: `{ name, version, description, permissions{tool_families[],
  data_roots[]}, components{ skills[], commands[], agents[], hooks, mcp } }`.
- Loader treats `skills/<pack>/SKILL.md` packs as implicit one-component
  plugins; the catalog schema (v1) gains `manifest: true` + sha256.
- Commands: manifest-declared slash commands surface in the existing
  slash-command loader; no new runtime.

### E3 — Deep catalog

- First-party set (draft, owner-trimmed): research-suite (web-search +
  fetch + source-notebook), document-factory (pdf/docx/xlsx/deck packs),
  coding-suite (read/edit/patch/run_tests packs), memory-manager, vision,
  voice, channels (telegram/discord cards), tool-servers (mcp), image-gen,
  shell+terminal. Each = real artifact zip + sha256 + example prompts.

### E4 — Marketplace + signing

- `marketplace.json` (name, version, sha256, url, description, tags);
  resolution order: local registry → configured marketplace URL (manual
  refresh, throttle reused from plugin store).
- Signing reuses the ephemera cell's canonicalization + ES256; verify at
  install AND at enable when `plugins.plugin_signature_check` is true.
- Store UI: detail sheet (version, source, permissions, example prompts,
  update button) — existing liquid-glass tokens, judge-gated.

### E5 — User extension points

- `~/.ephe/agents/*.json`: role, tool whitelist (subset of TOOL_MAP), model
  override, timeout — spawn_agent generalizes from its hardcoded list;
  swarm keeps its own flow.
- `~/.ephe/hooks.json`: event → command/route mappings, priority ordering,
  fail-tolerant like the internal hooks; audit-logged.
- Deep `plugins` section wired: autorun + signature check consulted by the
  runtime; mcp_servers_count reflects live state.

### E6 — Switcher migration

- `ephe import <dir>`: reads a reference client directory; maps settings →
  deep sections (documented per-section mapping table), persona file →
  `persona.md` (already SOUL-compatible), skills → packs (SKILL.md-compatible),
  tool-server defs → `mcp.json`. Output = plan + diff; writes only on
  explicit confirm; everything lands DISABLED.
- Docs page "Switching to Ephe" + conformance note for the open skill
  standard.

## Alternatives considered

- **Wire toggles into each consumer ad hoc (no runtime module):** rejected —
  five silent failure points instead of one audited gate.
- **Full new plugin runtime (process-per-plugin):** rejected for 1.0 — the
  WASI cell already covers isolation where it matters; a new runtime violates
  scope hammering.
- **Skip migration wave:** rejected — the owner's stated goal is that users
  of reference clients can switch without starting over.

## Cross-cutting

- **Userspace guarantee:** OpenAPI paths, TOOL_MAP, and pack compatibility
  are release gates; every wave runs the frozen-baseline gates (pytest/vitest/
  tsc/build) + bench pass³ before release.
- **Security:** fail-closed gates, signature quarantine, no plugin approval
  bypass, audit on every decision; API-review gate for anything under /api/*.
- **i18n:** every new UI string lands in en+de with the parity test.
- **Honesty rule:** any toggle that does not change runtime behavior is
  either wired or removed — the store never lists decorative controls.
