# Persona packs

A persona is one markdown file (`~/.ephe/persona.md`). A **persona pack** is
that file in a form you can hand to someone else: one self-describing JSON
document that carries its own identity and integrity.

## The format

`core/persona_pack.py`, `format: "ephe-persona"`, `version: 1`. File suffix
`.ephe-persona.json`.

```json
{
  "author": "Ada",
  "created": "2026-10-11T00:00:00Z",
  "description": "Warm, terse, no filler.",
  "format": "ephe-persona",
  "name": "marvin",
  "persona": "## Voice\n- Warm, brief, honest.",
  "persona_sha256": "…",
  "title": "Marvin",
  "version": 1
}
```

| Field | Required | Meaning |
|---|---|---|
| `format` | yes | `ephe-persona`; anything else is refused |
| `version` | yes | `1`; a different integer is refused before any field is judged |
| `name` | yes | slug (`[a-z0-9-]`, ≤64) — the pack's stable identity and filename |
| `persona` | yes | the markdown body, ≤8000 chars, `[persona]` marker stripped |
| `persona_sha256` | yes | sha256 of the canonical body, checked on import |
| `title`, `description`, `author`, `created` | no | attribution (≤120/≤280/≤120/≤40) |
| `signature` | no | ES256 record over every field but itself |

`dumps()` is deterministic (sorted keys, fixed indent), so two identical packs
share bytes.

## Python API

```python
from core import persona_pack as pp

# export the live persona, then write it out
pack = pp.export_current(title="Marvin", description="Warm, terse.")
open(pp.filename(pack), "w").write(pp.dumps(pack))

# import someone else's pack
summary = pp.import_pack(open("marvin.ephe-persona.json").read())
```

- `pp.validate(raw) -> (ok, reason)` never throws; `pp.load(raw)` returns the
  canonical pack or raises `PersonaPackError(reason)`.
- `pp.import_pack(raw, overwrite=False)` writes `~/.ephe/persona.md` through the
  same atomic, capped, 0600 writer the editor uses. It is additive: an existing
  persona is kept unless `overwrite=True`, and it refuses an oversized or
  tampered pack before touching disk.

## Signing

A pack signs with the plugin trust machinery verbatim
(`core/plugin_signing.py`: RFC 8785 canonical JSON + ES256 over every field but
`signature`), so it verifies against the same `~/.ephe/trusted-keys/*.pub.pem`
anchors as a plugin or skill pack.

```python
signed = pp.sign_pack(pack, private_pem, kid="first-party")
ok, reason = pp.verify_pack(signed, trusted_public_pems)
```

`verify_pack` never throws: any problem is `(False, reason)` — `integrity`,
`unsupported algorithm`, `no_trusted_key`, `signature not from a trusted key`.

## Fail-closed rules

Every field is checked in order and the first problem stops the import: wrong
`format`, unknown/missing/mistyped `name`, an unknown top-level key, an empty or
oversized `persona`, or a `persona_sha256` that does not match the body. There is
no partial import — a pack either imports whole or not at all.

## Not wired yet

The share/import logic is library-only. A Settings "Export persona" button and
an `ephe persona export|import` CLI verb are the obvious next step, but they
belong to the settings-route and CLI owners.
