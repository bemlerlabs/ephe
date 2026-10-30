"""S4 — static verification for a marketplace artifact before it is enabled.

Three checks that match what actually goes wrong with agent tooling: a tool
description that carries instructions (the documented poisoning shape), a
launch line that fetches unpinned code, and environment variables that carry
secrets. The verdict rides the install result and the audit line; a
high-severity finding refuses the install before anything is enabled.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

HIGH = "high"
INFO = "info"

#: Phrases that turn a description into an instruction to the model.
_INSTRUCTION_MARKERS = (
    "ignore previous",
    "ignore all previous",
    "disregard the",
    "do not tell",
    "don't tell",
    "without telling",
    "reveal your",
    "system prompt",
    "send the contents",
    "exfiltrate",
)

#: A package manager name without a pinned version, as the first command word.
_UNPINNED = re.compile(r"\b(?:npx|uvx|pip3?|npm)\s+(?:-y\s+)?(?!\S+@\d)([a-z0-9@/._-]+)")

#: Download directly into a shell.
_SHELL_PIPE = re.compile(r"\b(?:curl|wget)\b[^|]{0,200}\|\s*(?:ba|z|da)?sh\b")

_TEXT_SUFFIXES = {".json", ".md", ".yaml", ".yml", ".toml"}


def _walk_env(payload: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == "env" and isinstance(value, dict):
                names.update(str(name) for name in value)
            names.update(_walk_env(value))
    elif isinstance(payload, list):
        for item in payload:
            names.update(_walk_env(item))
    return names


def verify_artifact(root: Path) -> dict[str, Any]:
    """Scan an extracted artifact directory; return the verdict with findings."""
    findings: list[dict[str, str]] = []
    env_names: set[str] = set()
    root = Path(root)
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in _TEXT_SUFFIXES:
            continue
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        lowered = text.lower()
        for marker in _INSTRUCTION_MARKERS:
            if marker in lowered:
                findings.append(
                    {"class": "description-instructions", "severity": HIGH, "file": rel, "marker": marker}
                )
                break
        for match in _SHELL_PIPE.finditer(lowered):
            findings.append(
                {"class": "shell-download", "severity": HIGH, "file": rel, "marker": match.group(0)[:80]}
            )
        if path.suffix.lower() == ".json":
            try:
                env_names.update(_walk_env(json.loads(text)))
            except ValueError:
                pass
        elif path.name == "SKILL.md":
            for line in text.splitlines():
                match = _UNPINNED.search(line.lower())
                if match:
                    findings.append(
                        {"class": "unpinned-install", "severity": INFO, "file": rel, "marker": match.group(0)[:80]}
                    )
                    break
    high = [one for one in findings if one["severity"] == HIGH]
    verdict = "refused" if high else ("checked" if findings else "checked-clean")
    return {
        "verdict": verdict,
        "findings": findings,
        "env": sorted(env_names),
    }


def write_verdict(root: Path, verdict: dict[str, Any]) -> None:
    """Persist the verdict beside the artifact so installed rows can show it."""
    target = Path(root) / "VERIFY.json"
    try:
        target.write_text(json.dumps(verdict, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def read_verdict(root: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads((Path(root) / "VERIFY.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def verify_entry(fields: dict[str, str]) -> dict[str, Any]:
    """Y2 — the sandbox-less rehearsal: scan what the catalog publishes about an
    entry (title, description, launch line) with the same markers the artifact
    check uses. A live connector handshake is a separate, heavier seam; this
    answers before anything is downloaded or started."""
    findings: list[dict[str, str]] = []
    for field, value in fields.items():
        lowered = str(value or "").lower()
        for marker in _INSTRUCTION_MARKERS:
            if marker in lowered:
                findings.append(
                    {"class": "description-instructions", "severity": HIGH, "file": field, "marker": marker}
                )
                break
        for match in _SHELL_PIPE.finditer(lowered):
            findings.append(
                {"class": "shell-download", "severity": HIGH, "file": field, "marker": match.group(0)[:80]}
            )
        if field in {"install_hint", "spec"}:
            match = _UNPINNED.search(lowered)
            if match:
                findings.append(
                    {"class": "unpinned-install", "severity": INFO, "file": field, "marker": match.group(0)[:80]}
                )
    high = [one for one in findings if one["severity"] == HIGH]
    verdict = "refused" if high else ("checked" if findings else "checked-clean")
    return {"verdict": verdict, "findings": findings, "mode": "static"}
