# Plugins (Extensions 1.0)

Skills, slash commands, helper-agent profiles, event hooks, and MCP tool servers ship as plugins: a
directory with an `ephe-plugin.json` manifest ([`PLUGINS.md`](PLUGINS.md)), versioned, content-hashed,
and switchable.

- **Runtime.** Disabling a plugin removes its tools, commands, and skills from the agent loop on the
  very next turn. The master switch in Settings → Plugin Store returns Ephe to stock behavior. Every
  gate decision is audit-logged.
- **Fail-closed.** Permission families are declared in the manifest and validated fail-closed;
  mutating tools still pass the approval gates; a freshly installed plugin lands disabled unless you
  opt in (`plugin_autorun`).
- **Signed.** ES256 signatures over the canonical content hash. A signature-verified plugin that
  changes on disk cannot be re-enabled: the drift gate answers 409 and writes an audit line.
- **14 first-party bundles ship in-repo** (`plugins/`): browser-use, code-shell, documents, guide,
  image-studio, mcp-connector, memory, plugin-creator, presentations, skill-creator, spreadsheets,
  vision, voice, web-research.
- **CLI:** `ephe plugin list | enable | disable | install`.
- **Switching in:** `ephe import <dir>` imports persona, skills, tool servers, and settings from an
  existing local agent setup. It plans first, writes additively, and leaves everything disabled until
  you enable it ([`docs/SWITCHING.md`](SWITCHING.md)).
