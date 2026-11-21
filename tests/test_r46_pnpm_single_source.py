"""
◑ Ephe – Wave 1 (2026-09-24): pnpm as the only package-manager source.
tests/test_r46_pnpm_single_source.py

RULE: tests written BEFORE the implementation.

Pins:
1. app/package.json carries `packageManager` (Corepack pins the pnpm version).
2. Exactly ONE lockfile: app/pnpm-lock.yaml exists, app/package-lock.json does not.
3. .github/workflows/frontend-build.yml runs through pnpm (no `npm ci` left).
4. install.sh uses the pnpm path in build_pwa().
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"


def test_package_json_declares_package_manager():
    """GIVEN app/package.json
    THEN `packageManager` is set (the Corepack pin to pnpm)."""
    data = json.loads((APP / "package.json").read_text(encoding="utf-8"))
    assert "packageManager" in data
    assert data["packageManager"].startswith("pnpm@")


def test_single_lockfile_pnpm_only():
    """GIVEN app/
    THEN pnpm-lock.yaml exists as the only lockfile; package-lock.json is
    deleted (no dual source of truth any more)."""
    assert (APP / "pnpm-lock.yaml").is_file()
    assert not (APP / "package-lock.json").exists()


def test_frontend_workflow_uses_pnpm():
    """GIVEN .github/workflows/frontend-build.yml
    THEN the install runs through pnpm (no `npm ci` left in the workflow)."""
    text = (ROOT / ".github" / "workflows" / "frontend-build.yml").read_text(
        encoding="utf-8"
    )
    assert "pnpm" in text
    assert "npm ci" not in text


def test_installer_uses_pnpm():
    """GIVEN install.sh
    THEN build_pwa() uses the pnpm path."""
    text = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert "pnpm" in text
