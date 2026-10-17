"""The tool surface has to import from a process whose working directory is gone.

A running process can sit in a directory that no longer exists: a cleanup removed
the tree, a mount went away, a temp root was deleted under a live turn. ``Path.cwd()``
raises FileNotFoundError in exactly that state, and ``core/tools/base.py`` read it
while building ``ALLOWED_ROOTS`` at module level, so ``import core.tools.base`` failed
-- and every tool of every surface went with it -- for a condition no caller was ever
told about. The bar held here: importing the tool surface, or reading its roots, either
works or names what is wrong. A bare FileNotFoundError raised from a module's top level
is neither, and a vanished directory is not a reason for the tool layer to be absent.

Each case runs in a child process, because the condition under test is the process's own
working directory and the suite sits in the repository.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: Modes: `live` reads with a working directory, `gone` imports after the directory
#: was removed, `gone-after-import` removes it after the import, `moved` imports in one
#: directory and reads in a second one.
CHILD = r'''
import json, os, shutil, sys, tempfile
from pathlib import Path

mode, repo = sys.argv[1], sys.argv[2]
sys.path.insert(0, repo)


def cwd_gone() -> bool:
    try:
        Path.cwd()
    except FileNotFoundError:
        return True
    return False


first = Path(tempfile.mkdtemp(prefix="ephe-cwd-"))
os.chdir(first)
here = str(Path.cwd())

if mode == "gone":
    shutil.rmtree(first)
    gone = cwd_gone()
    import core.tools.base as base
    later = None
elif mode == "gone-after-import":
    import core.tools.base as base
    shutil.rmtree(first)
    gone = cwd_gone()
    later = None
elif mode == "moved":
    import core.tools.base as base
    second = Path(tempfile.mkdtemp(prefix="ephe-cwd-"))
    os.chdir(second)
    gone = False
    later = str(Path.cwd())
else:
    import core.tools.base as base
    gone = False
    later = None

roots = [str(p) for p in base.ALLOWED_ROOTS]
print(json.dumps({
    "cwd_gone": gone,
    "here": here,
    "later": later,
    "roots": roots,
    "has_here": here in roots,
    "has_later": later in roots if later else None,
}))
'''


def _run(mode: str) -> dict:
    proc = subprocess.run(
        [sys.executable, "-c", CHILD, mode, str(REPO_ROOT)],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=180,
        check=False,
    )
    detail = f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    assert proc.returncode == 0, f"child in mode {mode!r} failed:\n{detail}"
    assert "Traceback" not in proc.stderr, f"child in mode {mode!r} raised:\n{detail}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


#: The four roots that do not depend on the working directory.
STATIC = ("Documents", "Desktop", "Downloads", ".ephe")


def test_the_import_survives_a_working_directory_that_was_removed():
    out = _run("gone")
    assert out["cwd_gone"] is True, "the child did not reach the condition under test"
    assert out["roots"], "the roots came back empty"


def test_the_static_roots_are_still_there_after_the_directory_vanished():
    out = _run("gone")
    for name in STATIC:
        assert any(root.endswith(f"/{name}") for root in out["roots"]), f"{name} missing"
    assert out["has_here"] is False, "a working directory that is gone cannot be a root"


def test_a_read_after_the_directory_vanished_does_not_raise():
    out = _run("gone-after-import")
    assert out["cwd_gone"] is True
    assert out["has_here"] is False, "the dead directory is still listed as a root"
    for name in STATIC:
        assert any(root.endswith(f"/{name}") for root in out["roots"])


def test_the_roots_are_read_where_they_are_used_not_where_the_module_is_imported():
    out = _run("moved")
    assert out["has_later"] is True, "the second directory is not a root"
    assert out["has_here"] is False, "the reading is pinned to the import-time directory"


def test_a_live_working_directory_is_a_root_and_keeps_its_place():
    out = _run("live")
    assert out["cwd_gone"] is False
    assert out["has_here"] is True, "the working directory is not among the roots"
    assert out["roots"][-1] == out["here"], "the working directory is no longer the last root"
