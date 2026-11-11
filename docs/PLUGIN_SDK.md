# Ephe plugin SDK — short guide for plugin authors

> Working doc for plugin authors. The authoritative field specification stays
> `docs/PLUGINS.md` (manifest v1); this document is the practical entry point
> along the real install/verify path. Modules:
> `core/plugin_manifest.py` (loading and scanning),
> `core/plugin_manifest_contract.py` (the manifest contract),
> `core/plugin_memory_contract.py` (a declared memory provider),
> `core/plugin_store.py` (registry + scan), `core/plugin_market.py`
> (marketplace install), `core/plugin_signing.py` (ES256),
> `core/plugin_runtime.py` (activation); REST: `server/routes/plugins.py`.

## Quickstart: an installed plugin in ten lines

A plugin is a folder under the plugins root, and folder presence is the install: the
scanner reads `~/.ephe/plugins/<name>/ephe-plugin.json`, and `ephe plugin list` shows that
row with its switch state. Nine lines from an empty folder, with a shell and nothing else:

```bash
mkdir -p ~/.ephe/plugins/hello-card/ui
cat > ~/.ephe/plugins/hello-card/ephe-plugin.json <<'JSON'
{"manifest_version": 1, "name": "hello-card", "version": "0.1.0",
 "description": "Says hello.", "permissions": {"tool_families": [], "data_roots": []},
 "components": {"ui": {"type": "floating-window", "entry": "ui/index.html", "title": "Hello"}, "skills": [], "commands": []}}
JSON
printf '<!doctype html><meta charset="utf-8"><p>Hello.</p>\n' > ~/.ephe/plugins/hello-card/ui/index.html
ephe plugin list
ephe plugin enable hello-card
```

`ephe plugin list` prints `hello-card` with `on`. A row whose state reads `invalid` is a
folder the loader refused, and the line under the table names why — the usual causes are a
`name` that differs from the folder, a file a component declares but does not ship, and a
JSON typo. The switch applies from the next agent turn. Everything below this point explains
what the nine lines contain; the manifest fields are in [PLUGINS.md](PLUGINS.md), and the
marketplace path is §5.

## 0. Mental model

A plugin is a **folder** under `~/.ephe/plugins/<name>/` holding an
`ephe-plugin.json` — one switchable unit: enable/disable changes skills,
slash commands and helper agent profiles **from the next turn on**, without leaking
into other sessions. There is no silent fallback: what is not in the manifest
does not exist for the agent.

Handing that folder to someone else is specified in
[PLUGIN_EXPORT.md](PLUGIN_EXPORT.md). The export and file-import commands
are the next change.

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
ephe plugin list                                      # is "my-tool" installed and enabled?
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
| Surface | `components.ui` | one descriptor `{type, entry, title, default_size?, capabilities?}`; `entry` is an `.html` document inside the bundle, and `capabilities` is the closed vocabulary of `core/plugin_ui_capabilities.py` |
| Contributed tools | `components.tools[]` (a manifest v2 list) | one object per tool `{name, entry, family, description, parameters?}`; `entry` is a `path.py:callable` inside the bundle and the served name is the declared one (`web_search` is served as `web_search`; the namespace is the package, not the name); `family` has to be one `permissions.tool_families` declares; rules and the DoD checks in `docs/PLUGINS.md` |
| Vendored libraries | `ephe-libraries.json` (a file beside the manifest) | one entry per shipped code file `{name, version, path, sha256, kind}`; every byte under `vendor/` has to be declared or the plugin is quarantined (§4) |
| Memory provider | `capabilities.memory` (a manifest v2 object) | one descriptor `{id, transport, url, scope?, description?}`; registered from the same manifest scan the tool gate reads, and reachable only while the bundle is active (§3d) |

The hook contract (`~/.ephe/hooks.json`, E5): one JSON line on stdin
(`{"event","tool","args","result"}`), one JSON line on stdout — `pre_tool`:
`{"args":{…}}` or `{"block":"reason"}`; `post_tool`: `{"result":"…"}`.
argv without a shell, a 10-s cap, `match` per tool, `priority` ascending, every
run audit-logged.

## 3. Permissions and the security profile

`permissions.tool_families` ⊆ `read | write | shell | network | memory | vision | docs | browser`.
The declared families are declarative: the app's security profile
(strict / session / autonomous) remains the hard approval boundary.
`permissions.data_roots` is a read grant, and both rails honour it: the kernel file tools a
bundle calls, and the confined worker a v2 tool runs in, which used to see nothing of the
line. Absolute paths are taken as written after `validate_data_roots` has refused a home or
system root and a name that is not a folder; a relative entry is a folder inside the current
workspace, and a `..` that leaves it quarantines the manifest at load. Nothing declared this
way becomes writable — a worker writes in its own state directory, the folder its `state_dir`
argument names. Declare only the families and the folders your skill really needs; smaller
surfaces mean less approval friction.

That state folder is bounded by `permissions.state_cap_mb`, a whole number of megabytes, and
the default is **512 MiB** whether or not the line is written. A bundle at or past its ceiling
is refused before a worker starts, with the bytes it holds and the bytes it may keep named,
and the move the reader has is on Extensions: that row names the megabytes kept and the
megabytes allowed, and lists the stored files so one of them can be removed. The folder
path stays off the row. The run that crosses the ceiling is
allowed and measured — its row in the audit view carries `state_bytes=` and
`state_cap_bytes=` — and the call after it is the one refused, because a per-directory quota
exists on neither rail this product runs on, and a child that found itself unable to write
would report that as a failure of its own.

```json
"permissions": {
  "tool_families": ["read", "network"],
  "data_roots": ["cache"],
  "state_cap_mb": 512
}
```

### 3a. The tool callable, and the bridge it may ask the host through

A contributed tool is a Python callable inside your bundle. It runs in a worker process the OS
boundary created — no network, no host paths, a scrubbed environment, a wall clock — and never
inside the application. The host hands it two arguments and reads one value back:

```python
def run(arguments: dict, state_dir: str):
    ...
    return {"summary": "..."}          # JSON-serialisable, capped at 64 KiB
```

A tool that needs something the boundary cannot do — reading a URL, or running a search — takes
a third argument. The host inspects the signature when it calls you and passes a bridge handle
when the callable asks for one; nothing else about the call changes.

```python
def run(arguments: dict, state_dir: str, bridge):
    page = bridge.fetch("https://example.com/spec.md")   # {"status": 200, "text": "...", …}
    return {"chars": len(page["text"]), "truncated": page["truncated"]}
```

What the handle offers, and what it will not:

| | |
|---|---|
| Methods today | `fetch(url)` — the host's guarded reader, redirects re-checked hop by hop, HTML reduced to text. `search(query, max_results=None)` — the host's search function, the same one the kernel tool runs. `fetch_url(url, prompt=None)` — the kernel page tool. The text is that function's own sentence, including its failure lines. `prompt` stays off the wire when the caller left it out. `memory_add`, `memory_replace`, `memory_remove` and `memory_list` — the kernel memory tool, one method per action. `memory_action(action, target, ...)` carries an action outside those four to the same function and refuses a known action. A field the caller left out stays off the wire. `browser_go(url)`, `browser_screenshot()`, `browser_click(target_description)`, `browser_type(text)`, `browser_press(key)`, `browser_scroll(direction=None, amount=None)`, `browser_evaluate(js)` and `browser_exec(code, session=None, timeout_s=None)` run the kernel browser tools, one method per action. `direction`, `amount`, `session` and `timeout_s` stay off the wire when the caller left them out. The address check and the release gate stay in the kernel functions. `vision_click(target_description)` and `vision_type(text, press_enter=None)` run the kernel desktop tools. `press_enter` stays off the wire when the caller left it out. The confirmation stays inside those functions. `analyze_image(path, question=None, region=None)` runs the kernel image tool. `question` and `region` stay off the wire when the caller left them out. The path check stays in that function. `run_shell(command, cwd=None)`, `read_file(path, offset=None, limit=None)`, `write_file(path, content)`, `edit_file(path, old_string, new_string, replace_all=None)`, `list_directory(path)`, `file_search(query, path=None)`, `load_workspace(path, extensions=None)`, `analyze_project(path)`, `run_tests(command, cwd=None)`, `run_linter(path, fix=None, max_issues=None)`, `format_code(path, check_only=None)` and `scaffold_project(target_dir, template=None, project_name=None, description=None, author=None)` run the kernel shell and file tools. A field the caller left out stays off the wire. The command check and the path check stay in those functions. `create_pdf(title, content, filename=None, template=None, document=None)`, `create_docx(title, content, filename=None)`, `create_qrcode(data, filename=None, fill_color=None, back_color=None)`, `extract_pdf_text(path, max_chars=None)`, `build_document(topic, source_paths=None, include_web_research=None, filename=None)`, `export_source_brief(notebook_path, question=None, filename=None)`, `create_source_notebook(paths, title=None, notebook_id=None, extensions=None)`, `query_source_notebook(notebook_path, question, max_chunks=None)` and `verify_artifact(path, checks=None)` run the kernel document tools. A field the caller left out stays off the wire. The body check stays in those functions. `create_xlsx(title, data, filename=None, path=None, formats=None)` and `generate_chart(chart_type, title, labels, values=None, xlabel=None, ylabel=None, color=None, theme=None, series=None)` run the kernel sheet and chart tools. A field the caller left out stays off the wire. The formula check stays in those functions. `create_pptx_deck(topic, audience=None, thesis=None, slides=None, filename=None, deck_profile=None, design_theme=None, source_notes=None, evidence_level=None, enterprise_grade=None, template_path=None, brand_name=None, brand_primary=None, brand_secondary=None, deck_quality_profile=None, source_notebook_path=None, asset_paths=None)`, `create_pitch_deck(topic, audience=None, thesis=None, slides=None, filename=None, include_animation_preview=None, deck_profile=None, design_theme=None, source_notes=None, evidence_level=None, enterprise_grade=None, deck_quality_profile=None, brand_kit=None, source_notebook_path=None, asset_paths=None)`, `inspect_pptx_template(path, filename=None)`, `edit_pptx_template(template_path, replacements, filename=None)`, `qa_pptx_deck(pptx_path)`, `create_diagram(kind, title, items, filename=None, theme=None)` and `create_svg(svg_code, filename=None)` run the kernel deck tools. A field the caller left out stays off the wire. The slide check stays in those functions. `generate_image(prompt, filename=None, size=None)` runs the kernel picture tool. `filename` and `size` stay off the wire when the caller left them out. The endpoint check stays in that function. `synthesize(text)` runs the local piper writer. `transcribe(name)` runs the kernel speech reader on one file already stored for this session |
| Grant | the method's family has to be in this bundle's `permissions.tool_families`; a family named in the arguments is ignored, and the mount's declaration is what answers |
| Calls | 32 per tool run — a loop of host calls is a second agent run the manifest never declared |
| Size | 64 KiB per message in either direction; a `fetch`, `search` or `fetch_url` answer is cut to what fits and says `truncated` |
| Audit | every call writes one `bridge_call` row naming the plugin, the tool, the method and the decision. A fetch row names the host and drops the path and the query of the URL. A `fetch_url` row names the host the same way, and the prompt stays out of the row. A search row records the method and no query. A memory row records the method and no entry body. A browser row records the method. A navigation row names the host. Typed text, a script and a code block stay out of the row. A vision row records the method. The target description and the typed text stay out of the row. An image row records the method. The path and the question stay out of the row. A shell row records the method. The command, the path and the file body stay out of the row. A document row records the method. The body, the path and the source text stay out of the row. A sheet row records the method. The rows, the labels and the path stay out of the row. A deck row records the method. The slide text, the notes and the path stay out of the row. A picture row records the method. The prompt stays out of the row. A voice row records the method. The spoken text and the transcript stay out of the row |

A refusal is an exception with a `code` attribute, and the code is the part you can act on:

| Code | What happened |
|---|---|
| `bridge_method_unknown` | No such method in this build; the text names what exists |
| `bridge_method_denied` | The method works in a family this bundle did not declare, or the host's own guard refused the address |
| `bridge_args_invalid` | A required argument was missing or blank |
| `bridge_payload_too_large` | The message is past the byte ceiling |
| `bridge_call_limit` | The 32 calls of this run are spent |
| `bridge_internal` | The host could not complete it. The text is an exception class name. A search whose backends refused carries the status line the kernel tool already writes |

A `fetch_url` refusal keeps the code the kernel tool put on the sentence. The worker hands that code back with the text, and the host puts it on the sentence again. The model still reads the sentence. A memory sentence does the same, and keeps the flag that says whether the action happened, so a stored entry is a completion.

`docs/SANDBOX_EXECUTION.md` states which ceiling each layer actually enforces, per platform.

## 3b. The page SDK

A surface loads one file, `ephe.js`, from its own mount:

```html
<script src="ephe.js"></script>
```

The mount serves the copy that ships with this build. A file of the same name inside the bundle is not the one that loads. There is no package to install. The field lists stay in `docs/PLUGINS.md`.

The page is sandboxed, so the file asks the frame that embedded it. The overlay answers. A native window is its own top-level document in this build, and a page there has no embedding frame to ask. Each call waits 120 seconds.

| Call | What it does |
|---|---|
| `ephe.storage.get(key)` | The value stored under that key, or `null` when the key is absent. Asking does not create the state folder |
| `ephe.storage.set(key, value)` | Stores one JSON value. `null` removes the key. A key is one token of letters, digits, `.`, `_` and `-`, at most 64 characters. A slash is refused |
| `ephe.callTool(name, args)` | Runs one tool this bundle owns. The answer is the tool's own sentence. A tool another bundle owns is refused. A tool that needs a confirmation still needs one, and with nobody asking the user the sentence says the call was not executed |
| `ephe.subscribe(listener)` | Calls `listener` with `{event, data}` for this bundle's lifecycle events, and for the global pause. Returns the function that removes the listener |

`sdk/ephe.d.ts` is the type of that global for a strict checker. The runtime file is `sdk/ephe.js`.

### 3c. Page storage for a mounted surface (existing bundles)

A mounted document has an opaque origin — `sandbox allow-scripts allow-popups` with no
`allow-same-origin` — so the engine's own `localStorage` and `sessionStorage` throw a
`SecurityError`. The mount restores the *API* without restoring the origin: it serves
`sdk/ephe-storage.js` under a reserved name and places it, with a snapshot of this
bundle's own page store, ahead of the first script the bundle ships. A bundle that was
written against the Storage API keeps working; that is the bridge for existing bundles,
and `ephe.storage` above stays the path a new bundle should use. Nothing here makes the
shim the authoring path: a new bundle keeps its state with `ephe.storage`, and the
definition of done grades that call. The mount serves `ephe.js` itself, so the reference
`<script src="ephe.js"></script>` is the SDK and a bundle does not ship that file.

What the shim guarantees:

- `localStorage.getItem`, `setItem`, `removeItem`, `clear`, `key` and `length`, with
  synchronous reads served from the snapshot the mount embedded.
- A read straight after a write returns the written value (`setItem` updates the view
  at once and sends the write over the `ephe.sdk` bridge; the shell stores it in this
  bundle's own state root). A reload sees it in the new snapshot.
- Only this bundle's store is in the snapshot, and the frame's host is bound to this
  bundle's id, so no frame can read a sibling's keys.
- A refused or unanswered write is never silent: the key falls back to its confirmed
  value, `window` dispatches `ephestorageerror` with `{key, code, message}`, and the
  next call that touches the key throws an `EpheStorageError` whose `name` is
  `EpheStorageError` and whose `code` names the failure (`storage_refused`,
  `storage_timeout`, `storage_write_failed`, `storage_no_host`, `storage_unavailable`).
- `sessionStorage` has the same methods and is a memory area for this document. The
  sandbox gives every document a fresh opaque origin, so a session area would not have
  survived a reload anyway.

What it does not do, and a bundle must not rely on:

- Named-property access (`localStorage.theme`), `for...in`, `JSON.stringify(localStorage)`
  and the cross-document `storage` event are not emulated. Use the methods above.
- A key must be 1–64 characters from `A-Z a-z 0-9 . _ -`, starting with a letter or
  digit (the page store's rule). Any other key throws `storage_key_invalid`; it is never
  silently stored.
- The store is a string store: `setItem` writes the string form of its value, and a
  non-string value written through `ephe.storage.set` reads here as its JSON text. The
  two APIs share the store but not a value type, so pick one per key.
- The snapshot is taken when the document loads. A write from another document (or a
  reload in another window) is not pushed into this one, and `clear()` removes the keys
  this document knows — the snapshot it started with plus its own writes. Use
  `ephe.storage` when a page must see a sibling's latest value.
- The shell's store ceilings still apply: 8 KiB per value and 64 KiB per bundle
  (`core/plugin_state.py`). A value past the ceiling arrives as a refused write through the
  same `ephestorageerror` path, so a page reads one error shape for every refusal.
- A native window (slot `native`) is its own top-level document with no embedding frame,
  so there is no host for the bridge. The shim's reads still come from the snapshot, but
  a write there fails with `storage_no_host` instead of pretending it landed. A
  host-mediated store for the native slot is a separate package; the decision record
  (`docs/decisions/PLUGIN_SURFACE_PAGE_STORAGE.md`) says so.

### 3d. A memory provider (manifest v2)

A version 2 bundle may point the agent's memory at a backend of its own. It declares one
descriptor, `core/plugin_memory_contract.py` holds every rule, and the kernel never imports
the bundle:

```json
"permissions": { "tool_families": ["network"], "data_roots": [] },
"capabilities": {
  "memory": {
    "id": "team-memory",
    "transport": "kepta-bridge",
    "url": "http://127.0.0.1:3010",
    "scope": "team",
    "description": "Shared notes for the team."
  }
}
```

| Field | Rule |
|---|---|
| `id` | Lowercase slug, at most 40 characters; `kepta` and `kepta-bridge` belong to the kernel and are refused |
| `transport` | `kepta-bridge`, the HTTP protocol `core/memory_kepta_bridge.py` implements — a provider answers inside the turn, where no plugin module may be imported |
| `url` | http(s), no credentials, no fragment. This URL is the whole reach of the provider |
| `scope` | Optional slug, written into every call; without it the workspace hash names the scope |
| `description` | Optional, and non-empty when present |

`permissions.tool_families` has to declare `network`, or the bundle is quarantined. Two
bundles declaring one `id` make that id contested, and contested and unknown are answered
the same way — both fall back. Registration is the manifest scan the tool gate already runs
(`core/plugin_runtime.py`), so a mount or an edit retires the table.

A user reaches a declared provider through `EPHE_MEMORY_PROVIDER=<id>` or through the
written record (`~/.ephe/memory/provider.json`). With the bundle switched off the env value
is ignored with a warning, and a record naming that provider stays on disk while `kepta`
serves the memory: the choice applies again the moment the bundle is back. The settings
route still offers the two kernel ids, so a declared provider is selected by env or record
in this version.

## 4. Vendored libraries (the offline runtime)

A surface that needs a third-party renderer or game runtime ships it inside its own
directory. No CDN path exists: the `Content-Security-Policy` the surface route serves
keeps `script-src 'self'` closed for every capability name in
`core/plugin_ui_capabilities.py`, so a `<script src="https://…">` in a generated
document loads nothing, and `fetch` to a remote host is refused by the same header.
The offline path below is the one that answers.

1. Put the file under `vendor/`, at or below the directory of `components.ui.entry`
   (a surface resolves relative URLs against its own directory and the asset route
   refuses a `..` segment, so a library above the entry document has no URL that
   reaches it).
2. Declare it in `ephe-libraries.json`, beside `ephe-plugin.json`: `name` (slug),
   `version`, `path`, `kind` (`script`, `module`, `wasm`) and the `sha256` of the
   bytes that ship.
3. Load it relatively from the entry: `<script type="module" src="vendor/renderer.mjs">`.

```json
{
  "schema": 1,
  "libraries": [
    {
      "name": "renderer",
      "version": "0.169.0",
      "path": "ui/vendor/renderer.mjs",
      "sha256": "<64 hex of the shipped bytes>",
      "kind": "module"
    }
  ]
}
```

What validation refuses, each one quarantining the whole plugin: a hash that does not
match, a declared file that never shipped, a file under `vendor/` nobody declared, a
`.wasm` entry whose surface did not declare the `wasm` capability, a file past the
8 MiB per-file cap, and a bundle past the 24 MiB total. The two caps are stated in
`core/plugin_libraries.py`; the per-file number is the same ceiling the asset route
already applies to any file it reads (`MAX_SURFACE_ASSET_BYTES`), and the totals come
from measured engine bundles — `docs/PLUGINS.md` carries the byte counts and where
they came from.

The hash answers one question: did the bytes change since they were declared? It
detects drift (an editor, a packing step, a swapped file on disk). A declared hash
says nothing about whether the code is welcome, so keep the library small, keep it
versioned, and expect the review to read it.

A `.wasm` file needs `components.ui.capabilities: ["wasm"]`: the route only hands
those bytes to a mount whose policy may compile them.

## 5. Distribution through the store

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

## 6. Debugging table

| Symptom | Most likely cause | First look |
|---|---|---|
| The plugin is missing from `ephe plugin list` | the folder is not under the plugins root, or its name ≠ `manifest.name` (a hard rule) | `ephe plugin list --json`: a quarantined folder is an `installed` row with `state: "error"` and its reason |
| enabled, but the skills/commands are empty | `components` declared incompletely, or the master switch is off | complete `components`; `POST /api/plugins/master` |
| Quarantine after an edit | the E4b drift gate: a signature record exists and the content changed | is `plugins.plugin_signature_check` ON? re-sign or update `ephe-plugin.sig.json` |
| The command does not appear in the composer | `name` without the leading `/`? only validated plugins return entries | `GET /api/plugins/commands` |
| 404/43-style load errors | nested folder: `plugins/<x>/<name>/ephe-plugin.json` | exactly one level: `plugins/<name>/ephe-plugin.json` |

## 7. Checklist before the release pack

- [ ] `name` = folder name, slug-conformant (`^[a-z0-9][a-z0-9-]*$`), `version` = `X.Y.Z`
- [ ] every declared skill pack has `skills/<pack>/SKILL.md`
- [ ] every file under `vendor/` is declared in `ephe-libraries.json`, and every
      `sha256` there was computed from the bytes that ship in this pack (§4)
- [ ] tool families kept minimal; only real TOOL_MAP names in `components.agents.tools`
- [ ] the ZIP's `sha256` computed freshly and maintained in `plugin-marketplace.json`
- [ ] the signature record (`ephe-plugin.sig.json`) matches the current `ephe plugin list` version
- [ ] dry run: master-disable → `GET /api/plugins/commands` goes empty; master-enable → entries back

## See also

- `docs/PLUGINS.md` — the complete manifest format v1, enforcement semantics, API table
