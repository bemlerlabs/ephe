"""One authority for the workspace root: a neutral default the guard can reach (ticket #153).

The property this file buys: the folder ``get_workspace_dir()`` hands an unconfigured
install lies outside every ``path_guard.DENY_ROOTS`` root and is reachable through
``core.tools.base._is_path_allowed``. A configured workspace keeps winning, and a legacy
neutral folder under the config root is migrated rather than abandoned.

The decision is recorded in ``docs/decisions/workspace-authority.md``. Every test runs
with a fake ``HOME`` and a scratch ``EPHE_CONFIG_DIR``, so the neutral folder is created
inside ``tmp_path`` and never in the developer's home.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core import engine_config, path_guard, workspace_rules
from core.tools.base import _is_path_allowed

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def unconfigured_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """A machine nobody configured: no env choice, no engine.json, source checkout cwd."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    cfg = tmp_path / "config"
    cfg.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))
    monkeypatch.delenv("EPHE_WORKSPACE", raising=False)
    monkeypatch.setattr(engine_config, "default_config_path", lambda: cfg / "engine.json")
    monkeypatch.chdir(REPO_ROOT)
    return SimpleNamespace(home=home, cfg=cfg)


def _shipped_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run ``denied()`` as the product does, with the configured root protected.

    Pytest writes ``PYTEST_CURRENT_TEST`` before the call phase, after fixture setup, so
    the marker is dropped inside the test body: ``path_guard.denied`` then adds the
    configured ``EPHE_CONFIG_DIR`` to its roots and the scratch config root is refused
    exactly as a user's ``~/.ephe`` is.
    """
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)


def test_the_neutral_workspace_sits_outside_every_deny_root(
    unconfigured_install: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GIVEN no configured workspace and a cwd inside the checkout
    WHEN  get_workspace_dir() answers
    THEN  the answer is the neutral home folder, outside every refused root."""
    _shipped_guard(monkeypatch)
    handed_out = Path(engine_config.get_workspace_dir())
    assert handed_out == unconfigured_install.home / "Ephe"
    assert handed_out.is_dir()

    real = handed_out.resolve()
    for root in path_guard.DENY_ROOTS:
        assert not path_guard.within(real, Path(root).expanduser().resolve())
    assert path_guard.denied(handed_out) is False
    assert path_guard.denied(handed_out / "AGENTS.md") is False


def test_the_tool_gate_reaches_the_neutral_workspace(
    unconfigured_install: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GIVEN the folder the fallback hands out
    WHEN  the file-tool gate is asked about a file inside it
    THEN  the gate allows it and the dispatch refusal list stays empty."""
    _shipped_guard(monkeypatch)
    workspace = Path(engine_config.get_workspace_dir())
    target = workspace / "AGENTS.md"
    assert _is_path_allowed(target) is True
    assert path_guard.deny_paths({"path": str(target)}) == []


def test_a_configured_workspace_wins_over_the_neutral_default(
    unconfigured_install: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GIVEN EPHE_WORKSPACE names a project folder
    WHEN  get_workspace_dir() answers
    THEN  the configured folder is returned and the neutral one is never created."""
    chosen = tmp_path / "project"
    chosen.mkdir()
    monkeypatch.setenv("EPHE_WORKSPACE", str(chosen))

    assert Path(engine_config.get_workspace_dir()) == chosen.resolve()
    assert not (unconfigured_install.home / "Ephe").exists()


def test_a_configured_workspace_is_not_migrated(
    unconfigured_install: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GIVEN a legacy neutral folder and a configured workspace
    WHEN  the workspace is resolved
    THEN  the configured choice answers and the legacy files stay where they are."""
    legacy = unconfigured_install.cfg / "workspace"
    legacy.mkdir()
    (legacy / "notes.md").write_text("old\n", encoding="utf-8")
    chosen = tmp_path / "project"
    chosen.mkdir()
    monkeypatch.setattr(
        engine_config,
        "load_engine_config",
        lambda: engine_config.EngineChoice(
            provider="local_ollama", model="m", workspace_dir=str(chosen)
        ),
    )

    assert Path(engine_config.get_workspace_dir()) == chosen.resolve()
    assert (legacy / "notes.md").read_text(encoding="utf-8") == "old\n"
    assert not (unconfigured_install.home / "Ephe").exists()


def test_a_legacy_neutral_workspace_is_migrated_to_the_new_default(
    unconfigured_install: SimpleNamespace,
) -> None:
    """GIVEN an old install kept files in <config root>/workspace
    WHEN  the neutral workspace is resolved
    THEN  those files are reachable at the new default and are not deleted."""
    legacy = unconfigured_install.cfg / "workspace"
    legacy.mkdir()
    (legacy / "AGENTS.md").write_text("# project rules\n", encoding="utf-8")

    handed_out = Path(engine_config.get_workspace_dir())
    assert handed_out == unconfigured_install.home / "Ephe"
    migrated = handed_out / "AGENTS.md"
    assert migrated.read_text(encoding="utf-8") == "# project rules\n"
    assert _is_path_allowed(migrated) is True
    # The default was free, so the call renamed the folder instead of duplicating it.
    assert not legacy.exists()


def test_a_legacy_folder_does_not_overwrite_an_occupied_default(
    unconfigured_install: SimpleNamespace,
) -> None:
    """GIVEN the new default already holds a file the user edited
    WHEN  a legacy neutral folder with the same name is migrated
    THEN  the current file is kept and the legacy file is left in place."""
    legacy = unconfigured_install.cfg / "workspace"
    legacy.mkdir()
    (legacy / "AGENTS.md").write_text("legacy\n", encoding="utf-8")
    current = unconfigured_install.home / "Ephe"
    current.mkdir()
    (current / "AGENTS.md").write_text("current\n", encoding="utf-8")

    assert Path(engine_config.get_workspace_dir()) == current
    assert (current / "AGENTS.md").read_text(encoding="utf-8") == "current\n"
    assert (legacy / "AGENTS.md").read_text(encoding="utf-8") == "legacy\n"


def test_a_legacy_folder_is_not_migrated_into_the_running_checkout(
    unconfigured_install: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GIVEN the neutral folder is the source checkout the process runs from
    WHEN  a legacy neutral folder holds files
    THEN  nothing is written into the checkout and the old files stay where they are."""
    legacy = unconfigured_install.cfg / "workspace"
    legacy.mkdir()
    (legacy / "AGENTS.md").write_text("legacy\n", encoding="utf-8")
    checkout = unconfigured_install.home / "Ephe"
    checkout.mkdir()
    (checkout / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    monkeypatch.setattr(engine_config, "_source_checkout_root", lambda: checkout)
    monkeypatch.chdir(checkout)

    assert Path(engine_config.get_workspace_dir()) == checkout
    assert not (checkout / "AGENTS.md").exists()
    assert (legacy / "AGENTS.md").read_text(encoding="utf-8") == "legacy\n"


def test_the_prompt_resolver_delegates_to_the_one_authority(
    unconfigured_install: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GIVEN the workspace resolver the prompt layer reads
    WHEN  it answers beside get_workspace_dir()
    THEN  both name the same folder, including for an unusable EPHE_WORKSPACE value."""
    monkeypatch.setenv("EPHE_WORKSPACE", "/no/such/workspace")
    assert Path(workspace_rules.resolve_workspace_dir()) == Path(
        engine_config.get_workspace_dir()
    )


def test_the_neutral_folder_steps_aside_when_the_home_holds_the_checkout(monkeypatch, tmp_path):
    """A source checkout already sitting at the neutral default's own name is not handed out.

    On a case-insensitive volume `~/Ephe` and a checkout named `~/ephe` are one folder; on
    Linux and on a case-sensitive volume they are two. The property is the same on both: when
    the candidate `~/Ephe` *is* the checkout, the default moves to a sibling and no file write
    can reach the source tree. The fixture builds the checkout at that candidate, so the test
    asserts the property instead of relying on the filesystem's case rules.
    """
    from core import engine_config as cfg

    home = tmp_path / "home"
    checkout = home / "Ephe"
    (checkout / "core").mkdir(parents=True)
    (checkout / "pyproject.toml").write_text(
        '[project]\nname = "ephe"\nversion = "0.0.0"\n', encoding="utf-8"
    )
    (checkout / ".git").mkdir()
    monkeypatch.setattr(cfg.Path, "home", classmethod(lambda cls: home))

    resolved = cfg.neutral_workspace_dir()

    assert resolved != checkout, resolved
    assert resolved.parent == home, resolved
    assert resolved.name.lower().startswith("ephe"), resolved
