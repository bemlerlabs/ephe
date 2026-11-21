"""One error taxonomy the serve, chat and CLI surfaces import.

The repair classes a malformed tool call is refused under used to live in the
tool registry alone. They sit in ``core/provider_errors.py`` now — the module the
three surfaces already import — and the registry reads them from there, so the
class set and the token a refusal carries are one table rather than two.

Runs offline: no engine, no network. The provider is never called.
"""
from __future__ import annotations

import argparse
import importlib
import json
import re

import pytest

from core import provider_errors
from core.observability import ErrorCode
from core.tools import registry

# Every hint placeholder the table uses, so a class renders without a KeyError.
HINT_FIELDS = {"names": "a, b", "key": "mode", "values": ["one", "two"]}


def test_the_registry_reads_the_one_taxonomy_not_a_copy():
    """The registry's names ARE the shared objects, not a second definition."""
    assert registry._REPAIR_TAXONOMY is provider_errors.REPAIR_TAXONOMY
    assert registry._REPAIR_CLASSES is provider_errors.REPAIR_CLASSES
    assert registry._REPAIR_CLASS_TOKEN is provider_errors.REPAIR_CLASS_TOKEN
    assert registry._RepairClass is provider_errors.RepairClass
    assert registry._refuse is provider_errors.refuse


def test_the_table_keys_are_the_class_names():
    """The dict and the tuple carry the same classes, entry for entry."""
    names = {rc.name for rc in provider_errors.REPAIR_CLASSES}
    assert names, "the repair taxonomy is empty"
    assert set(provider_errors.REPAIR_TAXONOMY) == names
    for rc in provider_errors.REPAIR_CLASSES:
        assert provider_errors.REPAIR_TAXONOMY[rc.name] is rc


def test_the_class_token_is_built_from_the_class_set():
    """The token matches exactly the announced classes — it cannot drift."""
    names = [rc.name for rc in provider_errors.REPAIR_CLASSES]
    rebuilt = re.compile(r"\[(" + "|".join(re.escape(n) for n in names) + r")\]")
    assert provider_errors.REPAIR_CLASS_TOKEN.pattern == rebuilt.pattern
    for name in names:
        assert provider_errors.REPAIR_CLASS_TOKEN.search(f"[{name}]")
    assert provider_errors.REPAIR_CLASS_TOKEN.search("[not-a-class]") is None


def test_a_rendered_refusal_classifies_back_to_its_class():
    """A refusal renders its class, and the registry reads the same class back."""
    for rc in provider_errors.REPAIR_CLASSES:
        text = provider_errors.refuse("some_tool", rc.name, "detail", **HINT_FIELDS)
        assert f"[{rc.name}]" in text
        assert provider_errors.repair_class_of(text) == rc.name
        assert registry._classify_tool_error(text) == rc.name


def test_an_unclassified_text_reads_no_class():
    """A refusal without a class token reads None from the shared reader."""
    assert provider_errors.repair_class_of("[TOOL-ERROR] x: some other error") is None


# The surfaces that import the taxonomy module at import time.
@pytest.mark.parametrize("module_name", ["server.openai", "core.chat_stream"])
def test_import_time_surfaces_bind_the_one_taxonomy(module_name):
    surface = importlib.import_module(module_name)
    assert surface.provider_errors is provider_errors
    assert surface.provider_errors.REPAIR_TAXONOMY is registry._REPAIR_TAXONOMY


def test_the_cli_surface_resolves_through_the_one_taxonomy(monkeypatch, capsys):
    """The CLI reads its code from the same module the taxonomy lives on."""
    from core._cli_common import _emit_error

    seen: list[object] = []

    def spy(error: object) -> ErrorCode:
        seen.append(error)
        return ErrorCode.UPSTREAM

    monkeypatch.setattr(provider_errors, "error_code_for", spy)
    _emit_error(
        argparse.Namespace(json=True), 1, "engine down", "Start the engine",
        error=RuntimeError("boom"),
    )
    assert seen, "the CLI did not read the one taxonomy module"
    payload = json.loads(capsys.readouterr().out)["error"]
    assert payload["code_id"] == ErrorCode.UPSTREAM.value
