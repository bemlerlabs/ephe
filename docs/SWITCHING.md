# Switching to Ephe

You already run a local agent setup and want to move to Ephe? One command
prepares the move — nothing is written until you say so, and nothing you
import runs until you switch it on.

```bash
ephe import ~/path-to-your-old-agent-setup          # dry plan (no writes)
ephe import ~/path-to-your-old-agent-setup --apply  # actually import
```

## What gets imported

| Artifact in your old setup | Detected by | Lands as |
|---|---|---|
| Persona file (`SOUL.md`, `persona.md`, `AGENT.md`, `IDENTITY.md`) | exact file name | `~/.ephe/persona.md` — **never overwrites** an existing persona |
| Skill packs (`<name>/SKILL.md` trees) | directory structure | `~/.ephe/skills/<name>/` — **DISABLED**; enable in Settings → Skills |
| Tool-server config (`.mcp.json`, `mcp.json` with `mcpServers`) | structure | merged into `~/.ephe/mcp.json` as Ephe spec strings (existing servers win) |
| Settings file (`config.yaml`/`config.yml`/`config.json`) | generic keys (`temperature`, `top_p`, `max_tokens`, `context_window`, `timezone`) | mapped onto Ephe's deep settings; everything unmapped is reported and left out |

The importer is deliberately vendor-neutral: it matches structure, not
product names, so most local agent layouts import directly.

## What does NOT transfer

- Engine choice: Ephe has **no silent default** — you pick the engine in the
  app (local Ollama, remote Ollama, or any OpenAI-compatible endpoint).
- Plugins/extensions of other products have no runtime in Ephe; their
  skills/portions import where they map to the open skill-pack format.
- Message history stays where it is (privacy by design — Ephe does not read
  other apps' databases).

## After importing

1. `ephe configure` (or the in-app onboarding) to pick your engine.
2. Settings → **Skills** → enable the imported packs you actually want.
3. Settings → **Expert** → check the mapped generation values.
4. Optional: Settings → **MCP** → review the imported tool servers.

Everything imported is visible, nothing is hidden, and everything stays
switchable — off means off.
