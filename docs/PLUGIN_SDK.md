# Ephe plugin SDK — short guide for plugin authors

> Working doc for plugin authors. The authoritative field specification stays
> `docs/PLUGINS.md` (manifest v1); this document is the practical entry point
> along the real install/verify path. Modules:
> `core/plugin_manifest.py` (validation), `core/plugin_store.py` (registry +
> scan), `core/plugin_market.py` (marketplace install), `core/plugin_signing.py`
> (ES256), `core/plugin_runtime.py` (activation); REST:
> `server/routes/plugins.py`.

## 0. Mental model

A plugin is a **folder** under `~/.ephe/plugins/<name>/` holding an
`ephe-plugin.json` — one switchable unit: enable/disable changes skills,
slash commands and helper agent profiles **from the next turn on**, without leaking
into other sessions. There is no silent fallback: what is not in the manifest
does not exist for the agent.

## 1. A minimal plugin in 3 steps

1. Create the folder: `~/.ephe/plugins/my-tool/`
2. Write `ephe-plugin.json` — `name` MUST equal the folder name:

```json
{
  "manifest_version": 1,
  "name": "my-tool",
  "version": "0.1.0",
  "description": "Short summary of what the bundle does.",
  "permissions": {
    "tool_families": ["read", "shell"],
    "data_roots": []
  },
  "components": {
    "skills": ["my-pack"],
    "commands": [
      { "name": "my-tool", "description": "Short, what the command does", "template": "Use {input}" }
    ],
    "agents": [],
    "hooks": {},
    "mcp": {}
  }
}
```

3. Ship every skill pack you declared: `skills/my-pack/SKILL.md`
   (agentskills style, frontmatter `name`/`description`). A declared pack
   without a `SKILL.md` quarantines the whole plugin.

Check the visibility:

```bash
ephe plugin list                                      # is "my-tool" in the catalog, enabled?
curl -s localhost:8765/api/plugins | python3 -m json.tool   # quarantine + error per entry
curl -s localhost:8765/api/plugins/commands             # is /my-tool in the slash menu?
```

## 2. Component cheat sheet

| What | Manifest field | Rule (short form) |
|---|---|---|
| Skill packs | `components.skills[]` | directory names; `SKILL.md` mandatory; on a name collision the user/built-in packs always beat the bundled ones |
| Slash commands | `components.commands[]` | `{name, description, template?}`; the server expands the placeholder (`{input}`) — no JS in the composer |
| Helper agents | `components.agents[]` | `{name, description?, tools ⊆ TOOL_MAP, model?, timeout?}`; `timeout` clamp 30–900 s; an unknown tool ⇒ the profile is quarantined; an empty tool set never loads |
| Hooks | `components.hooks` | reserved — accepted structurally, never executed; the active hook API is `~/.ephe/hooks.json` (E5) |
| MCP | `components.mcp` | reserved |

The hook contract (`~/.ephe/hooks.json`, E5): one JSON line on stdin
(`{"event","tool","args","result"}`), one JSON line on stdout — `pre_tool`:
`{"args":{…}}` or `{"block":"reason"}`; `post_tool`: `{"result":"…"}`.
argv without a shell, a 10-s cap, `match` per tool, `priority` ascending, every
run audit-logged.

## 3. Permissions and the security profile

`permissions.tool_families` ⊆ `read | write | shell | network | memory | vision | docs | browser`.
The declared families are declarative: the app's security profile
(strict / session / autonomous) remains the hard approval boundary.
`data_roots` carries entries for display/intent only. Declare only the
families your own skill really needs — smaller surfaces =
less approval friction.

## 4. Distribution through the store

- Pack the plugin as a ZIP with **one** top-level folder = the plugin folder name (`my-tool/` holding
  `ephe-plugin.json` + `skills/` inside it). Zip-slip guard: every member has to stay
  inside the target folder.
- Catalog `plugin-marketplace.json` (repo root):
  `{ "name", "version", "sha256", "url", "description", "tags" }`; the
  `sha256` is compared against the delivered content during install
  (verify-first: resolve → fetch → sha256 → SAFE unzip → manifest validation).
- With a `signature` object (E4b) the install verifies ES256 over
  `canonical_json`; after that the drift gate applies on re-enable: 409 when the
  content changed, with the detail in the error (recorded hash vs. current hash).

Install/check:

```bash
ephe plugin install my-tool          # from plugin-marketplace.json
curl -s localhost:8765/api/plugins   # is extracted / enabled visible?
```

Install result values: `extracted` (then enabled), `hash_mismatch`
(nothing extracted), `unsafe_archive` (discarded), `quarantined` (folder
backed out), `unknown_plugin` / `no_url` (honest, no crash).

## 5. Debugging table

| Symptom | Most likely cause | First look |
|---|---|---|
| The plugin is missing from `ephe plugin list` | the scan overlooks the folder: folder name ≠ `manifest.name` (a hard rule) or a JSON error | the `GET /api/plugins` scan output, the `error` field per entry |
| enabled, but the skills/commands are empty | `components` declared incompletely, or the master switch is off | complete `components`; `POST /api/plugins/master` |
| Quarantine after an edit | the E4b drift gate: a signature record exists and the content changed | is `plugins.plugin_signature_check` ON? re-sign or update `ephe-plugin.sig.json` |
| The command does not appear in the composer | `name` without the leading `/`? only validated plugins return entries | `GET /api/plugins/commands` |
| 404/43-style load errors | nested folder: `plugins/<x>/<name>/ephe-plugin.json` | exactly one level: `plugins/<name>/ephe-plugin.json` |

## 6. Checklist before the release pack

- [ ] `name` = folder name, slug-conformant (`^[a-z0-9][a-z0-9-]*$`), `version` = `X.Y.Z`
- [ ] every declared skill pack has `skills/<pack>/SKILL.md`
- [ ] tool families kept minimal; only real TOOL_MAP names in `components.agents.tools`
- [ ] the ZIP's `sha256` computed freshly and maintained in `plugin-marketplace.json`
- [ ] the signature record (`ephe-plugin.sig.json`) matches the current `ephe plugin list` version
- [ ] dry run: master-disable → `GET /api/plugins/commands` goes empty; master-enable → entries back

## See also

- `docs/PLUGINS.md` — the complete manifest format v1, enforcement semantics, API table
