"""HOOK-P1 — the turn hook a manifest may declare (`components.hooks`).

The seam this file pins: a version 2 manifest names one hook for the end of a turn, with
one entry inside the bundle directory and one bound in seconds; the manifest scan registers
it, and the dispatcher is the only reader. The kernel fixes the event vocabulary, the
payload, the confinement and the timeout's window, so the manifest cannot ask for the
answer, a second event or a longer run.

What the kernel keeps, and this file therefore checks under a declared hook too: the entry
rule is a contributed tool's (`_entry_field_error`), the version rule is the capability
sections' (version 2 only), and the rail reports the bundle as code it carries. The
dispatcher's behavioural half is `tests/test_plugin_turn_hooks.py`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.plugin_hooks_contract import (
    HOOK_EVENTS,
    MAX_HOOK_TIMEOUT_SECONDS,
    MIN_HOOK_TIMEOUT_SECONDS,
    TurnHook,
    hook_claims,
    hook_facts,
    scan_turn_hooks,
    validate_hooks,
)


def _hook(**overrides: object) -> dict:
    """One valid hook body; `overrides` replaces a field, and None drops it."""
    body: dict = {"entry": "hooks/turn_end.py:main", "timeout_seconds": 2}
    body.update(overrides)
    return {key: value for key, value in body.items() if value is not None}


def _manifest(hooks: object = None, **overrides: object) -> dict:
    """A version 2 manifest declaring one hook; `hooks` replaces the section."""
    manifest: dict = {
        "manifest_version": 2,
        "name": "acme-hook",
        "version": "1.0.0",
        "description": "Runs one hook when a turn ends.",
        "publisher": {"name": "Acme"},
        "license": "MIT",
        "engines": {"ephe": ">=0.6.0"},
        "permissions": {"tool_families": [], "data_roots": []},
        "components": {"hooks": {"turn_end": _hook()} if hooks is None else hooks},
    }
    manifest.update(overrides)
    return manifest


def _write(root: Path, manifest: dict) -> Path:
    directory = root / str(manifest["name"])
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ephe-plugin.json").write_text(
        json.dumps({**manifest, "name": directory.name}), encoding="utf-8"
    )
    return directory


def _error(root: Path, manifest: dict) -> str | None:
    from core.plugin_manifest import load_manifest

    return load_manifest(_write(root, manifest))[1]


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    directory = tmp_path / "contract"
    directory.mkdir()
    return directory


class TestContract:
    def test_a_version_two_bundle_may_name_one_turn_end_hook(self, root: Path) -> None:
        from core.plugin_manifest import load_manifest

        manifest, error = load_manifest(_write(root, _manifest()))
        assert error is None
        claims = hook_claims(manifest)
        assert claims == (
            TurnHook(
                plugin_id="acme-hook",
                event="turn_end",
                entry="hooks/turn_end.py:main",
                timeout_seconds=2,
            ),
        )
        assert hook_facts(manifest) == [{"event": "turn_end", "timeout_seconds": 2}]

    def test_an_empty_hooks_object_declares_nothing(self, root: Path) -> None:
        from core.plugin_manifest import load_manifest

        manifest, error = load_manifest(_write(root, _manifest(hooks={})))
        assert error is None
        assert hook_claims(manifest) == ()

    def test_a_version_one_manifest_cannot_declare_a_live_hook(self, root: Path) -> None:
        """The section in a version 1 bundle is refused even when it holds nothing."""
        for hooks in ({"turn_end": _hook()}, {}):
            error = _error(
                root, _manifest(hooks=hooks, manifest_version=1)
            )
            assert error is not None and "manifest_version 2 required" in error

    def test_a_hook_is_one_event_in_this_cut(self, root: Path) -> None:
        assert HOOK_EVENTS == ("turn_end",)
        error = _error(
            root,
            _manifest(hooks={"turn_end": _hook(), "turn_start": _hook()}),
        )
        assert error is not None and "turn_start" in error

    def test_hooks_has_to_be_an_object(self, root: Path) -> None:
        error = _error(root, _manifest(hooks=[_hook()]))
        assert error is not None and "object expected" in error

    def test_the_event_body_has_to_be_an_object(self, root: Path) -> None:
        error = _error(root, _manifest(hooks={"turn_end": ["hooks/turn_end.py:main"]}))
        assert error is not None and "components.hooks.turn_end" in error

    @pytest.mark.parametrize(
        "field",
        ["payload", "answer", "history", "context", "event"],
    )
    def test_a_field_outside_the_body_is_refused_by_name(
        self, root: Path, field: str
    ) -> None:
        error = _error(
            root, _manifest(hooks={"turn_end": _hook(**{field: "the answer"})})
        )
        assert error is not None and field in error
        assert "cannot declare another field" in error

    @pytest.mark.parametrize(
        "entry",
        [
            "/etc/passwd.py:main",
            "../escape.py:main",
            "hooks/turn_end.py",
            "hooks/turn_end.txt:main",
            "hooks/turn_end.py:not-a-name",
            "hooks/turn_end.py:main:extra",
            "hooks/../turn_end.py:main",
        ],
    )
    def test_the_entry_obeys_the_contributed_tool_rule(
        self, root: Path, entry: str
    ) -> None:
        error = _error(root, _manifest(hooks={"turn_end": _hook(entry=entry)}))
        assert error is not None and "entry" in error

    def test_the_entry_is_required(self, root: Path) -> None:
        error = _error(root, _manifest(hooks={"turn_end": _hook(entry=None)}))
        assert error is not None and "path.py:callable" in error

    @pytest.mark.parametrize(
        "timeout", [None, True, False, 0, 4, -1, 2.5, "2"]
    )
    def test_the_bound_is_a_whole_number_in_the_kernel_window(
        self, root: Path, timeout: object
    ) -> None:
        error = _error(
            root, _manifest(hooks={"turn_end": _hook(timeout_seconds=timeout)})
        )
        assert error is not None and "timeout_seconds" in error

    @pytest.mark.parametrize("timeout", [MIN_HOOK_TIMEOUT_SECONDS, MAX_HOOK_TIMEOUT_SECONDS])
    def test_both_edges_of_the_window_are_accepted(
        self, root: Path, timeout: int
    ) -> None:
        from core.plugin_manifest import load_manifest

        manifest, error = load_manifest(
            _write(root, _manifest(hooks={"turn_end": _hook(timeout_seconds=timeout)}))
        )
        assert error is None
        assert hook_claims(manifest)[0].timeout_seconds == timeout

    def test_validation_refuses_a_manifest_that_is_not_an_object(self, root: Path) -> None:
        assert validate_hooks(None, root) is None
        assert validate_hooks([], root) is None

    def test_a_version_one_manifest_yields_no_claim(self) -> None:
        assert hook_claims(_manifest(manifest_version=1)) == ()
        assert hook_claims(None) == ()
        assert hook_claims({}) == ()

    def test_a_malformed_body_yields_no_claim_rather_than_a_wrong_one(self) -> None:
        assert hook_claims(_manifest(hooks={"turn_end": _hook(entry=None)})) == ()
        assert hook_claims(_manifest(hooks={"turn_end": _hook(timeout_seconds=9)})) == ()
        assert hook_claims(_manifest(hooks={"turn_end": "not an object"})) == ()


class TestRegistration:
    def _entry(self, directory: Path, manifest: dict | None, error: str = "") -> dict:
        return {"dir": str(directory), "manifest": manifest, "error": error}

    def test_the_scan_orders_the_hooks_by_plugin_id(self, tmp_path: Path) -> None:
        first = tmp_path / "zulu"
        second = tmp_path / "alpha"
        hooks = scan_turn_hooks(
            [
                self._entry(first, _manifest(name="zulu")),
                self._entry(second, _manifest(name="alpha")),
            ]
        )
        assert [hook.plugin_id for hook in hooks] == ["alpha", "zulu"]
        assert hooks[0].plugin_dir == str(second)

    def test_an_unreadable_entry_contributes_no_hook(self, tmp_path: Path) -> None:
        hooks = scan_turn_hooks(
            [
                self._entry(tmp_path / "broken", _manifest(), error="bad manifest"),
                self._entry(tmp_path / "naked", None),
                self._entry(tmp_path / "quiet", _manifest(hooks={})),
            ]
        )
        assert hooks == ()

    def test_a_hook_counts_as_code_the_bundle_carries(self) -> None:
        from core.plugin_rail import RAIL_WORKER, rail_fact

        fact = rail_fact(_manifest())
        assert fact == {"rail": RAIL_WORKER, "contributed": 1, "activated": 0}

    def test_a_bundle_with_a_tool_and_a_hook_counts_both(self) -> None:
        from core.plugin_rail import rail_fact

        manifest = _manifest()
        manifest["components"]["tools"] = [
            {
                "name": "tick",
                "entry": "tools/tick.py:run",
                "family": "read",
                "description": "Counts.",
            }
        ]
        assert rail_fact(manifest)["contributed"] == 2
