"""Ephe — self-organised learning (SOL).

Three phases, all deterministic and all on disk in the workspace:

- orientation: `organizer` reads the workspace manifests once per change and
  keeps a compact map under `.ephe/learning/map.json`;
- action: `reflector` turns a failed tool round into a structured reflection
  block for the next model call, and applies what the project already knows;
- consolidation: `consolidator` writes the rule that ended a failure into
  `.ephe/learning/heuristics.md`, where the user can read, edit and delete it.

`session` binds the three to one turn; `context` composes the prompt block.
"""
