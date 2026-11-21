"""Sprint2-F1: bundle audit tooling (app/scripts/bundle_audit.py) — semantics tests.

SPECK (CTO-pinned): DoD (1) initial-bundle gzip < 500 KB, measurable from the build
output. This test locks down the measurement semantics: dynamic `import()` references
(React.lazy route-split) do NOT belong to the initial bundle, static import closures and
modulepreload references do. A mistake in the initial/lazy classification would be a
silent DoD mis-measurement (over- or under-estimation), so it is pinned here against a
synthetic dist fixture.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "app" / "scripts" / "bundle_audit.py"


def _write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def _make_dist(dist: Path) -> None:
    """Synthetic dist: index.html → entry.js (static closure: shared.js + css),
    entry.js loads route.js via import() (lazy), route.js → heavy.js (lazy closure).
    Enlarging the lazy parts must NOT move the initial measurement."""
    _write(
        dist / "index.html",
        '<script type="module" src="/assets/entry.js"></script>\n'
        '<link rel="stylesheet" href="/assets/style.css">\n',
    )
    _write(dist / "assets" / "style.css", "body{color:red}")
    _write(
        dist / "assets" / "entry.js",
        'import { x } from "./shared.js";'
        'const route = () => import("./route.js");'
        "export { x };\n",
    )
    _write(dist / "assets" / "shared.js", "export const x = 1;\n")
    _write(
        dist / "assets" / "route.js",
        'import { h } from "./heavy.js";export const r = h;\n',
    )
    # keep the lazy closure deliberately large: it must not move the initial size
    _write(dist / "assets" / "heavy.js", "export const h = '" + "z" * 20000 + "';\n")


def _run_audit(dist: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(AUDIT), str(dist)],
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout


def test_given_synthetic_dist_when_audit_then_lazy_chunks_excluded_from_initial(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _make_dist(dist)
    rc, out = _run_audit(dist)
    assert rc == 0, out
    # Initial closure: entry.js + shared.js + style.css (route.js/heavy.js NOT included)
    assert "entry.js" in out.split("INITIAL TOTAL")[0]
    assert "shared.js" in out.split("INITIAL TOTAL")[0]
    assert "style.css" in out.split("INITIAL TOTAL")[0]
    # Lazy chunks (route-split) are counted separately
    lazy_section = out.split("LAZY chunks")[1]
    assert "route.js" in lazy_section
    assert "heavy.js" in lazy_section
    assert "entry.js" not in lazy_section


def test_given_large_lazy_chunk_when_audit_then_initial_budget_untouched(tmp_path: Path) -> None:
    """Regression guard: the 20KB heavy chunk sits ONLY in the lazy closure → PASS.
    Were the classification to count it as initial, the initial line would have to come
    out correspondingly fatter. Checks the budget decision explicitly."""
    dist = tmp_path / "dist"
    _make_dist(dist)
    rc, out = _run_audit(dist)
    assert rc == 0, out
    assert "PASS" in out
    initial_block = out.split("INITIAL TOTAL")[0]
    assert "heavy.js" not in initial_block
