"""WE-35: per-chunk bundle budget gate (app/scripts/bundle_budget.py).

bundle_audit.py gates the aggregate initial gzip total; this gate pins a number
to every chunk that matters — the chunks index.html loads on first paint plus any
chunk over the size floor — so a single chunk ballooning past its budget fails
even when the aggregate stays under. Semantics pinned here against synthetic dist
fixtures plus the real build when present.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / "app" / "scripts" / "bundle_budget.py"
DIST = REPO / "app" / "dist"


def _write(p: Path, data: bytes | str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data if isinstance(data, bytes) else data.encode())


def _main_dist(dist: Path, index_js: bytes | str = "export const a=1;\n") -> None:
    """A dist whose index.html loads the five budgeted main chunks."""
    refs = "\n".join(
        f'<script type="module" src="/assets/{n}"></script>'
        for n in (
            "index-BBvxx5rb.js",
            "ui-vendor-BMdbY3LA.js",
            "motion-CQFg8Nau.js",
            "app-vendor-BMTtgqs3.js",
        )
    )
    _write(dist / "index.html", f'{refs}\n<link rel="stylesheet" href="/assets/index-Clcm4dX3.css">')
    _write(dist / "assets" / "index-BBvxx5rb.js", index_js)
    for n in ("ui-vendor-BMdbY3LA.js", "motion-CQFg8Nau.js", "app-vendor-BMTtgqs3.js"):
        _write(dist / "assets" / n, "export const v=1;\n")
    _write(dist / "assets" / "index-Clcm4dX3.css", "body{color:red}")


def _run(dist: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(GATE), str(dist)],
        capture_output=True, text=True, timeout=120,
    )
    return proc.returncode, proc.stdout


def test_budgets_are_declared_and_within_the_aggregate_budget() -> None:
    """GIVEN the gate WHEN reading its budgets THEN each main chunk has a number
    and no single chunk budget exceeds the 500 KB aggregate."""
    src = GATE.read_text(encoding="utf-8")
    entries = re.findall(r'"([\w.\-]+\.(?:js|css))":\s*([0-9.]+)', src)
    budgets = {k: float(v) for k, v in entries}
    for key in ("index.js", "ChatPage.js", "markdown.js", "ui-vendor.js", "motion.js", "index.css", "app-vendor.js"):
        assert key in budgets, f"missing budget for chunk {key}"
    assert budgets["index.js"] <= 300.0, "entry-chunk budget raised without measurement"
    assert all(b <= 500.0 for b in budgets.values())


def test_given_small_chunks_when_gate_then_pass(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _main_dist(dist)
    rc, out = _run(dist)
    assert rc == 0, out
    assert "All gated chunks within budget" in out


def test_given_oversized_main_chunk_when_gate_then_fail(tmp_path: Path) -> None:
    """A single main chunk (index.js) over its number fails even though the total
    payload would still sit under the aggregate budget."""
    dist = tmp_path / "dist"
    _main_dist(dist, index_js=os.urandom(400 * 1024))  # incompressible -> gzip ~400 KB
    rc, out = _run(dist)
    assert rc == 1, out
    assert "index.js over budget" in out


def test_given_oversized_lazy_route_chunk_when_gate_then_fail(tmp_path: Path) -> None:
    """A lazy route chunk over its budget fails too: nothing large ships unwatched."""
    dist = tmp_path / "dist"
    _main_dist(dist)
    _write(dist / "assets" / "markdown-V4M29lm3.js", os.urandom(200 * 1024))
    rc, out = _run(dist)
    assert rc == 1, out
    assert "markdown.js over budget" in out


def test_given_unbudgeted_main_chunk_when_gate_then_fail_closed(tmp_path: Path) -> None:
    """A new statically loaded chunk with no number is refused, so a regression
    cannot dodge the gate by adding a chunk."""
    dist = tmp_path / "dist"
    _main_dist(dist)
    html = (dist / "index.html").read_text()
    _write(dist / "index.html", html + '\n<script src="/assets/newvendor-ABCDEFGH.js"></script>')
    _write(dist / "assets" / "newvendor-ABCDEFGH.js", "export const n=1;\n")
    rc, out = _run(dist)
    assert rc == 1, out
    assert "unbudgeted main chunk" in out


def test_given_new_large_lazy_chunk_when_gate_then_fail_closed(tmp_path: Path) -> None:
    """A large lazy chunk with no number is refused as well (floor fail-closed)."""
    dist = tmp_path / "dist"
    _main_dist(dist)
    _write(dist / "assets" / "BigRoute-ABCDEFGH.js", os.urandom(200 * 1024))
    rc, out = _run(dist)
    assert rc == 1, out
    assert "unbudgeted large chunk" in out


def test_given_large_compressible_chunk_when_gate_then_gzip_not_raw(tmp_path: Path) -> None:
    """The gate measures gzip, not raw: 1 MB of 'z' compresses far under 300 KB."""
    dist = tmp_path / "dist"
    _main_dist(dist, index_js="z" * (1024 * 1024))
    rc, out = _run(dist)
    assert rc == 0, out


def test_every_chunk_is_gated_not_only_main(tmp_path: Path) -> None:
    """A small lazy chunk with no row of its own is measured and reported (it
    used to be skipped below the floor): every chunk is gated."""
    dist = tmp_path / "dist"
    _main_dist(dist)
    _write(dist / "assets" / "useMemoryFacts-AAAABBBB.js", os.urandom(5 * 1024))
    rc, out = _run(dist)
    assert rc == 0, out
    assert "small useMemoryFacts-AAAABBBB.js" in out


def test_lazy_chunk_over_the_small_ceiling_when_gate_then_fail(tmp_path: Path) -> None:
    """A lazy chunk that outgrows the small ceiling and has no row fails, so a
    medium chunk cannot settle under the ceiling without earning a number."""
    dist = tmp_path / "dist"
    _main_dist(dist)
    _write(dist / "assets" / "MediumRoute-AAAABBBB.js", os.urandom(15 * 1024))
    rc, out = _run(dist)
    assert rc == 1, out
    assert "unbudgeted large chunk" in out


def test_chunk_sharing_a_main_name_is_gated_small(tmp_path: Path) -> None:
    """Vite emits several index-*.js barrels. A non-main chunk that shares the
    entry's name is held to the small ceiling instead of its 300 kB row."""
    dist = tmp_path / "dist"
    _main_dist(dist)
    _write(dist / "assets" / "index-ZZZZZZZZ.js", os.urandom(30 * 1024))
    rc, out = _run(dist)
    assert rc == 1, out
    assert "shares the" in out


@pytest.mark.skipif(not DIST.is_dir(), reason="no frontend build present (run `cd app && npm run build`)")
def test_shipped_build_respects_every_chunk_budget() -> None:
    """GIVEN the built app/dist WHEN running the gate THEN every gated chunk is within budget."""
    rc, out = _run(DIST)
    assert rc == 0, f"chunk budget breached:\n{out}"
