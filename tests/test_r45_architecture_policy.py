"""
◑ Ephe – W3a (2026-09-24): architecture policy (plan step 1).
tests/test_r45_architecture_policy.py

RULE: tests written BEFORE the implementation (convention from test_r44).

Pins:
1. architecture-policy.yaml exists at the repo root, parses as a mapping, version 1.
2. Exactly 4 modules with the IDs app-frontend, core, server, scripts.
3. Each module carries id/roots/requires/publicEntrypoints/owner.
4. Initially every module is managed:false (baseline freeze comes later).
5. Global thresholds 400/300/12, flags forbidCycles/forbidDeepImports/
   managedOnly true, exceptions [].
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "architecture-policy.yaml"

EXPECTED_IDS = ["app-frontend", "core", "server", "scripts"]
REQUIRED_FIELDS = ["id", "roots", "requires", "publicEntrypoints", "owner"]


def _load() -> dict:
    return yaml.safe_load(POLICY.read_text(encoding="utf-8"))


def test_policy_file_exists_and_parses():
    """GIVEN the repo root WHEN architecture-policy.yaml is loaded
    THEN it is a mapping with version == 1."""
    assert POLICY.is_file(), "architecture-policy.yaml fehlt am Repo-Root"  # language-gate: ignore — asserted failure message literal, not prose
    data = _load()
    assert isinstance(data, dict)
    assert data["version"] == 1


def test_exactly_four_modules_with_required_fields():
    """THEN exactly 4 module IDs in order, each with all required fields."""
    data = _load()
    mods = data["modules"]
    assert [m["id"] for m in mods] == EXPECTED_IDS
    for mod in mods:
        for key in REQUIRED_FIELDS:
            assert key in mod, f"{mod.get('id')}: Feld '{key}' fehlt"  # language-gate: ignore — asserted failure message literal, not prose


def test_all_modules_unmanaged_initially():
    """THEN every module starts out managed:false (the freeze happens in step 11)."""
    data = _load()
    assert all(mod["managed"] is False for mod in data["modules"])


def test_global_thresholds():
    """THEN maxFileLines 400, maxContractLines 300, maxPublicMethods 12."""
    g = _load()["global"]
    assert g["maxFileLines"] == 400
    assert g["maxContractLines"] == 300
    assert g["maxPublicMethods"] == 12


def test_global_flags():
    """THEN forbidCycles/forbidDeepImports/managedOnly are true."""
    g = _load()["global"]
    assert g["forbidCycles"] is True
    assert g["forbidDeepImports"] is True
    assert g["managedOnly"] is True


def test_exceptions_empty_and_module_wiring():
    """THEN exceptions []; app-frontend carries the 5 frontend roots,
    server requires [core]."""
    data = _load()
    assert data["exceptions"] == []
    fe = next(m for m in data["modules"] if m["id"] == "app-frontend")
    assert fe["roots"] == [
        "app/src/components",
        "app/src/hooks",
        "app/src/lib",
        "app/src/store",
        "app/src/pages",
    ]
    assert fe["publicEntrypoints"] == [
        "app/src/components/index.ts",
        "app/src/hooks/index.ts",
        "app/src/lib/index.ts",
        "app/src/store/index.ts",
        "app/src/pages/index.ts",
    ]
    server = next(m for m in data["modules"] if m["id"] == "server")
    assert server["requires"] == ["core"]
