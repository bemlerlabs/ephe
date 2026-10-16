# PR/FAQ — Ephe Extensions 1.0

> Working-backwards artifact (playbook rule 1): written BEFORE implementation
> of the E-waves. If this document stops being true, the waves have drifted.
> Status at writing: E0 draft — E1 (runtime wiring) not yet implemented.

---

## Press Release (hypothetical, dated after E6)

**Ephe ships Extensions 1.0: a plugin system where every switch actually switches**

*Bad Liebenzell, Schwarzwald —* Ephe, the ephemeral local AI agent, today
announced Extensions 1.0, a plugin system built on one uncomfortable honesty
principle: **a toggle that toggles nothing gets removed.**

Ephe Extensions bundles capabilities into single installable plugins. One
plugin can carry skill packs, slash commands, helper-agent profiles, event
hooks, and tool servers (MCP) — versioned, signed, and switchable. The store
ships with first-party plugins for the jobs people actually do: research,
documents, coding, channels, memory.

Three properties distinguish the system:

1. **Runtime honesty.** Turning a plugin off removes its tools, commands, and
   skills from the agent loop on the very next turn. Nothing keeps running in
   the dark. The Plugins master switch returns Ephe to its stock behavior —
   auditable, because every gating decision is recorded in the audit log.
2. **Conservative by default.** Third-party plugins must declare the tool
   families and data paths they touch; mutating tools still pass the existing
   approval gates. Signature checking (RFC 8785 canonicalization + ES256, the
   same machinery as the ephemeral cell) is on by default.
3. **No lock-in, in both directions.** Ephe reads the open skill-pack format
   natively and ships importers that bring settings, personas, skills, and
   tool-server configs over from the agent tools people use today. Leaving is
   just as plain: every plugin artifact is a plain directory of text files.

"The agent market taught users to distrust plugin stores — stores that list
capabilities that do nothing, or that keep phoning home after you switch them
off," the team said. "Extensions 1.0 is our answer: measured, not promised,
and off means off."

## FAQ

**Q: What exactly is a plugin?**
A directory with a manifest (`ephe-plugin.json`): metadata (name, version,
permissions) plus any mix of `skills/`, `commands/`, `agents/`, `hooks.json`,
and `mcp.json`. A bare skill pack remains a valid one-component plugin —
backward compatibility with the existing 51 built-in packs is a release gate.

**Q: What happens when I disable a plugin?**
Its registered components stop resolving: tools disappear from the agent's
schema list, commands from the palette, skills from routing, hooks from the
event bus. Sessions keep their history. The next turn runs without the plugin.

**Q: Can I turn the whole system off?**
Yes — the master switch in Settings → Plugins. Off means stock Ephe: built-in
tools only, no third-party resolution, no hook execution.

**Q: How do permissions work?**
Manifests declare tool families (read / write / shell / network / memory) and
optional data roots. Declared-but-absent capabilities fail closed. Anything
mutating still hits the approval gate exactly as stock tools do; plugins get
no bypass.

**Q: How does signing work?**
Catalog plugins carry a sha256 of the artifact; first-party releases are
ES256-signed over the RFC 8785 canonical manifest. Signature check is a
setting (default on); a mismatch quarantines the plugin, it does not run.

**Q: Why build this at all — aren't 51 skill packs enough?**
Skill packs change *what the agent knows*. Extensions change *what the agent
is*. Commands, helper agents, hooks, and tool servers are structural — they
belong in one versioned, signed, switchable unit instead of four half-visible
mechanisms.

**Q: What does the audit log record?**
Plugin enable/disable, gate decisions (tool hidden / allowed), hook
executions, and signature verdicts — same append-only JSONL as tool approvals.

**Q: What is deliberately NOT in 1.0?**
No network marketplace sync in the background (refresh is manual and
throttled), no plugin-side UI rendering, no auto-updates (semver ranges with
explicit user action), no revenue/share mechanics.

**Q: How do I bring my existing setup over?**
`ephe import` reads the config, persona, skills, and tool-server definitions
from a reference-client directory and maps them onto Ephe's formats, showing
a diff before writing anything. Nothing is auto-enabled: imported plugins
start disabled until you switch them on.
