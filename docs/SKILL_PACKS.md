# Ephe — skill packs (R16)

A skill pack is a directory with one `SKILL.md` (YAML frontmatter + Markdown body) plus optional `examples/` and `references/` subfolders. All built-in skills (`skills/<name>/SKILL.md`) and all installed user packs (`~/.ephe/skills/<name>/SKILL.md`) use the same format — the loader (`core/skills.py`) reads both, and a user pack overrides a built-in of the same name.

## The SKILL.md format

```markdown
---
name: my-skill              # required; must match the directory name
version: "1.2.0"            # semantic versioning (install/update semantics)
trigger: /myskill           # required; a unique slash trigger
description: "Short description"
tools: [web_search, create_pdf]
when_to_use: [report, research]          # optional, positive fuzzy routing
when_not_to_use: [shell command]         # optional, negative fuzzy routing
quality_profile: artifact                # standard | artifact
artifact_types: [pdf]                    # optional
allowed_tools: [web_search, create_pdf]  # a narrow tool gate
---
# my-skill

**Trigger**: /myskill
**Description**: Short description
**Tools**: web_search, create_pdf

## System Prompt
...

## Test
**Input**: …
**Expect Tool**: web_search
**Expect Contains**: …
```

The body may still carry the classic `**Field**:` lines (backwards compatibility with flat skills); the frontmatter wins. User skills created through `POST /api/skills` stay flat files and count as `1.0.0`.

## Management (settings → skills, REST)

| Action | Route | Behavior |
|---|---|---|
| List | `GET /api/skills` | incl. `version`, `disabled` |
| Install | `POST /api/skills/install` | multipart `file` (zip/tgz/tar) + `force` |
| Install (URL) | `POST /skills/install/url` | `{url, force}` — an explicit user action |
| Disable/enable | `POST /api/skills/{name}/disable` `/enable` | persisted in `~/.ephe/skills_state.json`; a disabled skill is never resolved automatically but stays listed |
| Verify signature | `GET /api/skills/{name}/verify` | `{signed, verified, reason, kid}` — fail-soft; an unsigned or flat skill answers `signed=false`, a missing skill answers 404 |
| Delete | `DELETE /api/skills/{name}` | user packs/files only; built-ins are protected |

### Install guards (conservative, release bar)

- Path traversal (`..`), absolute paths, backslashes, dotfiles and symlinks/hardlinks are rejected.
- Extensions allowlisted: `.md .txt .json .yaml .yml .csv`.
- Caps: 10 MB archive, 20 MB unpacked, 500 entries, 2 MB per file.
- `name` must follow `^[a-z0-9][a-z0-9_-]{0,63}$` and match the directory name; the frontmatter has to yield a valid skill.
- Built-in names can never be overwritten (403).
- Update semantics: same version → skip; lower version → 409; higher version or `force=true` → replaces the user pack.

Tests: `tests/test_skill_pack_install.py`; the format gate: `tests/test_builtin_skills_quality.py` (every pack declares name + semantic version).

## Signed packs (W3-14)

A pack can carry a signature. It reuses the plugin trust machinery verbatim
(`core/plugin_signing.py`): the same RFC 8785 canonical JSON and the same ES256
(SECP256R1) signatures, verified against the same trust anchors — the repo
`plugins/first-party.pub.pem` (when shipped) and `~/.ephe/trusted-keys/*.pub.pem`.

- The record lives inside the pack as `ephe-skill.sig.json` and binds the pack
  identity (SKILL.md `name` + `version`) to a hash over the whole pack:
  `{"alg":"ES256","kid":…,"name":…,"version":…,"sha256":<pack hash>,"signature":…}`.
- The record itself and the install-time note (`.ephe-install.json`) are
  EXCLUDED from that hash, so signing and installing do not change the hash the
  signature covers. A record hidden in a subdirectory is refused — the hash does
  not cover it.
- Verify path: `GET /api/skills/{name}/verify` → `{signed, verified, reason,
  kid}`; the skill list/detail also carry a `signature` field for a signed pack.
  Verification is fail-soft (a drifted or foreign-signed pack is reported, never
  silently trusted) and needs no signature for an unsigned pack.
- Install is fail-closed for a pack that *declares* a signature: if the record
  does not verify against the trusted keys, the install is rejected (422) and
  nothing is written. Unsigned packs install exactly as before.
- Signing a pack is a publisher action (`core/skill_signing.sign_skill_pack`);
  the private key never reaches the server.

Tests: `tests/test_skill_signing.py`.
