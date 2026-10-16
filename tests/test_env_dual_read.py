"""R38: Env reads — the `EPHE_*` prefix is the only source of truth.

After the rebranding (`NOX_*` → `EPHE_*`) every env read path reads `EPHE_*` and
nothing else. This test pins the behaviour on the representative path
(`engine_config.config_root`) so the single-prefix integrity cannot drift.
"""
from __future__ import annotations

import importlib
from pathlib import Path


def _ec():
    return importlib.import_module("core.engine_config")


def test_ephe_prefix_is_authoritative(monkeypatch):
    """When `EPHE_CONFIG_DIR` is set, that value is the config root."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", "/tmp/ephe-new")
    assert str(_ec().config_root()) == "/tmp/ephe-new"


def test_default_when_absent(monkeypatch):
    """When `EPHE_CONFIG_DIR` is absent, the device default `~/.ephe` applies."""
    monkeypatch.delenv("EPHE_CONFIG_DIR", raising=False)
    assert str(_ec().config_root()) == str(Path.home() / ".ephe")
