# Plugins (Extensions 1.0)

Skills, slash commands, helper-agent profiles, event hooks and MCP tool servers ship as plugins: a
directory with an `ephe-plugin.json` manifest ([`PLUGINS.md`](PLUGINS.md)), versioned, content-hashed,
and switchable. A version 2 manifest may declare one turn-end hook (`components.hooks.turn_end`);
the other hook events live in `~/.ephe/hooks.json` and stay a separate contract.

- **Runtime.** Disabling a plugin removes its tools, commands, and skills from the agent loop on the
  very next turn. The master switch in Settings → Plugin Store returns Ephe to stock behavior. Every
  gate decision is audit-logged.
- **Fail-closed.** Permission families are declared in the manifest and validated fail-closed;
  mutating tools still pass the approval gates; a freshly installed plugin lands disabled unless you
  opt in (`plugin_autorun`).
- **Signature records.** ES256 signatures over the canonical content hash. A bundle that carries
  `ephe-plugin.sig.json` mounts as `signed`; a signature-verified plugin that changes on disk cannot
  be re-enabled: the drift gate answers 409 and writes an audit line. None of the bundled packs
  carries a record, so they mount as local content.
- **17 first-party bundles ship in-repo** (`plugins/`): the nine plugins and seven presets the
  catalogue lists, plus `countdown`, the reference bundle for a declarative surface.
  Plugins: browser-use, code-shell, documents, local-document-factory, memory, presentations,
  private-research-notebook, spreadsheets, web-research.
  Presets: guide, image-studio, mcp-connector, plugin-creator, skill-creator, vision, voice.
  The catalogue also offers five first-party skill packs and one bundled third-party pack
  (Superpowers, MIT); the 51 built-in skills are separate ([`SKILLS.md`](SKILLS.md)).
- **CLI:** `ephe plugin list | enable | disable | install | remove`.
- **Switching in:** `ephe import <dir>` imports persona, skills, tool servers, and settings from an
  existing local agent setup. It plans first, writes additively, and leaves everything disabled until
  you enable it ([`docs/SWITCHING.md`](SWITCHING.md)).
