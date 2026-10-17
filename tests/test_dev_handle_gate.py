"""The dev store handle must not ship — pin of app/scripts/dev_handle_check.py.

`src/store/chatStore.ts` assigns `window.__epheStore` under `import.meta.env.DEV`
so the fifteen Playwright specs that seed state through it can run (register #68).
The gate reads the build artefact and fails when the assignment is in a served
file. This pins the gate's verdict on synthetic dist fixtures, so the gate cannot
become the next thing that quietly stops looking: pass on a clean dist, fail on a
dist that carries the assignment, and refuse to answer when it cannot tell (no
dist, no store in the scanned set). The real app/dist is checked when one is
present.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GATE = REPO / "app" / "scripts" / "dev_handle_check.py"
STORE_SRC = REPO / "app" / "src" / "store" / "chatStore.ts"
DIST = REPO / "app" / "dist"

# The store's compiled shape: a ChatState key (the gate's own vacuity control,
# `STORE_MARK`) plus the assignment the gate hunts for.
ENTRY_CLEAN = 'const s=[];activeSessionId;typeof window<"u"&&(window.__ephe=1);'
ENTRY_SHIPPED = 'const s=[];activeSessionId;typeof window<"u"&&(window.__epheStore=ka);'


def _write(p: Path, data: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(data, encoding="utf-8")


def _dist(tmp_path: Path, entry_js: str = ENTRY_CLEAN) -> Path:
    """A dist with one served entry chunk, as index.html loads it."""
    dist = tmp_path / "dist"
    _write(dist / "index.html", '<script type="module" src="/assets/index-AAAA1111.js"></script>')
    _write(dist / "assets" / "index-AAAA1111.js", entry_js)
    return dist


def _run(dist: Path) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(GATE), str(dist)],
        capture_output=True, text=True, timeout=120,
    )
    return proc.returncode, proc.stdout


def test_given_clean_dist_when_gate_then_pass(tmp_path: Path) -> None:
    rc, out = _run(_dist(tmp_path))
    assert rc == 0, out
    assert "PASS" in out


def test_given_assignment_in_a_served_chunk_when_gate_then_fail(tmp_path: Path) -> None:
    """The minified shape a production build emits when the DEV guard is gone."""
    rc, out = _run(_dist(tmp_path, ENTRY_SHIPPED))
    assert rc == 1, out
    assert "index-AAAA1111.js" in out


def test_given_computed_assignment_when_gate_then_fail(tmp_path: Path) -> None:
    """A bracket write is the same capability under another spelling."""
    rc, out = _run(_dist(tmp_path, 'activeSessionId;window["__epheStore"]=ka;'))
    assert rc == 1, out


def test_given_dist_without_the_store_when_gate_then_refuses(tmp_path: Path) -> None:
    """No chunk carries a ChatState key, so the scan proves nothing about the app."""
    rc, out = _run(_dist(tmp_path, "const a=1;"))
    assert rc == 2, out
    assert "not in the scanned set" in out


def test_given_no_dist_when_gate_then_refuses(tmp_path: Path) -> None:
    rc, out = _run(tmp_path / "dist")
    assert rc == 2, out
    assert "run `npm run build` first" in out


def test_given_name_in_a_map_and_its_sibling_when_gate_then_fail(tmp_path: Path) -> None:
    """A map names the chunk the store compiled into; that chunk is served, so the
    name in the served sibling is a failure even without the assignment."""
    dist = _dist(tmp_path, 'activeSessionId;const n="__epheStore";')
    _write(dist / "assets" / "index-AAAA1111.js.map", '{"sourcesContent":["window.__epheStore = s"]}')
    rc, out = _run(dist)
    assert rc == 1, out
    assert "served sibling" in out


def test_given_name_only_in_a_map_when_gate_then_pass(tmp_path: Path) -> None:
    """The shipped world: the map carries the source text, the served script does not."""
    dist = _dist(tmp_path)
    _write(dist / "assets" / "index-AAAA1111.js.map", '{"sourcesContent":["window.__epheStore = s"]}')
    rc, out = _run(dist)
    assert rc == 0, out
    assert "those scripts carry the name: none" in out


def test_gate_pattern_matches_the_shipped_source_once() -> None:
    """The gate's instrument, read from its own file and pointed at chatStore.ts:
    one assignment site, so the pattern cannot pass by looking for nothing."""
    pattern = re.search(r'ASSIGN = re\.compile\(r"""(.+?)"""\)', GATE.read_text(encoding="utf-8"))
    assert pattern, "the gate no longer declares its ASSIGN pattern where this test reads it"
    sites = re.findall(pattern.group(1), STORE_SRC.read_text(encoding="utf-8"))
    assert len(sites) == 1, f"chatStore.ts carries {len(sites)} assignment sites"


@pytest.mark.skipif(not DIST.is_dir(), reason="no frontend build present (run `cd app && npm run build`)")
def test_shipped_build_carries_no_dev_handle() -> None:
    """The built bundle answers the production half of the pin (register #68)."""
    rc, out = _run(DIST)
    assert rc == 0, f"a served file carries the dev handle:\n{out}"
