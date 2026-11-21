"""The model-facing contract of the creator calls: the sentence, the fields, the refusals.

A tool description is the only specification a model reads before it calls: when to reach
for the call, when not to, an example, and what each parameter must carry. `errors` are the
other half — every refusal has to name (a) the code, (b) the reason, (c) the next call, or
the author is left to guess. The descriptions below are pinned on purpose: a reworded
sentence is a contract change a model has to re-learn, so the diff has to be deliberate.

Both halves are read through the registry envelope the model really receives
(`CREATOR_TOOL_SCHEMAS`).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import plugin_manifest
from core.tools import creator_tools

#: The five names Creator mode offers, and no sixth.
CREATOR_TOOL_NAMES = {
    "create_plugin_scaffold",
    "read_plugin_source",
    "write_plugin_source",
    "verify_plugin_bundle",
    "install_plugin_bundle",
}

#: Pinned, per tool. A model that read only this sentence has to know what the call does,
#: what it must not be used for, and what a valid call looks like.
DESCRIPTIONS = {
    "create_plugin_scaffold": (
        "Drafts a whole declarative Ephe plugin bundle in the creator's staging "
        "folder from one template: the Manifest v2 descriptor, the html surface and "
        "its assets, an optional tool and a README. The draft is kept only when the "
        "plugin loader reads it without an error. Use it first when the user asks for "
        "a plugin or a small Ephe extension, and pick the template whose shape "
        "matches the ask: `surface` for a window without a tool, `surface-tool` for a "
        "window that also brings one, `tool` for a tool alone and `network-tool` for "
        "a tool that needs `bridge.fetch`. Not for a name that is already staged: "
        "that draft is refused, so read it with read_plugin_source or pick another "
        "name. Every refusal carries the code, the reason and the next step. Example: "
        "create_plugin_scaffold(name=\"countdown\", description=\"Counts down to a set "
        "time.\", template=\"surface-tool\", tool=\"remaining\")"
    ),
    "read_plugin_source": (
        "Reads one file of one staged bundle: the text, the byte count, and whether the "
        "text was cut at the context cap. The path stays inside that bundle. Use it before "
        "replacing a file with write_plugin_source, and after a write to see what the bundle "
        "really holds. Not for files outside the staged bundle; the workspace file tools "
        "read those. "
        'Example: read_plugin_source(bundle="countdown", path="ephe-plugin.json")'
    ),
    "write_plugin_source": (
        "Writes or replaces one whole file inside one staged bundle. The path is "
        "bundle-relative and is refused when it leaves the bundle. Use it for the surface, "
        "its assets and manifest edits; read the file first, because a write replaces all of "
        "it and content you leave out is gone. Not for a partial edit or for a file in the "
        "workspace. "
        'Example: write_plugin_source(bundle="countdown", path="ui/app.js", '
        'content="export const left = 60;")'
    ),
    "verify_plugin_bundle": (
        "Checks one staged bundle against the rules the mount applies later: the manifest "
        "contract, the file every declared tool entry names, the tool names the registry "
        "already serves, and the digest of the bytes. It changes nothing, so it is safe to "
        "repeat. Use it after every write and before install_plugin_bundle; ok is true only "
        "when install will pass too. Not for deciding whether a bundle is welcome: it "
        "reports the contract, not the trust. The answer carries ok, sha256, problems and "
        "the next call."
    ),
    "install_plugin_bundle": (
        "Installs one staged bundle through the path a marketplace artifact takes, as an "
        "unsigned local artifact the person who wrote it vouches for. It re-reads the "
        "manifest first and refuses what verify_plugin_bundle reports. Use it after "
        "verify_plugin_bundle returned ok, when the user asked to keep or try the bundle. "
        "Not for a plugin from a marketplace listing; install that with `ephe plugin "
        "install`. "
        'Example: install_plugin_bundle(bundle="countdown")'
    ),
}

#: Every parameter of every creator schema, in the words the model reads.
PARAMETERS = {
    "create_plugin_scaffold": {
        "name": (
            "Bundle slug and folder name: lowercase letters, digits and dashes."
        ),
        "description": (
            "One non-empty sentence that the catalog shows."
        ),
        "template": (
            "The shape to draft: surface = one floating window and its page, no tool; "
            "surface-tool = the same window plus one tool the agent can call (read "
            "family); tool = one tool the agent can call, no window (read family); "
            "network-tool = one tool that reads the web through the host's bridge "
            "(network family). Defaults to surface."
        ),
        "publisher": (
            "Name a reader sees as the author; 'Independent' when left out."
        ),
        "license": (
            "SPDX identifier, for example 'MIT'; a proprietary reference when left "
            "out."
        ),
        "title": (
            "Window title of the declared surface; defaults to the bundle name."
        ),
        "tool": (
            "Tool name for a template that ships one (a-z0-9_); defaults to the "
            "bundle name in that spelling."
        ),
    },
    "read_plugin_source": {
        "bundle": "Name of a staged bundle, as create_plugin_scaffold answered it.",
        "path": (
            "Bundle-relative file path, for example 'ephe-plugin.json'; an absolute path "
            "or '..' is refused."
        ),
    },
    "write_plugin_source": {
        "bundle": "Name of a staged bundle, as create_plugin_scaffold answered it.",
        "path": (
            "Bundle-relative file path, for example 'ui/app.js'; an absolute path or '..' "
            "is refused."
        ),
        "content": "Full text of the file; the write replaces the file, so this is not a patch.",
    },
    "verify_plugin_bundle": {
        "bundle": "Name of a staged bundle, as create_plugin_scaffold answered it.",
    },
    "install_plugin_bundle": {
        "bundle": "Name of a staged bundle, as create_plugin_scaffold answered it.",
    },
}

#: The refusal codes each call answers with, and the next call the author can take.
NEXT_STEPS = {
    "invalid_bundle_name": (
        "Pick a lowercase slug (a-z, 0-9, dashes) and call create_plugin_scaffold again."
    ),
    "invalid_description": (
        "Pass one non-empty sentence as description and call create_plugin_scaffold again."
    ),
    "bundle_exists": "Read the staged bundle with read_plugin_source, or pick another name.",
    "bundle_missing": (
        "Call create_plugin_scaffold first, then retry with the name it answered."
    ),
    "path_outside_bundle": "Name one file inside the bundle, for example ui/app.js.",
    "path_is_a_directory": "Name a file inside the bundle, not a folder.",
    "content_not_text": "Send the file content as a string.",
    "source_missing": "Write the file first with write_plugin_source, then read it.",
    "not_verified": "Fix the problems verify_plugin_bundle reports, then install again.",
}


def _functions() -> dict[str, dict]:
    return {entry["function"]["name"]: entry["function"] for entry in creator_tools.CREATOR_TOOL_SCHEMAS}


def _call(tool: str, **arguments) -> dict:
    return json.loads(getattr(creator_tools, tool)(**arguments))


def test_the_schemas_offer_exactly_the_five_creator_calls():
    assert set(_functions()) == CREATOR_TOOL_NAMES


@pytest.mark.parametrize("name", sorted(DESCRIPTIONS))
def test_the_description_is_the_pinned_one(name: str) -> None:
    """GIVEN a creator call
    WHEN the model reads its description
    THEN it is the sentence this contract pins."""
    assert _functions()[name]["description"] == DESCRIPTIONS[name]


@pytest.mark.parametrize("name", sorted(DESCRIPTIONS))
def test_the_description_says_when_to_use_it_and_when_not_to(name: str) -> None:
    """A description that only says what the call does leaves the model guessing whether
    this is the ask it belongs to; "Not for" names the neighbouring case."""
    description = _functions()[name]["description"]
    assert "Use it" in description, f"{name}: no when-to-use sentence"
    assert "Not for" in description, f"{name}: no when-not-to-use sentence"


@pytest.mark.parametrize("name", sorted(DESCRIPTIONS))
def test_every_call_carries_an_example_except_the_check(name: str) -> None:
    """verify_plugin_bundle takes nothing but the bundle name, so its valid call is the
    schema itself; the four calls with a choice to make carry one."""
    description = _functions()[name]["description"]
    if name == "verify_plugin_bundle":
        assert "Example" not in description
    else:
        assert "Example:" in description, f"{name}: no example call"


@pytest.mark.parametrize("name", sorted(PARAMETERS))
def test_every_parameter_carries_the_pinned_description(name: str) -> None:
    properties = _functions()[name]["parameters"]["properties"]
    assert {
        key: properties[key]["description"] for key in properties
    } == PARAMETERS[name]


def test_the_required_parameters_are_the_ones_a_call_cannot_omit():
    """GIVEN each creator schema
    WHEN its required list is read
    THEN it names exactly the arguments the handler cannot run without."""
    by_name = _functions()
    pinned = {
        "create_plugin_scaffold": ["name", "description"],
        "read_plugin_source": ["bundle", "path"],
        "write_plugin_source": ["bundle", "path", "content"],
        "verify_plugin_bundle": ["bundle"],
        "install_plugin_bundle": ["bundle"],
    }
    assert {name: by_name[name]["parameters"]["required"] for name in pinned} == pinned


@pytest.fixture()
def lane(tmp_path, monkeypatch):
    from core import plugin_runtime

    config = tmp_path / "cfg"
    (config / "plugins").mkdir(parents=True)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", config / "plugins")
    plugin_runtime.invalidate_ownership_cache()
    yield {"config": config, "root": config / "plugins"}
    plugin_runtime.invalidate_ownership_cache()


#: One call per refusal code, with the argument that earns it. Every call is a plain
#: function: a refusal is a JSON answer, never an exception.
REFUSALS = {
    "invalid_bundle_name": ("create_plugin_scaffold", {"name": "Weather Card"}),
    "invalid_description": ("create_plugin_scaffold", {"name": "weather", "description": "  "}),
    "bundle_missing": ("write_plugin_source", {"bundle": "nope", "path": "a.py", "content": "x"}),
    "path_outside_bundle": (
        "write_plugin_source",
        {"bundle": "weather", "path": "../escape.py", "content": "x"},
    ),
    "path_is_a_directory": ("read_plugin_source", {"bundle": "weather", "path": "ui"}),
    "content_not_text": (
        "write_plugin_source",
        {"bundle": "weather", "path": "a.py", "content": 5},
    ),
    "source_missing": ("read_plugin_source", {"bundle": "weather", "path": "ui/none.js"}),
}


@pytest.mark.parametrize("code", sorted(REFUSALS))
def test_a_refusal_names_the_code_the_reason_and_the_next_call(lane, code: str) -> None:
    """GIVEN an author call the rules refuse
    WHEN it answers
    THEN it carries the code, a reason in words, and a next step — no exception."""
    tool, arguments = REFUSALS[code]
    if arguments.get("bundle") == "weather":
        _call("create_plugin_scaffold", name="weather", description="Reads one sky.")
    answer = _call(tool, **arguments)

    assert answer["error"] == code
    assert str(answer["detail"]).strip(), f"{code}: no reason"
    assert str(answer["next"]).strip(), f"{code}: no next step"
    assert NEXT_STEPS[code] in answer["next"]


def test_a_second_scaffold_of_one_name_is_refused_with_the_way_out(lane) -> None:
    _call("create_plugin_scaffold", name="weather", description="Reads one sky.")
    answer = _call("create_plugin_scaffold", name="weather", description="Reads one sky.")

    assert answer["error"] == "bundle_exists"
    assert NEXT_STEPS["bundle_exists"] in answer["next"]


def test_a_manifest_the_loader_refuses_cannot_be_installed(lane) -> None:
    _call("create_plugin_scaffold", name="weather", description="Reads one sky.")
    bundle = creator_tools.bundle_dir("weather", lane["config"])
    (bundle / plugin_manifest.MANIFEST_FILENAME).write_text(
        json.dumps({"manifest_version": 2, "name": "weather"}), encoding="utf-8"
    )

    answer = _call("install_plugin_bundle", bundle="weather")

    assert answer["error"] == "not_verified"
    assert NEXT_STEPS["not_verified"] in answer["next"]


def test_an_install_the_install_path_refuses_names_its_next_step(lane, monkeypatch) -> None:
    """The install path's own status is a code too; the answer frames it with a move."""
    _call("create_plugin_scaffold", name="weather", description="Reads one sky.")

    def refuse(*args, **kwargs):
        return {"status": "downgrade_refused", "name": "weather", "error": "installed 9.9.9"}

    monkeypatch.setattr(creator_tools, "install_from_marketplace", refuse)
    answer = _call("install_plugin_bundle", bundle="weather")

    assert answer["error"] == "install_refused"
    assert answer["detail"]["status"] == "downgrade_refused"
    assert "newer" in answer["next"]


def test_an_install_path_that_raises_still_answers_in_the_envelope(lane, monkeypatch) -> None:
    """GIVEN an install path that stops with an exception
    WHEN the author calls install_plugin_bundle
    THEN the call answers a coded refusal with the move, not a traceback."""
    _call("create_plugin_scaffold", name="weather", description="Reads one sky.")

    def explode(*args, **kwargs):
        raise OSError("disk gone")

    monkeypatch.setattr(creator_tools, "install_from_marketplace", explode)
    answer = _call("install_plugin_bundle", bundle="weather")

    assert answer["error"] == "install_raised"
    assert "OSError" in answer["detail"]
    assert next(iter(lane["root"].iterdir()), None) is None
    assert "audit row" in answer["next"]


def test_the_success_answers_keep_naming_the_next_call(lane) -> None:
    """The refusal contract is the mirror of the success one: both end on a move."""
    scaffold = _call("create_plugin_scaffold", name="weather", description="Reads one sky.")
    assert "write_plugin_source" in scaffold["next"]

    written = _call(
        "write_plugin_source", bundle="weather", path="ui/app.js", content="export const a = 1;\n"
    )
    assert "verify_plugin_bundle" in written["next"]

    verified = _call("verify_plugin_bundle", bundle="weather")
    assert verified["ok"] is True
    assert "install_plugin_bundle" in verified["next"]


def test_a_staged_name_is_a_folder_not_a_path(lane) -> None:
    """The bundle argument of every call is the staged folder's name; a path is refused
    with the same code the scaffold uses, so the model cannot write outside staging."""
    _call("create_plugin_scaffold", name="weather", description="Reads one sky.")
    answer = _call(
        "write_plugin_source", bundle="../weather", path="ui/app.js", content="x"
    )
    assert answer["error"] == "bundle_missing"
    assert Path(lane["root"]).parent.exists()
