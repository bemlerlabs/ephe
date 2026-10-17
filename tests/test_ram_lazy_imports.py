"""RAM guards: the idle path must not load heavy libs.

Root cause from the audit (Aug 2026): server.routes.audio loaded edge_tts at
module import (it pulls aiohttp), chat.py built a fresh vector-store client per
turn. Both paths are lazy now — this test keeps them sealed.
"""
from __future__ import annotations

import subprocess
import sys


def _loaded_modules(bootstrap_code: str) -> set[str]:
    """Import bootstrap_code in a clean interpreter and return
    the loaded top-level module names."""
    probe = (
        bootstrap_code
        + ";import sys;"
        + "print(chr(10).join(sorted({m.split('.')[0] for m in sys.modules})))"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True, text=True, timeout=120,
    )
    assert out.returncode == 0, out.stderr[-2000:]
    return {line for line in out.stdout.splitlines() if line.strip()}


def test_audio_route_import_does_not_load_edge_tts():
    mods = _loaded_modules("import server.routes.audio")
    assert "edge_tts" not in mods
    assert "aiohttp" not in mods


def test_the_removed_package_is_loaded_by_no_import_of_the_memory_stack():
    # The package left the product, so the promise is no longer "loaded late" but
    # "never loaded": importing the chat prompt, the facade, the provider and the
    # vision store must each leave it out of sys.modules.
    for statement in ("import core.chat", "import core.memory",
                      "import core.memory_provider", "import core.vision_memory"):
        mods = _loaded_modules(statement)
        assert "chromadb" not in mods, f"{statement} loaded the package the product removed"


def test_memory_singleton_reuses_instance(tmp_path, monkeypatch):
    import core.memory as m
    monkeypatch.setattr(m, "DEFAULT_MEMORY_DIR", tmp_path / "mem")
    m.Memory._INSTANCE = None
    a = m.Memory()
    assert a is m.Memory()
    assert m.Memory(persist_dir=str(tmp_path / "other")) is not a
    m.Memory._INSTANCE = None


def test_has_persisted_memory_false_for_missing_dir(monkeypatch):
    from pathlib import Path
    from core.memory import Memory
    import core.memory as m
    monkeypatch.setattr(m, "DEFAULT_MEMORY_DIR", Path("/definitely/not/here"))
    assert Memory.has_persisted_memory() is False
