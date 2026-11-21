"""What the Creator tools promise, read against the contracts the lane ships.

Every assertion calls the same function the tool calls: `core.plugin_manifest` decides
whether a descriptor is loadable, `dir_sha256` is the artifact digest, the reserved-name
map and the activation scan are what the mount will consult, and `core.plugin_install`
owns the only path a directory takes to becoming a loadable plugin.

Staging lives under the device folder and the installed bundle under the plugins root, so
the fixture moves both into tmp_path through `EPHE_CONFIG_DIR` and `PLUGINS_ROOT_OVERRIDE`.
"""

from __future__ import annotations

import asyncio
import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest

from core import plugin_manifest, plugin_templates
from core.tools import creator_tools

CREATOR_TOOL_NAMES = {
    "create_plugin_scaffold",
    "read_plugin_source",
    "write_plugin_source",
    "verify_plugin_bundle",
    "install_plugin_bundle",
}


def _call(tool: str, **arguments) -> dict:
    """One tool call, answered as the envelope the tool really returns."""
    payload = getattr(creator_tools, tool)(**arguments)
    assert isinstance(payload, str), f"{tool} must answer a JSON string"
    return json.loads(payload)


@pytest.fixture()
def lane(tmp_path, monkeypatch):
    from core import plugin_runtime

    config = tmp_path / "cfg"
    (config / "plugins").mkdir(parents=True)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", config / "plugins")
    plugin_runtime.invalidate_ownership_cache()
    yield {"config": config, "root": config / "plugins", "tmp": tmp_path}
    plugin_runtime.invalidate_ownership_cache()


class TestScaffold:
    def test_writes_a_manifest_the_loader_accepts(self, lane):
        answer = _call(
            "create_plugin_scaffold", name="weather-card", description="Reads one sky."
        )
        manifest, error = plugin_manifest.load_manifest(Path(answer["bundle"]))
        assert error is None
        assert manifest["name"] == "weather-card"
        assert manifest["manifest_version"] == plugin_manifest.MANIFEST_VERSION_V2

    def test_ships_the_surface_the_manifest_declares(self, lane):
        answer = _call(
            "create_plugin_scaffold", name="weather-card", description="Reads one sky."
        )
        bundle = Path(answer["bundle"])
        manifest = json.loads((bundle / plugin_manifest.MANIFEST_FILENAME).read_text())
        entry = manifest["components"]["ui"]["entry"]
        assert (bundle / entry).is_file(), (
            "the declared surface entry has to ship with it"
        )

    def test_reports_the_files_it_shipped(self, lane):
        answer = _call(
            "create_plugin_scaffold", name="weather-card", description="Reads one sky."
        )
        bundle = Path(answer["bundle"])
        on_disk = sorted(
            path.relative_to(bundle).as_posix()
            for path in bundle.rglob("*")
            if path.is_file()
        )
        assert sorted(answer["files"]) == on_disk

    def test_names_the_author_it_was_told(self, lane):
        answer = _call(
            "create_plugin_scaffold",
            name="weather-card",
            description="Reads one sky.",
            publisher="Bemler Labs",
        )
        manifest = plugin_manifest.load_manifest(Path(answer["bundle"]))[0]
        assert manifest["publisher"]["name"] == "Bemler Labs"

    def test_refuses_a_name_the_loader_would_refuse(self, lane):
        answer = _call(
            "create_plugin_scaffold", name="Weather Card", description="Reads one sky."
        )
        assert answer["error"] == "invalid_bundle_name"
        assert answer["detail"] == "name: lowercase slug expected (a-z0-9-)"
        staging = creator_tools.bundles_root(lane["config"])
        assert list(staging.iterdir()) == []

    def test_refuses_a_description_the_loader_would_refuse(self, lane):
        answer = _call("create_plugin_scaffold", name="weather-card", description="   ")
        assert answer["error"] == "invalid_description"
        assert not creator_tools.bundle_dir("weather-card", lane["config"]).exists()

    def test_leaves_an_existing_bundle_untouched(self, lane):
        _call(
            "create_plugin_scaffold", name="weather-card", description="Reads one sky."
        )
        bundle = creator_tools.bundle_dir("weather-card", lane["config"])
        (bundle / "ui" / "app.js").write_text(
            "export const kept = 1;\n", encoding="utf-8"
        )
        answer = _call(
            "create_plugin_scaffold", name="weather-card", description="Reads one sky."
        )
        assert answer["error"] == "bundle_exists"
        assert "kept" in (bundle / "ui" / "app.js").read_text(encoding="utf-8")


class TestSourceWrite:
    def _bundle(self, name="weather-card"):
        _call("create_plugin_scaffold", name=name, description="Reads one sky.")
        return name

    def test_lands_a_file_inside_the_bundle(self, lane):
        name = self._bundle()
        answer = _call(
            "write_plugin_source",
            bundle=name,
            path="tools/sky.py",
            content="def run(arguments):\n    return {'sky': 'overcast'}\n",
        )
        bundle = creator_tools.bundle_dir(name, lane["config"])
        assert (bundle / "tools" / "sky.py").is_file()
        assert answer["bytes"] == (bundle / "tools" / "sky.py").stat().st_size

    def test_replaces_the_file_it_writes_again(self, lane):
        name = self._bundle()
        _call(
            "write_plugin_source", bundle=name, path="tools/sky.py", content="A = 1\n"
        )
        _call(
            "write_plugin_source", bundle=name, path="tools/sky.py", content="A = 2\n"
        )
        bundle = creator_tools.bundle_dir(name, lane["config"])
        assert (bundle / "tools" / "sky.py").read_text(encoding="utf-8") == "A = 2\n"

    def test_refuses_a_path_that_climbs_out_of_the_bundle(self, lane):
        name = self._bundle()
        answer = _call(
            "write_plugin_source", bundle=name, path="../escape.py", content="A = 1\n"
        )
        assert answer["error"] == "path_outside_bundle"
        staging = creator_tools.bundles_root(lane["config"])
        assert not (staging.parent / "escape.py").exists()

    def test_refuses_an_absolute_path(self, lane):
        name = self._bundle()
        answer = _call(
            "write_plugin_source", bundle=name, path="/etc/passwd", content="A = 1\n"
        )
        assert answer["error"] == "path_outside_bundle"

    def test_refuses_a_bundle_that_is_not_there(self, lane):
        answer = _call(
            "write_plugin_source",
            bundle="never-made",
            path="tools/sky.py",
            content="A\n",
        )
        assert answer["error"] == "bundle_missing"


class TestSourceRead:
    """The read half of the authoring loop: what the model is allowed to see of its own bundle.

    Live evidence 2026-11-09 (`/private/tmp/ephe-creation-eval/run5/runs.json`, creation-01
    against `deepseek-v4-pro`): the turn scaffolded twice, verified twice and never once
    called `write_plugin_source`, so both staged bundles held the 28-byte scaffold template
    and the loop ran out of its 16-round budget. The audit trail names what it reached for
    between the scaffold and the write — two refusals, each correct under its own rule:

        read_file  <config>/creator/plugins/countdown-timer/manifest.json
                   "is inside a protected root (~/.ephe ...); no approval can open it"
        read_file  <checkout>/plugins/countdown/manifest.json
                   "is not in the allowed directories"

    The staging folder lives under the device root (`bundles_root`, and `~/.ephe` is a
    DENY_ROOT in `core/path_guard.py`), so no approval opens it and the file tools were
    never the way in. The family that owns that folder shipped a write and no read, which
    left the author blind to the bytes it was editing.
    """

    def _bundle(self, name="weather-card"):
        _call("create_plugin_scaffold", name=name, description="Reads one sky.")
        return name

    def test_answers_with_the_bytes_the_scaffold_shipped(self, lane):
        name = self._bundle()
        bundle = creator_tools.bundle_dir(name, lane["config"])
        answer = _call("read_plugin_source", bundle=name, path="ephe-plugin.json")
        assert answer["content"] == (bundle / "ephe-plugin.json").read_text(
            encoding="utf-8"
        )

    def test_answers_with_what_write_plugin_source_put_there(self, lane):
        name = self._bundle()
        source = "export const sky = 'overcast';\n"
        _call("write_plugin_source", bundle=name, path="ui/app.js", content=source)
        answer = _call("read_plugin_source", bundle=name, path="ui/app.js")
        assert answer["content"] == source, "the read misses the write it follows"

    def test_names_the_bundle_and_the_path_it_read(self, lane):
        name = self._bundle()
        answer = _call("read_plugin_source", bundle=name, path="ui/index.html")
        assert answer["bundle"] == name
        assert answer["path"] == "ui/index.html"

    def test_refuses_a_path_that_climbs_out_of_the_bundle(self, lane):
        name = self._bundle()
        answer = _call("read_plugin_source", bundle=name, path="../escape.json")
        assert answer["error"] == "path_outside_bundle"

    def test_refuses_an_absolute_path(self, lane):
        name = self._bundle()
        answer = _call("read_plugin_source", bundle=name, path="/etc/passwd")
        assert answer["error"] == "path_outside_bundle"

    def test_refuses_a_bundle_that_is_not_there(self, lane):
        answer = _call("read_plugin_source", bundle="never-made", path="ui/app.js")
        assert answer["error"] == "bundle_missing"

    def test_refuses_a_file_that_is_not_there(self, lane):
        name = self._bundle()
        answer = _call("read_plugin_source", bundle=name, path="ui/missing.js")
        assert answer["error"] == "source_missing"

    def test_refuses_a_directory(self, lane):
        name = self._bundle()
        answer = _call("read_plugin_source", bundle=name, path="ui")
        assert answer["error"] == "path_is_a_directory"

    def test_a_link_inside_the_bundle_does_not_open_the_device_root(self, lane):
        """A bundle is authored by calls, but a folder can arrive from anywhere.

        The confinement is `resolve()` before the prefix test, so a link out of the
        staging folder answers the same refusal a `..` gets.
        """
        name = self._bundle()
        bundle = creator_tools.bundle_dir(name, lane["config"])
        outside = lane["config"] / "secret.txt"
        outside.write_text("device state", encoding="utf-8")
        (bundle / "ui" / "link.js").symlink_to(outside)
        answer = _call("read_plugin_source", bundle=name, path="ui/link.js")
        assert answer.get("error") == "path_outside_bundle", answer

    def test_answers_within_the_context_cap_and_says_so(self, lane):
        """A read that returns more than the turn can hold is a read the turn loses.

        `file_ops.MAX_FILE_CHARS` is the cap the read tools already answer with, so an
        author who wrote a large asset is told the rest is on disk instead of being
        handed the file whole.
        """
        from core.tools.file_ops import MAX_FILE_CHARS

        name = self._bundle()
        source = "x" * (MAX_FILE_CHARS + 10)
        _call("write_plugin_source", bundle=name, path="ui/app.js", content=source)
        answer = _call("read_plugin_source", bundle=name, path="ui/app.js")
        assert len(answer["content"]) == MAX_FILE_CHARS
        assert answer["truncated"] is True
        assert answer["bytes"] == len(source.encode("utf-8"))
        short = _call("read_plugin_source", bundle=name, path="ephe-plugin.json")
        assert short["truncated"] is False


class TestVerify:
    def _scaffold(self, name="weather-card"):
        _call("create_plugin_scaffold", name=name, description="Reads one sky.")
        return creator_tools.bundle_dir(name)

    def test_passes_the_bundle_it_just_scaffolded(self, lane):
        bundle = self._scaffold()
        answer = _call("verify_plugin_bundle", bundle="weather-card")
        assert answer["ok"] is True, answer
        assert answer["bundle"] == str(bundle)

    def test_answers_with_the_loaders_own_error(self, lane):
        bundle = self._scaffold()
        manifest = json.loads((bundle / plugin_manifest.MANIFEST_FILENAME).read_text())
        del manifest["license"]
        _write_manifest(bundle, manifest)
        answer = _call("verify_plugin_bundle", bundle="weather-card")
        assert answer["ok"] is False
        assert answer["error"] == "manifest_invalid"
        assert answer["problems"] == ["license: SPDX identifier expected"]

    def test_names_the_entry_the_confined_worker_cannot_find(self, lane):
        bundle = self._scaffold()
        _call(
            "write_plugin_source",
            bundle="weather-card",
            path="tools/sky.py",
            content="def run(a):\n    return 1\n",
        )
        manifest = json.loads((bundle / plugin_manifest.MANIFEST_FILENAME).read_text())
        manifest["permissions"]["tool_families"] = ["read"]
        manifest["components"]["tools"] = [
            {
                "name": "sky_read",
                "entry": "tools/missing.py:run",
                "family": "read",
                "description": "Reads the one sky this bundle knows.",
            }
        ]
        _write_manifest(bundle, manifest)
        answer = _call("verify_plugin_bundle", bundle="weather-card")
        assert answer["ok"] is False
        assert answer["error"] == "manifest_invalid"
        assert any("tools.missing:run" in problem for problem in answer["problems"])

    def test_hashes_the_bytes_it_read(self, lane):
        bundle = self._scaffold()
        before = _call("verify_plugin_bundle", bundle="weather-card")
        assert before["sha256"] == plugin_manifest.dir_sha256(bundle)
        _call(
            "write_plugin_source",
            bundle="weather-card",
            path="ui/app.js",
            content="export const v = 2;\n",
        )
        after = _call("verify_plugin_bundle", bundle="weather-card")
        assert after["sha256"] != before["sha256"]
        assert after["sha256"] == plugin_manifest.dir_sha256(bundle)

    def test_refuses_a_name_the_registry_holds(self, lane):
        bundle = self._scaffold()
        _call(
            "write_plugin_source",
            bundle="weather-card",
            path="tools/sky.py",
            content="def run(a):\n    return 1\n",
        )
        manifest = json.loads((bundle / plugin_manifest.MANIFEST_FILENAME).read_text())
        manifest["permissions"]["tool_families"] = ["vision"]
        manifest["components"]["tools"] = [
            {
                "name": "take_screenshot",
                "entry": "tools/sky.py:run",
                "family": "vision",
                "description": "Takes the name the kernel already serves.",
            }
        ]
        _write_manifest(bundle, manifest)
        answer = _call("verify_plugin_bundle", bundle="weather-card")
        assert answer["ok"] is False
        assert answer["error"] == "name_reserved"
        assert "take_screenshot" in json.dumps(answer["problems"])

    def test_refuses_a_bundle_that_is_not_there(self, lane):
        answer = _call("verify_plugin_bundle", bundle="never-made")
        assert answer["error"] == "bundle_missing"

    def test_a_bundle_the_loader_refuses_cannot_be_installed(self, lane):
        bundle = self._scaffold()
        _write_manifest(bundle, {"manifest_version": 2, "name": "weather-card"})
        answer = _call("install_plugin_bundle", bundle="weather-card")
        assert answer["error"] == "not_verified"
        assert list(lane["root"].iterdir()) == []


class TestInstall:
    def _verified(self, name="weather-card"):
        _call("create_plugin_scaffold", name=name, description="Reads one sky.")
        _call("verify_plugin_bundle", bundle=name)
        return name

    def test_places_the_bundle_where_the_scanner_reads(self, lane):
        name = self._verified()
        answer = _call("install_plugin_bundle", bundle=name)
        assert answer["status"] == "installed", answer
        installed = lane["root"] / name
        assert (installed / plugin_manifest.MANIFEST_FILENAME).is_file()
        scanned = {entry["dir"].name: entry for entry in plugin_manifest.scan_plugins()}
        assert name in scanned
        assert scanned[name]["error"] is None

    def test_the_artifact_is_the_one_the_staging_had(self, lane):
        name = self._verified()
        verified = _call("verify_plugin_bundle", bundle=name)
        answer = _call("install_plugin_bundle", bundle=name)
        assert answer["sha256"] == verified["sha256"]
        assert answer["sha256"] == plugin_manifest.dir_sha256(lane["root"] / name)

    def test_says_who_vouches_for_the_bytes(self, lane):
        answer = _call("install_plugin_bundle", bundle=self._verified())
        assert answer["trust"] == "local"
        assert answer["warning"] == "local_trust"

    def test_refuses_a_bundle_that_is_not_there(self, lane):
        answer = _call("install_plugin_bundle", bundle="never-made")
        assert answer["error"] == "bundle_missing"
        assert list(lane["root"].iterdir()) == []

    def test_reports_the_install_paths_own_refusal(self, lane, monkeypatch):
        name = self._verified()
        seen: dict = {}

        def refuse(*args, **kwargs):
            seen["called"] = True
            return {
                "status": "downgrade_refused",
                "name": name,
                "error": "installed 9.9.9",
            }

        monkeypatch.setattr(creator_tools, "install_from_marketplace", refuse)
        answer = _call("install_plugin_bundle", bundle=name)
        assert seen["called"] is True
        assert answer["error"] == "install_refused"
        assert answer["detail"]["status"] == "downgrade_refused"

    def test_carries_the_staging_bundle_as_a_named_directory(self, lane, monkeypatch):
        """The zip the one install path unpacks has to name the bundle it installs."""
        name = self._verified()
        captured: dict = {}

        def spy(bundle_name, **kwargs):
            fetcher = kwargs["fetcher"]
            captured["payload"] = fetcher("creator://weather-card.zip")
            return {"status": "refused", "name": bundle_name, "error": "spied"}

        monkeypatch.setattr(creator_tools, "install_from_marketplace", spy)
        _call("install_plugin_bundle", bundle=name)
        assert captured, "install never handed the artifact to the one path"
        archive = zipfile.ZipFile(io.BytesIO(captured["payload"]))
        members = archive.namelist()
        assert members and all(member.startswith(f"{name}/") for member in members)


class TestWaveBoundary:
    """#26 landed: the consent gate owns who may call these, and the kernel map dispatches them.

    Two pins this class wrote while the gate was open are dissolved. The dispatch map
    reaches the creator names now, and Creator mode is offered them; that the call is
    refused without the privilege, and that no other mode sees the names, is pinned in
    ``tests/test_creator_guard.py`` (`TestDispatchWiring`, `TestOfferWiring`), beside the
    rule itself. What stays here is the one assertion that file cannot make: these names
    are a promise the mode notice and the docs state, so the set is written here
    and checked against both places production derives it.
    """

    def test_the_three_places_that_name_the_calls_agree(self):
        """The schemas, the guard's vocabulary and this file's list are one set."""
        from core.tools import creator_guard

        named = {
            schema["function"]["name"] for schema in creator_tools.CREATOR_TOOL_SCHEMAS
        }
        assert named == CREATOR_TOOL_NAMES == set(creator_guard.CREATOR_TOOL_NAMES)


def _write_manifest(bundle: Path, manifest: dict) -> None:
    (bundle / plugin_manifest.MANIFEST_FILENAME).write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


class TestKernelDispatch:
    """The creator calls reach the kernel the way a chat turn reaches them: execute_tool.

    `_call` above invokes the Python handler, which is what let #27 ship plain `def`
    functions into a dispatcher that awaits every return
    (`result = await func(**arguments)`, core/tools/registry.py). Live evidence
    2026-11-09 (/private/tmp/ephe-creation-eval/run4/runs.json, 4 failed calls): the
    scaffold ran — the bundle is on disk — and its `str` return was then awaited, so every
    Creator call answered `object str can't be used in 'await' expression` and the turn
    stopped with nothing to show for it. The handler running while its answer is lost is
    the worst shape of this bug: the file exists, the model is told it failed.
    """

    async def test_execute_tool_runs_the_scaffold_and_returns_its_answer(self, lane):
        from core.tools.registry import execute_tool

        answer = await execute_tool(
            "create_plugin_scaffold",
            {"name": "weather-card", "description": "Reads one sky."},
        )

        assert isinstance(answer, str), type(answer)
        assert "[tool-error" not in answer, answer
        payload = json.loads(answer)
        assert payload["name"] == "weather-card"
        assert Path(payload["bundle"]).is_dir()

    async def test_a_creator_chain_runs_end_to_end_through_the_kernel(self, lane):
        """scaffold → write → read → verify → install, the order the mode instruction teaches.

        The read is the step run5 could not take: it is what tells the author whether the
        bytes it is about to replace are the ones it thinks they are.
        """
        from core.tools.registry import execute_tool

        source = "export const sky = 'overcast';\n"
        steps = [
            (
                "create_plugin_scaffold",
                {"name": "weather-card", "description": "Reads one sky."},
            ),
            (
                "write_plugin_source",
                {
                    "bundle": "weather-card",
                    "path": "ui/app.js",
                    "content": source,
                },
            ),
            ("read_plugin_source", {"bundle": "weather-card", "path": "ui/app.js"}),
            ("verify_plugin_bundle", {"bundle": "weather-card"}),
            ("install_plugin_bundle", {"bundle": "weather-card"}),
        ]
        answers = []
        for name, arguments in steps:
            answer = await execute_tool(name, arguments)
            assert "[tool-error" not in str(answer), f"{name}: {answer}"
            answers.append(answer)

        assert json.loads(answers[2])["content"] == source
        installed = json.loads(answers[-1])
        assert installed["bundle"], "the install answer names no bundle"
        assert Path(lane["root"], "weather-card").exists() is Path(installed["bundle"]).is_dir()


def _app():
    """The real app, with the plugin surface routes mounted and no LAN token."""
    from server.main import create_app

    return create_app(lan_mode=False)


def _request(app, path: str, *, method: str = "GET", headers: dict | None = None):
    """One request through the middleware stack as the app's own desktop client.

    A mutation on loopback carries the `Origin` the shell sends and the XHR marker
    the plugin routes' mutation guard requires.
    """
    sent = dict(headers or {})
    if method not in {"GET", "HEAD", "OPTIONS"}:
        sent.setdefault("Origin", "http://127.0.0.1:8765")
        sent.setdefault("X-Requested-With", "XMLHttpRequest")
    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 54321))

    async def run():
        async with httpx.AsyncClient(
            transport=transport, base_url="http://127.0.0.1:8765"
        ) as client:
            return await client.request(method, path, headers=sent)

    return asyncio.run(run())


def _mount_body(app, name: str):
    """`(nonce, document)` for one installed surface: the credential, then its page."""
    minted = _request(app, f"/api/plugins/{name}/surface-token", method="POST")
    assert minted.status_code == 200, minted.text
    nonce = minted.json()["surface"]
    return nonce, _request(app, f"/api/plugins/ui/{name}/{nonce}/")


class TestTemplateFamily:
    """A plugin exists before a model writes a line: the template is the whole bundle.

    `create_plugin_scaffold` used to ship one shape — a floating window, two assets, no
    tool — so every other ask had to be authored file by file by the model, which is
    where the live runs spent their round budget. The template family renders the
    manifest and the files from parameters, and the Creator tools keep their promises
    on the result: the loader accepts it, the install path takes it, the mount answers
    it.
    """

    @pytest.mark.parametrize("key", sorted(plugin_templates.TEMPLATES))
    def test_a_template_verifies_installs_and_needs_no_model(self, lane, key):
        name = f"wish-{key}"
        answer = _call(
            "create_plugin_scaffold",
            name=name,
            description="Answers the one ask this template covers.",
            template=key,
        )
        assert "bundle" in answer, answer
        verified = _call("verify_plugin_bundle", bundle=name)
        assert verified["ok"] is True, verified
        installed = _call("install_plugin_bundle", bundle=name)
        assert installed["status"] == "installed", installed
        manifest = plugin_manifest.load_manifest(lane["root"] / name)[0]
        assert manifest["manifest_version"] == plugin_manifest.MANIFEST_VERSION_V2
        assert (lane["root"] / name / "README.md").is_file()

    @pytest.mark.parametrize("key", sorted(plugin_templates.TEMPLATES))
    def test_the_family_the_template_grants_is_the_one_it_declares(self, lane, key):
        name = f"wish-{key}"
        answer = _call(
            "create_plugin_scaffold",
            name=name,
            description="Answers the one ask this template covers.",
            template=key,
        )
        manifest = json.loads(
            (Path(answer["bundle"]) / plugin_manifest.MANIFEST_FILENAME).read_text(
                encoding="utf-8"
            )
        )
        families = manifest["permissions"]["tool_families"]
        assert families == list(plugin_templates.TEMPLATES[key].families)
        assert ("network" in families) is (key == "network-tool")

    def test_the_tool_template_ships_the_tool_the_mount_reads(self, lane):
        answer = _call(
            "create_plugin_scaffold",
            name="sky-report",
            description="Reports the sky over one town.",
            template="surface-tool",
        )
        manifest = json.loads(
            (Path(answer["bundle"]) / plugin_manifest.MANIFEST_FILENAME).read_text(
                encoding="utf-8"
            )
        )
        from core.plugin_tools_contract import tool_claims

        assert [claim.name for claim in tool_claims(manifest)] == ["sky_report"]
        verified = _call("verify_plugin_bundle", bundle="sky-report")
        assert verified["ok"] is True, verified
        assert verified["tools"] == ["sky_report"]

    def test_an_unknown_wish_is_refused_with_the_templates_that_exist(self, lane):
        """A wish outside the family is a coded answer with a next step, not a traceback."""
        answer = _call(
            "create_plugin_scaffold",
            name="holo-deck",
            description="A hologram over the desk.",
            template="holo-deck",
        )
        assert answer["error"] == "unknown_template", answer
        assert sorted(answer["templates"]) == sorted(plugin_templates.TEMPLATES)
        assert answer["next"]
        assert list(creator_tools.bundles_root(lane["config"]).iterdir()) == []

    def test_a_surface_template_answers_on_the_mount(self, lane, monkeypatch):
        """A generated plugin, with nothing written after the scaffold, is a live page."""
        monkeypatch.setenv("EPHE_OFFLINE", "1")
        name = "countdown-widget"
        _call(
            "create_plugin_scaffold",
            name=name,
            description="Counts down to the date you picked.",
            title="Countdown",
        )
        _call("verify_plugin_bundle", bundle=name)
        installed = _call("install_plugin_bundle", bundle=name)
        assert installed["status"] == "installed", installed

        from core import plugin_runtime

        plugin_runtime.lifecycle().set_enabled(name, True, actor="test")
        plugin_runtime.invalidate_ownership_cache()

        _nonce, document = _mount_body(_app(), name)
        assert document.status_code == 200, document.text
        assert 'data-role="line"' in document.text
        assert "Countdown" in document.text

    async def test_an_unknown_wish_answers_an_envelope_through_the_kernel(self, lane):
        """The dispatch path adds no traceback of its own around the coded refusal."""
        from core.tools.registry import execute_tool

        answer = await execute_tool(
            "create_plugin_scaffold",
            {
                "name": "holo-deck",
                "description": "A hologram over the desk.",
                "template": "holo-deck",
            },
        )
        assert "[tool-error" not in str(answer), answer
        payload = json.loads(answer)
        assert payload["error"] == "unknown_template"
        assert payload["templates"]
