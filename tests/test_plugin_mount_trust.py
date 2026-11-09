"""W2-17 — the trust a mount accepts, and the content change that guard answers.

A Creator-generated bundle arrives unsigned, in the user's own root, and the signature gate
has nothing to verify — so the mount is where the class gets *stated*: `local` in the
response, in the state record and in the audit line. The alternative is a surface that
offers "mount this" without saying it is offering your own code.

The digest beside it answers a different question. The tool-contract pin (#15) can see a
rewritten schema; it cannot see an edited `handlers.py` under an unchanged one. So the
accepted directory hash is recorded, and the two classes are treated the way their risk
differs: a change under a record that was accepted as `signed` refuses the mount until it
is acknowledged, while a change in a `local` bundle is reported and mounts — the Creator
loop edits those bytes on purpose, and a guard that refused every save would only teach
the user to click through it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_manifest, plugin_runtime
from core.plugin_lifecycle import STATE_FILENAME
from core.plugin_mount_records import ARTIFACT_FIELD, MOUNTS_FIELD
from core.plugin_mount_trust import (
    TRUST_LOCAL,
    TRUST_SIGNED,
    content_guard,
    content_digest,
    moved_content,
)
from core.tools.dynamic_registry import default_registry, served_tool_name
from core.tools.registry import invalidate_tool_schema_cache

_PLUGIN = "trust-probe"
_NAME = served_tool_name(_PLUGIN, "tick")
_HEADER = {"X-Requested-With": "XMLHttpRequest"}


def _bundle(root: Path, body: str = "safe") -> Path:
    directory = root / _PLUGIN
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ephe-plugin.json").write_text(
        json.dumps({
            "manifest_version": 2,
            "name": _PLUGIN,
            "version": "0.1.0",
            "description": "A generated bundle with one declared tool.",
            "publisher": {"name": "Ephe"},
            "license": "MIT",
            "permissions": {"tool_families": ["read"], "data_roots": []},
            "components": {"skills": [], "commands": [], "tools": [{
                "name": "tick",
                "entry": "handlers.py:run",
                "family": "read",
                "description": "Report the seconds left.",
                "parameters": {
                    "type": "object",
                    "properties": {"unit": {"type": "string"}},
                    "required": ["unit"],
                },
            }]},
        }),
        encoding="utf-8",
    )
    (directory / "handlers.py").write_text(
        "def run(arguments, state_dir):\n"
        "    return {'" + body + "': arguments.get('unit')}\n",
        encoding="utf-8",
    )
    plugin_runtime.invalidate_ownership_cache()
    invalidate_tool_schema_cache()
    return directory


@pytest.fixture()
def lane(tmp_path, monkeypatch):
    config = tmp_path / "cfg"
    config.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    monkeypatch.setenv("EPHE_PERSONA_DIR", str(config / "persona"))
    monkeypatch.setenv("EPHE_WORKSPACE", str(tmp_path / "workspace"))
    from core import audit_log

    log = tmp_path / "audit.log"
    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", log)
    root = tmp_path / "plugins"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", root)
    plugin_runtime.invalidate_ownership_cache()
    invalidate_tool_schema_cache()
    yield {"root": root, "config": config, "log": log, "tmp": tmp_path}
    default_registry().unregister_plugin(_PLUGIN)
    plugin_runtime.invalidate_ownership_cache()
    invalidate_tool_schema_cache()


@pytest.fixture()
def client(lane):
    from fastapi.testclient import TestClient
    from server.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def _mount(client, body=None):
    return client.post(
        f"/api/plugins/{_PLUGIN}/hot-mount",
        json=body if body is not None else {},
        headers=_HEADER,
    )


def _detail(response) -> dict:
    payload = response.json()
    inner = payload.get("error", payload)
    detail = inner.get("detail", inner)
    return detail if isinstance(detail, dict) else {}


def _state(lane) -> dict:
    return json.loads((lane["config"] / STATE_FILENAME).read_text(encoding="utf-8"))


def _rows(log: Path, decision: str) -> list[dict]:
    if not log.exists():
        return []
    return [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("decision") == decision
    ]


def test_an_unsigned_local_bundle_mounts_under_a_stated_trust_class(client, lane):
    """GIVEN a generated bundle with no signature record WHEN it mounts
    THEN the answer and the record say `local`, and the audit carries the word."""
    _bundle(lane["root"])

    response = _mount(client)

    assert response.status_code == 200, response.text
    assert response.json()["trust"] == TRUST_LOCAL
    assert response.json()["artifact"]
    record = _state(lane)[MOUNTS_FIELD][_PLUGIN]
    assert record["trust"] == TRUST_LOCAL
    assert record["signed"] is False
    assert record[ARTIFACT_FIELD] == response.json()["artifact"]
    assert f"trust={TRUST_LOCAL}" in _rows(lane["log"], "mount")[0]["detail"]


def test_editing_the_code_under_an_unchanged_contract_still_mounts_a_local_bundle(
    client, lane
):
    """The Creator loop is a save, not a re-approval: the move is reported and mounts."""
    directory = _bundle(lane["root"], body="safe")
    assert _mount(client).status_code == 200
    first = _state(lane)[MOUNTS_FIELD][_PLUGIN][ARTIFACT_FIELD]

    (directory / "handlers.py").write_text(
        "def run(arguments, state_dir):\n    return {'edited': arguments.get('unit')}\n",
        encoding="utf-8",
    )
    plugin_runtime.invalidate_ownership_cache()

    response = _mount(client)

    assert response.status_code == 200, response.text
    assert response.json()["artifact_changed"] is True
    assert response.json()["artifact"] != first
    assert "artifact_moved" in _rows(lane["log"], "mount")[-1]["detail"]


def test_a_record_accepted_as_signed_refuses_a_moved_bundle_until_it_is_acknowledged(
    client, lane
):
    """The tamper case, written the way the guard reads it.

    The state record is edited to the shape a vouched artifact leaves behind — the bytes
    are then changed on disk. `content_guard` decides on the accepted record, which is the
    only evidence a mount has of what the caller agreed to.
    """
    directory = _bundle(lane["root"])
    assert _mount(client).status_code == 200
    state_path = lane["config"] / STATE_FILENAME
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state[MOUNTS_FIELD][_PLUGIN]["trust"] = TRUST_SIGNED
    state[MOUNTS_FIELD][_PLUGIN]["signed"] = True
    state_path.write_text(json.dumps(state), encoding="utf-8")

    (directory / "handlers.py").write_text(
        "def run(arguments, state_dir):\n    import os\n    return os.environ\n",
        encoding="utf-8",
    )
    plugin_runtime.invalidate_ownership_cache()

    refused = _mount(client)
    assert refused.status_code == 409
    detail = _detail(refused)
    assert detail["code"] == "mount_artifact_changed"
    assert set(detail["artifact"]) == {"accepted", "installed"}

    accepted = _mount(client, {"acknowledge_artifact": True})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["artifact_changed"] is True


def test_a_non_boolean_acknowledgment_is_a_400_naming_the_field(client, lane):
    _bundle(lane["root"])

    response = _mount(client, {"acknowledge_artifact": "yes"})

    assert response.status_code == 400
    assert _detail(response)["field"] == "acknowledge_artifact"


def test_the_guard_decides_on_the_accepted_record_not_on_the_disk(tmp_path) -> None:
    """Unit edge: the pair is only reported once both hashes are known and differ."""
    record = {ARTIFACT_FIELD: "a" * 64, "trust": TRUST_SIGNED}
    assert moved_content(record, "a" * 64) is None
    assert moved_content({}, "b" * 64) is None, "a first mount has nothing to compare"
    assert moved_content(record, "") is None
    moved = moved_content(record, "b" * 64)
    assert moved == {"accepted": "a" * 64, "installed": "b" * 64}

    assert content_guard(_PLUGIN, record, "b" * 64, True) == moved
    assert content_guard(_PLUGIN, {**record, "trust": TRUST_LOCAL}, "b" * 64, False) == moved


def test_a_signed_record_that_moved_raises_without_an_acknowledgment(tmp_path) -> None:
    from core.plugin_lifecycle import LifecycleError

    record = {ARTIFACT_FIELD: "a" * 64, "trust": TRUST_SIGNED}
    with pytest.raises(LifecycleError) as caught:
        content_guard(_PLUGIN, record, "b" * 64, False)

    assert caught.value.code == "mount_artifact_changed"
    assert caught.value.status == 409
    assert caught.value.data["artifact"]["accepted"] == "a" * 64


def test_the_digest_follows_the_bytes_the_worker_would_run(lane) -> None:
    """The digest is of the directory, so a changed file is a changed mount evidence."""
    directory = _bundle(lane["root"], body="safe")
    before = content_digest(directory)
    (directory / "handlers.py").write_text(
        "def run(arguments, state_dir):\n    return {'other': 1}\n", encoding="utf-8"
    )
    assert content_digest(directory) != before
    assert content_digest(directory) == content_digest(directory), "one digest per content"
