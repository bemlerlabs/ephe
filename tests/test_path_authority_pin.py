"""Pin: where an unconfigured install puts the workspace (ticket #153).

The property settled by ``docs/decisions/workspace-authority.md``: the folder
``get_workspace_dir`` hands an unconfigured install lies outside every
``path_guard.DENY_ROOTS`` root and the file-tool gate reaches it. The pin asks the real
functions on the path the fallback returns, so a future default cannot land in a refused
root without failing here.

The contradiction this file was written against, kept as the reason it exists: the
fallback answered ``config_root()/workspace`` while ``DENY_ROOTS`` refuses ``~/.ephe``.
``denied()`` was ``True``, ``_is_path_allowed()`` was ``False``, and
``core/tools/registry.py`` refused ``read_file`` before a human could approve it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core import engine_config, path_guard
from core.tools.base import _is_path_allowed

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_an_unconfigured_workspace_is_reachable_outside_the_refused_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pin of the settled state: the guard allows the folder the fallback hands out.

    The suite pins ``EPHE_CONFIG_DIR`` to a scratch folder, and the guard adds a
    configured root to the deny list only outside pytest. Drop the marker inside the test
    body, after fixture setup, so the shipped rule runs while the writes stay in
    ``tmp_path``; the scratch config root then stands in for the user's ``~/.ephe``.
    """
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    cfg = tmp_path / "cfg"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.delenv("EPHE_WORKSPACE", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))
    monkeypatch.setattr(engine_config, "default_config_path", lambda: cfg / "engine.json")
    monkeypatch.chdir(REPO_ROOT)

    # The real fallback, asked the way the tool gate asks it.
    handed_out = Path(engine_config.get_workspace_dir())
    assert handed_out == home / "Ephe"

    # The guard answers for the folder itself and for a file a tool would be pointed at.
    assert path_guard.denied(handed_out) is False
    assert path_guard.denied(handed_out / "AGENTS.md") is False
    assert _is_path_allowed(handed_out / "AGENTS.md") is True
    assert path_guard.deny_paths({"path": str(handed_out / "AGENTS.md")}) == []

    # No loophole was carved: the config root stays refused, its old workspace included.
    assert path_guard.denied(cfg / "workspace") is True
    assert "~/.ephe" in path_guard.DENY_ROOTS
