"""The doctor's Plugin lock row: the installed bundles against the record of them.

`core/plugin_lockfile.py` promised a start or a release would name the drifted bundle, and
`diff_lockfile` had no caller outside `tests/test_plugin_lockfile.py`: a comparison nobody
read says nothing on any surface. This row is that reader, so the assertions read the line
the user reads — a row that hides which bundle or which kind of drift fails here.
"""

from __future__ import annotations

import json
import shutil

import pytest

import ephe_cli


def _bundle(root, name: str, version: str = "1.0.0") -> None:
    folder = root / name
    folder.mkdir(parents=True)
    manifest = {
        "manifest_version": 1,
        "name": name,
        "version": version,
        "description": f"{name} test bundle",
        "permissions": {"tool_families": [], "data_roots": []},
        "components": {"skills": [], "commands": []},
    }
    (folder / "ephe-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (folder / "README.md").write_text(f"{name} {version}\n", encoding="utf-8")


@pytest.fixture
def install(monkeypatch, tmp_path):
    """A device folder holding one installed bundle and the lock built from it."""
    from core.plugin_lockfile import build_lockfile, write_lockfile
    from core.plugin_mount_records import lockfile_path

    root = tmp_path / "plugins"
    root.mkdir()
    _bundle(root, "counter")
    monkeypatch.setattr("core.plugin_manifest.PLUGINS_ROOT_OVERRIDE", str(root))
    monkeypatch.setattr("core.plugin_store.config_root", lambda: tmp_path)
    write_lockfile(lockfile_path(), build_lockfile())
    return tmp_path


class TestPluginLockRow:
    def test_given_a_matching_install_when_read_then_the_row_says_the_lock_matches(self, install):
        ok, detail = ephe_cli._doctor_plugin_lock()
        assert ok is True
        assert "1 bundle(s) match the lock" in detail, detail

    def test_a_bundle_edited_after_the_lock_is_named_by_name_and_kind(self, install):
        readme = install / "plugins" / "counter" / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "edited in place\n", encoding="utf-8")

        ok, detail = ephe_cli._doctor_plugin_lock()
        assert ok is False
        assert "name=counter" in detail, detail
        assert "kind=sha256" in detail, detail

    def test_a_bundle_replaced_by_another_version_is_named_with_both_versions(self, install):
        shutil.rmtree(install / "plugins" / "counter")
        _bundle(install / "plugins", "counter", version="2.0.0")

        ok, detail = ephe_cli._doctor_plugin_lock()
        assert ok is False
        assert "name=counter" in detail and "kind=version" in detail, detail
        assert "1.0.0->2.0.0" in detail, detail

    def test_a_bundle_removed_under_the_lock_is_named_as_missing(self, install):
        shutil.rmtree(install / "plugins" / "counter")

        ok, detail = ephe_cli._doctor_plugin_lock()
        assert ok is False
        assert "name=counter" in detail and "kind=missing" in detail, detail

    def test_a_machine_with_no_lock_yet_is_a_state_and_not_a_failure(self, monkeypatch, tmp_path):
        monkeypatch.setattr("core.plugin_store.config_root", lambda: tmp_path)
        monkeypatch.setattr("core.plugin_manifest.PLUGINS_ROOT_OVERRIDE", str(tmp_path / "plugins"))

        ok, detail = ephe_cli._doctor_plugin_lock()
        assert ok is True
        assert "no plugin lockfile" in detail, detail


def test_the_doctor_names_one_command_for_a_drifted_bundle():
    """The row has to come with the step that clears it, or the reader stops at the red."""
    step, why = ephe_cli._doctor_next_step(["Plugin lock"], engine=object(), engine_usable=True)
    assert "plugin install" in step
    assert "drift" in why
