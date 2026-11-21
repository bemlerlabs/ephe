"""
Ephe — R33: bundle budget as a test (DoD: "messbare Performance-Tests,  # language-gate: ignore (quoted German R33 DoD requirement — opening line of the quote, kept verbatim)
Budgets als Tests wie test_r25_latency_budgets.py").  # language-gate: ignore (quoted German R33 DoD requirement — continuation line of the same quote)

scripts/bundle_audit.py encodes the product budget: the INITIAL payload the
browser fetches on first paint (entry chunks + static graph + HTML-linked CSS,
gzip) must stay under 500 KB. Lazy route chunks are excluded by design —
React.lazy keeps them out of the initial load (App.tsx). This wrapper turns
that audit into a pytest assertion whenever a build exists (CI builds dist in
the Frontend workflow and runs the same gate as an explicit step).

Given / When / Then — strictly.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
AUDIT = REPO / "app" / "scripts" / "bundle_audit.py"
DIST = REPO / "app" / "dist"


def test_audit_script_exists_and_declares_the_budget():
    """GIVEN the audit harness WHEN reading its source THEN the committed budget is <= 500 KB."""
    src = AUDIT.read_text(encoding="utf-8")
    match = re.search(r"BUDGET_KB\s*=\s*([0-9.]+)", src)
    assert match, "budget constant missing in bundle_audit.py"
    assert float(match.group(1)) <= 500.0


def test_app_routes_are_lazy_loaded():
    """GIVEN App.tsx WHEN inspecting THEN every page route goes through lazy()."""
    src = (REPO / "app" / "src" / "App.tsx").read_text(encoding="utf-8")
    pages = re.findall(r"const (\w+Page)\s*=\s*lazy\(\s*\(\)\s*=>\s*import\(", src)
    assert len(pages) >= 3, f"expected lazy route-split pages, found {pages}"


@pytest.mark.skipif(not DIST.is_dir(), reason="no frontend build present (run `cd app && npm run build`)")
def test_initial_bundle_respects_the_gzip_budget():
    """GIVEN a fresh dist build WHEN running the bundle audit THEN exit code is 0 (budget kept)."""
    proc = subprocess.run(
        [sys.executable, str(AUDIT), str(DIST)],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, f"bundle budget exceeded:\n{proc.stdout}\n{proc.stderr}"
