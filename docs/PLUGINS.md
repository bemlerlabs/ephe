# Ephe Plugins — Manifest Format v1 (E2)

> Spec for `ephe-plugin.json`. Autoren-Einstieg: `docs/PLUGIN_SDK.md`. A
> plugin is a directory under
> `~/.ephe/plugins/<plugin>/`; the manifest turns that directory into a
> versioned, validated, switchable unit.

## Layout

```text
~/.ephe/plugins/
└── research-suite/
    ├── ephe-plugin.json          # manifest (required)
    └── skills/
        └── deep-dive/
            └── SKILL.md          # a regular skill pack (agentskills-style)
```

## Manifest

```json
{
  "manifest_version": 1,
  "name": "research-suite",
  "version": "1.0.0",
  "description": "Deep research bundle",
  "permissions": {
    "tool_families": ["read", "network"],
    "data_roots": []
  },
  "components": {
    "skills": ["deep-dive"],
    "commands": [
      { "name": "research", "description": "Run deep research", "template": "Research: {input}" }
    ],
    "agents": [],
    "hooks": {},
    "mcp": {}
  }
}
```

| Field | Rules |
|---|---|
| `manifest_version` | Must be `1` |
| `name` | Lowercase slug `^[a-z0-9][a-z0-9-]*$`; MUST equal the directory name |
| `version` | Semver `X.Y.Z` |
| `description` | Non-empty string |
| `permissions.tool_families` | Subset of `read, write, shell, network, memory, vision, docs, browser` |
| `permissions.data_roots` | List of path strings (display/intent; runtime roots stay governed by the security config) |
| `components.skills` | Pack directory names that MUST ship a `SKILL.md` under `skills/` |
| `components.commands` | `{ name (slug), description (non-empty), template? }` — template placeholders are expanded server-side |
| `components.agents` | Agent profiles: `{ name, description?, tools (⊆ TOOL_MAP), model?, timeout? }` — bundle helper agents; fail-closed validation (unknown tool quarantines the agent) |
| `components.hooks` / `mcp` | **Reserved** (E4b/E6): accepted structurally, never executed by the current runtime |

## Enforcement semantics

- **Fail-closed validation.** Any contract violation quarantines the WHOLE
  plugin (never a half-loaded state): bad JSON, bad slug/semver, name
  mismatch, an unknown tool family, or a declared skill pack that does not
  ship. Quarantined plugins show up in `GET /api/plugins` scan output with
  their error.
- **Fail-soft scanning.** One broken directory never breaks the others.
- **Enablement is real.** A registry-disabled plugin (or master switch off)
  contributes no skills and no commands on the very next turn. Catalog
  defaults never gate silently — only explicit registry entries do.
- **Priority.** Bundled skill packs have the lowest priority: user packs and
  built-ins always win on name collisions.
- **Commands.** `/name` entries of active plugins join the composer slash
  menu (`GET /api/plugins/commands`) and are expanded from their template
  server-side.

## API surface (v1)

| Endpoint | Purpose |
|---|---|
| `GET /api/plugins` | Catalog + registry + master switch |
| `POST /api/plugins/{id}/enable` | Toggle one plugin |
| `POST /api/plugins/master` | Kill-switch (false = stock Ephe) |
| `GET /api/plugins/commands` | Slash commands of active manifest plugins |

## Marketplace (E4a)

`plugin-marketplace.json` (repo root) lists installable artifacts:

```json
{
  "version": 1,
  "plugins": [
    { "name": "web-search", "version": "1.0.0", "sha256": "…", "url": "https://…/web-search.zip", "description": "…", "tags": [] }
  ]
}
```

Install flow (strictly verify-first):

1. `resolve` the entry → 2. `fetch` the artifact (injectable fetcher; never
network in tests) → 3. `sha256` compare against the entry → 4. SAFE unzip
(zip-slip guard: every member must stay inside the destination) → 5. manifest
validation. Outcomes: `extracted` (enabled by default), `hash_mismatch`
(nothing extracted), `unsafe_archive` (rejected), `quarantined` (extracted
directory removed again), `unknown_plugin` / `no_url` (honest, no crash).

CLI:

```bash
ephe plugin list                 # catalog + enabled state + version
ephe plugin enable web-search    # takes effect on the next agent turn
ephe plugin disable web-search
ephe plugin install web-search   # from plugin-marketplace.json
```

## Signatures (E4b)

A plugin directory can carry a signature record (`ephe-plugin.sig.json`,
excluded from the content hash):

```json
{
  "alg": "ES256", "kid": "first-party",
  "name": "web-search", "version": "1.0.0",
  "sha256": "<dir_sha256 at signing time>",
  "signature": "<base64 ECDSA-P256-SHA256 over canonical_json(payload)>"
}
```

- `canonical_json` = RFC 8785 subset for manifest payloads (sorted keys, no
  whitespace, UTF-8).
- **Install-time:** a marketplace entry with a `signature` object is verified
  against the extracted content; failure → quarantined (directory removed).
- **Enable-time drift gate:** with the deep setting
  `plugins.plugin_signature_check` (default ON) and a signature record
  present, re-enabling a CHANGED plugin fails with 409 and an audit line —
  recorded hash vs. current hash is part of the error message.
- Trust anchors: repo `plugins/first-party.pub.pem` (when shipped) +
  `~/.ephe/trusted-keys/*.pub.pem`.

## User agents (E5)

Helper profiles for `spawn_agent` live in `~/.ephe/agents/<name>.json` (or
bundled via `components.agents` of an active plugin):

```json
{
  "name": "scout",
  "description": "Fast read-only explorer",
  "tools": ["read_file", "list_directory", "file_search"],
  "model": null,
  "timeout": 60
}
```

Fail-closed validation: an unknown tool quarantines the profile, `timeout`
clamps to 30–900 s, an empty tool set never loads. `spawn_agent` resolves its
`subagent_type` label against these profiles — a match pins the helper's
tools/model/timeout, an unknown label runs the stock read-only generalist.

## User hooks (E5)

`~/.ephe/hooks.json`:

```json
{
  "pre_tool":  [{ "command": "/usr/local/bin/guard", "match": "run_shell", "priority": 10 }],
  "post_tool": [{ "command": "/usr/local/bin/annotate" }],
  "session_start": [], "turn_end": [], "pre_compact": []
}
```

Contract: the command receives one JSON line on stdin
(`{"event", "tool", "args", "result"}`) and may print one JSON line:
pre_tool → `{"args": {…}}` (transform) or `{"block": "reason"}` (deny);
post_tool → `{"result": "…"}`. Fail-tolerant (crash = ignored + audit line),
`match` filters per tool, `priority` orders (lower first), argv execution
without shell, 10 s cap, every run audit-logged.

## Deep wiring (E5)

- `plugins.plugin_autorun` (default OFF): whether a freshly INSTALLED
  marketplace plugin lands enabled or disabled in the registry.
- `plugins.mcp_servers_count` reflects the LIVE configured server count.
- `plugins.plugin_signature_check` (default ON): the enable-time drift gate (E4b).
- `tts` plugin: an explicit registry-disable denies `/api/audio/synthesize`
  with an honest 403 (no silent stock change without a toggle).

## Reserved for later waves

- `components.agents` → user-defined helper-agent profiles (E5).
- `components.hooks` → user-defined event hooks (E5).
- `components.mcp` → per-plugin tool-server definitions (E4/E5).
- Signature verification (ES256 over the canonical manifest) at install and
  enable time (E4).
