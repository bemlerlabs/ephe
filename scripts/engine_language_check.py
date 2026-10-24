#!/usr/bin/env python3
"""English-first gate for engine-facing prompt content.

Scans every prompt surface the engine sees: manifest and command text, golden
inputs, notes and expectations, skill frontmatter and the System Prompt,
Example, Test and Reference sections, the example/reference sidecars and the
pack descriptions. A `language: de` marker only exempts a pack named in the
explicit German-pack allowlist; a marker anywhere else is itself a finding.

English text that happens to contain words like "die" is not German: a finding
needs a German-specific character, an unambiguous German word, or two distinct
ambiguous function words.

    python3 scripts/engine_language_check.py [--write-baseline]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "scripts" / "engine-language-baseline.json"

GERMAN_CHARS = re.compile(r"[äöüßÄÖÜ]")
#: Unambiguous in English; stems keep inflected forms covered.
STRONG = re.compile(
    r"(?i)\b(?:"
    r"und|nicht|bitte|für|fuer|über|ueber|auch|oder|werden|wird|sind|ist|"  # language-gate: ignore
    r"zum|zur|vom|beim|einen|einem|einer|eines|bist|du|ich|wir|dass|wenn|"  # language-gate: ignore
    r"dann|noch|nur|schon|jetzt|hier|dort|dieser|diese|dieses|"  # language-gate: ignore
    r"erstell\w*|erzeug\w*|prüf\w*|pruef\w*|überprüf\w*|ueberpruef\w*|"
    r"zähl\w*|zaehl\w*|finde|fass\w*|übersetz\w*|uebersetz\w*|"
    r"bericht\w*|protokoll\w*|datei\w*|quellen\w*|tabelle\w*|"
    r"schreib\w*|öffne\w*|oeffne\w*|speicher\w*|lösch\w*|loesch\w*|"
    r"analysier\w*|vergleich\w*|erklär\w*|erklaer\w*|berechne\w*|"
    r"extrahier\w*|änder\w*|aender\w*|entwickl\w*|baue|zeige|suche|"
    r"wähl\w*|waehl\w*|entfern\w*|aktualisier\w*|konfigurier\w*|teste|"
    r"reparier\w*|simulier\w*|beschreib\w*|nenne|liste|gib|führ\w*|"
    r"fuehr\w*|starte|stoppe"
    r")\b"
)
#: Ambiguous with English. Lowercase only, so "MIT" stays a licence.
WEAK = re.compile(r"\b(der|die|das|den|dem|des|ein|eine|mit)\b")  # language-gate: ignore
MARKER = re.compile(r"""(?i)["']?(?:language|lang)["']?\s*:\s*["']?de["']?""")
SECTION = re.compile(
    r"^##\s+(System Prompt|Example|Test|Reference)\b[^\n]*\n(.*?)(?=^##\s|\Z)",
    re.MULTILINE | re.DOTALL,
)
SECTION_KIND = {
    "System Prompt": "system-prompt",
    "Example": "example",
    "Test": "test",
    "Reference": "reference",
}
FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|\Z)", re.DOTALL)

#: Explicit German-language packs, name -> reason. Built-ins do not belong here.
GERMAN_PACKS: dict[str, str] = {}


def is_german(text: str) -> bool:
    if GERMAN_CHARS.search(text) or STRONG.search(text):
        return True
    return len({match.group(0) for match in WEAK.finditer(text)}) >= 2


def _show(text: str, limit: int = 80) -> str:
    return " ".join(text.split())[:limit]


def _has_marker(text: str) -> bool:
    return bool(MARKER.search(text))


def _finding(relative: Path, kind: str, text: str) -> dict:
    return {"path": str(relative), "kind": kind, "text": _show(text)}


def _marker_block(relative: Path, pack: str, text: str, findings: list[dict]) -> bool:
    """True when the file is exempt. A marker outside the allowlist is red."""
    if not _has_marker(text):
        return False
    if pack in GERMAN_PACKS:
        return True
    findings.append(_finding(relative, "language-marker", text))
    return False


def _scan_markdown(path: Path, relative: Path, findings: list[dict]) -> None:
    text = path.read_text(encoding="utf-8")
    if _marker_block(relative, path.parent.name, text, findings):
        return
    front = FRONTMATTER.match(text)
    if front:
        fields = [
            line.split(":", 1)[1].strip()
            for line in front.group(1).splitlines()
            if line.startswith(("description:", "trigger:"))
        ]
        if any(is_german(value) for value in fields):
            findings.append(_finding(relative, "frontmatter", "\n".join(fields)))
    for match in SECTION.finditer(text):
        if is_german(match.group(2)):
            findings.append(_finding(relative, SECTION_KIND[match.group(1)], match.group(2)))


def _scan_plain(path: Path, relative: Path, kind: str, findings: list[dict]) -> None:
    text = path.read_text(encoding="utf-8")
    if _marker_block(relative, path.parent.parent.name, text, findings):
        return
    if is_german(text):
        findings.append(_finding(relative, kind, text))


def _scan_manifest(path: Path, relative: Path, findings: list[dict]) -> None:
    text = path.read_text(encoding="utf-8")
    if _marker_block(relative, path.parent.name, text, findings):
        return
    try:
        manifest = json.loads(text)
    except ValueError:
        return
    for field in ("description", "displayName"):
        value = str(manifest.get(field) or "")
        if is_german(value):
            findings.append(_finding(relative, "manifest", value))
    components = manifest.get("components") or {}
    for command in components.get("commands") or []:
        if not isinstance(command, dict):
            continue
        for field, kind in (("description", "command-description"), ("template", "command")):
            value = str(command.get(field) or "")
            if is_german(value):
                findings.append(_finding(relative, kind, value))
    golden = path.parent / "prompts" / "golden.jsonl"
    if not golden.is_file():
        return
    golden_relative = golden.relative_to(path.parents[2])
    for line in golden.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except ValueError:
            continue
        for field in ("input", "note"):
            value = str(case.get(field) or "")
            if is_german(value):
                findings.append(_finding(golden_relative, "golden", value))
        expect = case.get("expect") or {}
        for value in expect.get("any") or []:
            if is_german(str(value)):
                findings.append(_finding(golden_relative, "golden", str(value)))


def _scan_pack_index(path: Path, relative: Path, findings: list[dict]) -> None:
    try:
        packs = json.loads(path.read_text(encoding="utf-8")).get("packs") or []
    except (OSError, ValueError):
        return
    for pack in packs:
        text = f"{pack.get('title') or ''}\n{pack.get('description') or ''}".strip()
        if is_german(text):
            findings.append(_finding(relative, "pack-description", text))


def scan(root: Path = ROOT) -> list[dict]:
    findings: list[dict] = []
    for manifest_path in sorted((root / "plugins").glob("*/ephe-plugin.json")):
        _scan_manifest(manifest_path, manifest_path.relative_to(root), findings)
    skill_paths = sorted((root / "skills").glob("*/SKILL.md"))
    skill_paths += sorted((root / "plugins").glob("*/skills/*/SKILL.md"))
    for skill_path in skill_paths:
        _scan_markdown(skill_path, skill_path.relative_to(root), findings)
    sidecars = sorted((root / "skills").glob("*/examples/*.md"))
    sidecars += sorted((root / "plugins").glob("*/skills/*/examples/*.md"))
    for sidecar in sidecars:
        _scan_plain(sidecar, sidecar.relative_to(root), "example-file", findings)
    references = sorted((root / "skills").glob("*/references/*.md"))
    references += sorted((root / "plugins").glob("*/skills/*/references/*.md"))
    for reference in references:
        _scan_plain(reference, reference.relative_to(root), "reference-file", findings)
    pack_index = root / "skills" / "pack-index.json"
    if pack_index.is_file():
        _scan_pack_index(pack_index, pack_index.relative_to(root), findings)
    return findings


def counts(findings: list[dict]) -> Counter:
    return Counter(f"{finding['path']}::{finding['kind']}" for finding in findings)


def growth(findings: list[dict], baseline: dict[str, int]) -> list[str]:
    current = counts(findings)
    return [
        f"{key}: {count} > baseline {baseline.get(key, 0)}"
        for key, count in sorted(current.items())
        if count > baseline.get(key, 0)
    ]


def _write_baseline(findings: list[dict]) -> None:
    payload = {"version": 1, "counts": dict(sorted(counts(findings).items()))}
    BASELINE.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write-baseline", action="store_true", help="record the current findings")
    args = parser.parse_args(argv)
    findings = scan()
    if args.write_baseline:
        _write_baseline(findings)
        print(f"engine-language: baseline written with {len(findings)} finding(s)")
        return 0
    by_kind: dict[str, int] = {}
    for finding in findings:
        by_kind[finding["kind"]] = by_kind.get(finding["kind"], 0) + 1
    baseline: dict[str, int] = {}
    if BASELINE.is_file():
        try:
            baseline = json.loads(BASELINE.read_text(encoding="utf-8")).get("counts") or {}
        except (OSError, ValueError):
            baseline = {}
    problems = growth(findings, baseline)
    for finding in findings[:40]:
        print(f"  {finding['path']} [{finding['kind']}]: {finding['text']}")
    if len(findings) > 40:
        print(f"  ... and {len(findings) - 40} more")
    for problem in problems[:40]:
        print(f"  NEW: {problem}")
    print(
        f"engine-language: {len(findings)} finding(s) {by_kind}; "
        f"{sum(baseline.values())} baselined, {len(problems)} new"
    )
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
