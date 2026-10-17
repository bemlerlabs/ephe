"""Ephe — Reference-client import (Extensions wave E6)
core/importer.py

Switching to Ephe is a first-class path. The importer is VENDOR-NEUTRAL: it
detects common local-agent artifacts by STRUCTURE inside a source directory
and maps them onto Ephe's formats:

  persona file      SOUL.md / persona.md / AGENT.md / IDENTITY.md
                    → ~/.ephe/persona.md (additive: an existing persona is
                      NEVER overwritten)
  skill packs       any dir containing <name>/SKILL.md
                    → ~/.ephe/skills/<name>/ AND marked DISABLED in
                      skills_state.json (nothing runs until enabled)
  tool servers      .mcp.json / mcp.json ({"mcpServers": {...}})
                    → merged into ~/.ephe/mcp.json (existing servers win)
  settings file     config.yaml / config.yml / config.json — a few generic
                    keys (temperature, top_p, max_tokens, timezone, theme)
                    map onto deep settings; unmapped keys are reported

Contract: `build_import_plan` is pure (no writes). `apply_import` performs
the additive writes and returns what it did. The CLI `ephe import <dir>`
shows the plan; `--apply` executes it.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

PERSONA_CANDIDATES = ("SOUL.md", "persona.md", "AGENT.md", "IDENTITY.md")
TOOLSERVER_CANDIDATES = (".mcp.json", "mcp.json")
SETTINGS_CANDIDATES = ("config.yaml", "config.yml", "config.json")

#: Generic setting keys we can map onto Ephe deep settings (vendor-neutral
#: key names that appear in many local agent configs).
#: I3-6: 'timezone' dropped out — the register has no timezone field anymore,
#: because it was never read (the schedule's zone lives in EPHE_TIMEZONE,
#: core/scheduler.py).
SETTING_KEY_MAP: dict[str, str] = {
    "temperature": "generation.temperature",
    "top_p": "generation.top_p",
    "max_tokens": "generation.max_tokens",
    "context_window": "generation.context_window",
}


def _config_root() -> Path:
    import os

    return Path(os.environ.get("EPHE_CONFIG_DIR") or str(Path.home() / ".ephe"))


def _find_persona(source: Path) -> Path | None:
    for name in PERSONA_CANDIDATES:
        f = source / name
        if f.is_file():
            return f
    return None


def _find_skill_dirs(source: Path) -> list[Path]:
    """Direct <name>/SKILL.md children plus a nested skills/ directory."""
    out: list[Path] = []
    for pdir in sorted(p for p in source.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()):
        out.append(pdir)
    nested = source / "skills"
    if nested.is_dir():
        for pdir in sorted(p for p in nested.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()):
            if pdir.name not in {p.name for p in out}:
                out.append(pdir)
    return out


def _find_toolservers(source: Path) -> dict[str, str]:
    """Detect tool-server configs. Returns {name_or_url: ephe_spec_string}.

    External files may be dict-style ({mcpServers: {name: {url|command…}}})
    or list-style. Ephe specs are strings: http urls as-is, command objects
    as `stdio:<command> <args…>`."""
    for name in TOOLSERVER_CANDIDATES:
        f = source / name
        if f.is_file():
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            entries: Any
            if isinstance(raw, dict) and isinstance(raw.get("mcpServers"), dict):
                entries = raw["mcpServers"]
            elif isinstance(raw, dict) and isinstance(raw.get("servers"), list):
                entries = raw["servers"]
            elif isinstance(raw, dict):
                entries = raw
            else:
                continue
            out: dict[str, str] = {}
            if isinstance(entries, dict):
                for sname, conf in entries.items():
                    spec = _spec_of(conf)
                    if spec:
                        out[str(sname)] = spec
            elif isinstance(entries, list):
                for i, spec in enumerate(entries):
                    if isinstance(spec, str) and spec.strip():
                        out[f"server-{i + 1}"] = spec.strip()
            if out:
                return out
    return {}


def _spec_of(conf: Any) -> str | None:
    if isinstance(conf, str) and conf.strip():
        return conf.strip()
    if not isinstance(conf, dict):
        return None
    url = conf.get("url")
    if isinstance(url, str) and url.strip():
        return url.strip()
    command = conf.get("command")
    if isinstance(command, str) and command.strip():
        args = conf.get("args")
        arg_str = " ".join(str(a) for a in args) if isinstance(args, list) else ""
        return f"stdio:{command} {arg_str}".strip()
    return None


def _find_settings(source: Path) -> dict[str, Any]:
    for name in SETTINGS_CANDIDATES:
        f = source / name
        if not f.is_file():
            continue
        try:
            if f.suffix == ".json":
                return json.loads(f.read_text(encoding="utf-8"))
            return _flat_yaml_keys(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return {}


def _flat_yaml_keys(text: str) -> dict[str, Any]:
    """Tiny flat `key: value` reader (no YAML dependency, top-level keys only,
    scalars only) — enough for the generic setting map above."""
    out: dict[str, Any] = {}
    for line in text.splitlines():
        if ":" not in line or line.strip().startswith("#") or line.startswith((" ", "\t")):
            continue
        key, _, value = line.partition(":")
        value = value.strip()
        if not value:
            continue
        try:
            out[key.strip()] = json.loads(value)
        except ValueError:
            out[key.strip()] = value
    return out


def build_import_plan(source: Path) -> dict[str, Any]:
    """Pure detection + plan. Never writes."""
    source = Path(source)
    persona = _find_persona(source)
    skill_dirs = _find_skill_dirs(source)
    servers = _find_toolservers(source)
    raw_settings = _find_settings(source)
    mapped = {SETTING_KEY_MAP[k]: v for k, v in raw_settings.items() if k in SETTING_KEY_MAP}
    return {
        "source": str(source),
        "persona": {
            "found": persona is not None,
            "source_file": persona.name if persona else None,
            "target": str(_config_root() / "persona.md"),
        },
        "skills": [
            {"name": p.name, "source": str(p), "target": str(_config_root() / "skills" / p.name), "state": "disabled"}
            for p in skill_dirs
        ],
        "mcp": {"found": bool(servers), "servers": sorted(servers.keys())},
        "settings": {"found": bool(mapped), "mapped": mapped, "unmapped_keys": sorted(set(raw_settings) - set(SETTING_KEY_MAP))},
        "writes": [],  # plan only — an apply fills this with what it did
    }


def apply_import(source: Path) -> dict[str, Any]:
    """Perform the additive import. Returns what it wrote. Never overwrites
    existing Ephe state; imported skills land DISABLED."""
    plan = build_import_plan(source)
    source = Path(source)
    cfg = _config_root()
    wrote: dict[str, Any] = {"persona": False, "skills": [], "mcp_servers": [], "settings": {}}

    persona = _find_persona(source)
    if persona is not None:
        target = cfg / "persona.md"
        if not target.exists():
            cfg.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(persona, target)
            wrote["persona"] = True

    for skill in plan["skills"]:
        target = Path(skill["target"])
        if target.exists():
            continue
        shutil.copytree(skill["source"], target)
        wrote["skills"].append(skill["name"])
    if wrote["skills"]:
        state_file = cfg / "skills_state.json"
        state: dict[str, Any] = {}
        try:
            state = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        disabled = state.get("disabled") if isinstance(state.get("disabled"), dict) else {}
        for name in wrote["skills"]:
            disabled[name] = True
        state["disabled"] = disabled
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            from core.skills import invalidate_skill_cache

            invalidate_skill_cache()
        except Exception:
            pass

    servers = _find_toolservers(source)
    if servers:
        mcp_file = cfg / "mcp.json"
        existing: list[str] = []
        try:
            raw = json.loads(mcp_file.read_text(encoding="utf-8"))
            existing = [str(s) for s in raw.get("servers", [])] if isinstance(raw, dict) else []
        except (OSError, ValueError):
            existing = []
        merged = list(existing) + [s for s in servers.values() if s not in existing]
        mcp_file.parent.mkdir(parents=True, exist_ok=True)
        mcp_file.write_text(json.dumps({"servers": merged}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        wrote["mcp_servers"] = [s for s in merged if s not in existing]

    mapped = plan["settings"]["mapped"]
    if mapped:
        from core import settings_schema as ss

        sections: dict[str, dict[str, Any]] = {}
        for key, value in mapped.items():
            sec_key, _, field_key = key.partition(".")
            if field_key not in ss.SCHEMA:
                continue
            sections.setdefault(sec_key, {})[key] = ss.normalize_field(key, value)
        saved = ss.load_deep_settings()
        for sec_key, fields in sections.items():
            merged = {**fields, **saved.get(sec_key, {})}
            saved[sec_key] = merged
        ss.save_deep_settings(saved)
        wrote["settings"] = mapped

    return wrote
