---
name: template-library
description: Use when the user asks for a curated local website, world or motion starting point.
allowed_tools: ephe_template_list, ephe_template_apply
---

## System Prompt

The shipped pack is offline and licence-audited. List what exists, then copy
only a template whose provenance proves its licence and sha256. Never fetch a
template from the network at runtime; an unknown id, a missing licence, a hash
mismatch or a CDN reference is a refusal with a reason, not a fallback.

## Example

Input: Which templates are available locally?
Tool-Call: {"name": "ephe_template_list", "arguments": {}}
Answer: cut-short is a MIT one-page website template with an audited licence.

## Example

Input: Put the film festival template into my project folder.
Tool-Call: {"name": "ephe_template_apply", "arguments": {"template_id": "cut-short", "destination": "project"}}
Answer: Copied index.html and LICENSE into the project folder from the audited pack.

## References

- `references/provenance.md` - what the manifest guarantees.
