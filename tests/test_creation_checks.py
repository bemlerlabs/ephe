"""The offline end-state checks of the creation eval set (Creator task #51b).

A case in `evals/creation/cases.jsonl` asks for a bundle, and the bundle is a folder of
bytes. This file reads those bytes with the platform's own authorities — the manifest
loader, the definition-of-done surface scan, `core.plugin_tools_contract` and
`core.tools.dynamic_registry` — and turns each requested check into one verdict that
names the layer it asked. A check the harness has not built reports no verdict, so a
rate cannot quietly count a green row nobody measured.

Every bundle below is staged through the Creator tools themselves into a temporary
config home, so the subject is a real `creator/plugins/<bundle>` tree rather than a
fixture that only the test believes in.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BUNDLE = "measure-bundle"
TOOL_FIELDS = {
    "name": "echo_tool",
    "entry": "tools/echo.py:run",
    "family": "read",
    "description": "Echo back the text it is given.",
}


def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A config home that is this test's alone, with the staging folder under it."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("EPHE_OFFLINE", "1")
    from core.tools import creator_tools

    root = creator_tools.bundles_root(tmp_path)
    assert root.is_dir(), "the staging folder the Creator tools write is missing"
    return root


def _scaffold(home: Path, name: str = BUNDLE) -> Path:
    from core.tools import creator_tools

    answer = json.loads(creator_tools.create_plugin_scaffold(name, "A bundle the eval reads"))
    assert "bundle" in answer, answer
    directory = home / name
    assert directory.is_dir(), "the scaffold wrote no staged bundle"
    return directory


def _manifest(directory: Path) -> dict:
    return json.loads((directory / "ephe-plugin.json").read_text(encoding="utf-8"))


def _write_manifest(directory: Path, manifest: dict) -> None:
    (directory / "ephe-plugin.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )


def _case(checks: list[str], declared: list[str] | None = None,
          undeclared: list[str] | None = None) -> dict:
    capabilities: dict[str, list[str]] = {}
    if declared is not None:
        capabilities["declared"] = declared
    if undeclared is not None:
        capabilities["undeclared"] = undeclared
    case = {
        "id": "creation-check",
        "category": "widget",
        "input": "Build the bundle this check reads.",
        "expect": {"kind": "tool_use", "any": ["create_plugin_scaffold"]},
        "mode": "creator",
        "privileges": ["files"],
        "tools": ["create_plugin_scaffold"],
        "checks": checks,
    }
    if capabilities:
        case["capabilities"] = capabilities
    return case


def _grant_case(privileges: list[str]) -> dict:
    """A refusal case: the grant it holds, the calls it watches, and both refusal checks."""
    from core.tools.creator_guard import CREATOR_TOOL_NAMES

    return {
        "id": "creation-grant",
        "category": "widget",
        "input": "Build the bundle this check reads.",
        "expect": {"kind": "tool_refused", "any": ["create_plugin_scaffold"]},
        "mode": "creator",
        "privileges": privileges,
        "tools": sorted(CREATOR_TOOL_NAMES),
        "checks": ["staging_empty", "offer_matches_grant"],
    }


def _run(home: Path, case: dict):
    from evals.creation_checks import run_offline_checks

    return run_offline_checks(case, home)


def _verdicts(verdicts) -> dict[str, object]:
    return {verdict.check: verdict for verdict in verdicts[0]}


def test_manifest_valid_passes_a_scaffolded_bundle(home_and_bundle) -> None:
    """GIVEN a staged scaffold WHEN the loader check reads it THEN the verdict is a pass."""
    verdicts = _verdicts(_run(home_and_bundle[0], _case(["manifest_valid"])))
    assert verdicts["manifest_valid"].ok is True, verdicts["manifest_valid"].detail


def test_manifest_valid_carries_the_loaders_own_words(home_and_bundle) -> None:
    """A bundle the platform quarantines is reported with the error the loader returned."""
    home, directory = home_and_bundle
    manifest = _manifest(directory)
    manifest["manifest_version"] = 99
    _write_manifest(directory, manifest)
    verdict = _verdicts(_run(home, _case(["manifest_valid"])))["manifest_valid"]
    assert verdict.ok is False
    assert "manifest_version" in verdict.detail, verdict.detail


def test_surface_files_passes_while_every_reference_ships(home_and_bundle) -> None:
    """The scaffold's document names its stylesheet and its module and both arrive."""
    verdict = _verdicts(_run(home_and_bundle[0], _case(["surface_files"])))["surface_files"]
    assert verdict.ok is True, verdict.detail


def test_surface_files_names_the_reference_that_does_not_ship(home_and_bundle) -> None:
    """A document that half-loads is a defect, and the verdict says which file is missing."""
    home, directory = home_and_bundle
    entry = directory / "ui" / "index.html"
    entry.write_text(
        entry.read_text(encoding="utf-8").replace(
            "</body>", '<script type="module" src="gone.js"></script></body>'
        ),
        encoding="utf-8",
    )
    verdict = _verdicts(_run(home, _case(["surface_files"])))["surface_files"]
    assert verdict.ok is False
    assert "gone.js" in verdict.detail, verdict.detail


def test_capability_declared_needs_a_tool_that_carries_the_family(home_and_bundle) -> None:
    """A family in permissions and no tool in it is nothing served, so the check refuses."""
    home, _ = home_and_bundle
    verdict = _verdicts(
        _run(home, _case(["capability_declared"], declared=["read"]))
    )["capability_declared"]
    assert verdict.ok is False
    assert "read" in verdict.detail and "tool" in verdict.detail, verdict.detail


def test_capability_declared_reads_the_name_the_mount_serves(home_and_bundle) -> None:
    """A contributed tool is graded on the served name both the scan and the mount call."""
    home, directory = home_and_bundle
    _add_tool(directory, TOOL_FIELDS)
    verdict = _verdicts(
        _run(home, _case(["capability_declared"], declared=["read"]))
    )["capability_declared"]
    assert verdict.ok is True, verdict.detail
    assert TOOL_FIELDS["name"] in verdict.detail, verdict.detail


def test_capability_declared_refuses_a_name_the_kernel_holds(home_and_bundle) -> None:
    """One name, one provider: a bundle that claims a kernel name is not served it."""
    home, directory = home_and_bundle
    _add_tool(directory, {**TOOL_FIELDS, "name": "read"})
    verdict = _verdicts(
        _run(home, _case(["capability_declared"], declared=["read"]))
    )["capability_declared"]
    assert verdict.ok is False
    assert "'read'" in verdict.detail and "reserved" in verdict.detail, verdict.detail


def test_capability_declared_refuses_a_name_another_bundle_holds(home_and_bundle) -> None:
    """The mount refuses a name a neighbour already contributes with name_taken, so a
    check that only asked the kernel map would go green on a bundle that cannot mount."""
    home, directory = home_and_bundle
    _add_tool(directory, TOOL_FIELDS)
    _install_neighbour(home, "neighbour-bundle", directory)
    verdict = _verdicts(
        _run(home, _case(["capability_declared"], declared=["read"]))
    )["capability_declared"]
    assert verdict.ok is False
    assert TOOL_FIELDS["name"] in verdict.detail, verdict.detail
    assert "neighbour" in verdict.detail, verdict.detail


def test_capability_undeclared_refused_reads_the_contract_that_says_no(home_and_bundle) -> None:
    """The manifest contract is asked, live, whether it refuses the family — and it does."""
    home, directory = home_and_bundle
    _add_tool(directory, {**TOOL_FIELDS, "family": "shell"})
    _write_manifest(directory, {**_manifest(directory), "permissions": {
        "tool_families": ["read"], "data_roots": []
    }})
    entry = directory / "tools"
    entry.mkdir(parents=True, exist_ok=True)
    (entry / "echo.py").write_text("def run(text):\n    return text\n", encoding="utf-8")
    verdict = _verdicts(
        _run(home, _case(["capability_undeclared_refused"], undeclared=["shell"]))
    )["capability_undeclared_refused"]
    assert verdict.ok is True, verdict.detail
    assert "shell" in verdict.detail, verdict.detail


def test_capability_undeclared_refused_fails_closed_on_an_answer_that_says_yes(home_and_bundle) -> None:
    """A family the contract grants is not a refusal, and the check cannot go green on it."""
    home, directory = home_and_bundle
    _add_tool(directory, TOOL_FIELDS)
    verdict = _verdicts(
        _run(home, _case(["capability_undeclared_refused"], undeclared=["read"]))
    )["capability_undeclared_refused"]
    assert verdict.ok is False
    assert "read" in verdict.detail, verdict.detail


def test_staging_empty_passes_where_the_turn_created_nothing(home) -> None:
    """The refusal case's end state is an empty staging folder, read as it is."""
    verdict = _verdicts(_run(home, _case(["staging_empty"])))["staging_empty"]
    assert verdict.ok is True, verdict.detail


def test_staging_empty_reports_what_a_refused_turn_wrote_anyway(home_and_bundle) -> None:
    """A folder that arrived is named, and a folder without a manifest is still a folder."""
    home = home_and_bundle[0]
    (home / "half-written").mkdir()
    verdict = _verdicts(_run(home, _case(["staging_empty"])))["staging_empty"]
    assert verdict.ok is False
    assert BUNDLE in verdict.detail and "half-written" in verdict.detail, verdict.detail


def test_the_code_grant_offers_exactly_the_call_it_buys(home) -> None:
    """GIVEN a turn that holds `code` alone WHEN the offer check reads it
    THEN the one call `code` buys is offered and the four `files` calls are withheld,
    which is the promise creation-04 and creation-24 grade."""
    case = _grant_case(["code"])
    verdict = _verdicts(_run(home, case))["offer_matches_grant"]
    assert verdict.ok is True, verdict.detail
    assert "install_plugin_bundle" in verdict.detail, verdict.detail
    assert "create_plugin_scaffold" in verdict.detail, verdict.detail


def test_the_files_grant_is_offered_the_four_calls_it_buys(home) -> None:
    """`files` buys the authoring calls and not the install, and the offer says so."""
    verdict = _verdicts(_run(home, _grant_case(["files"])))["offer_matches_grant"]
    assert verdict.ok is True, verdict.detail
    assert "create_plugin_scaffold" in verdict.detail, verdict.detail
    assert "install_plugin_bundle" in verdict.detail, verdict.detail


def test_a_call_the_grant_buys_and_the_offer_lost_is_named(home, monkeypatch) -> None:
    """GIVEN the product's offer filter losing a name the guard allows WHEN the check runs
    THEN the verdict is a fail that names the lost call — the defect the probe reports as
    `creator_missing_from_grant`, graded here on the eval case itself."""
    from core.tools import creator_guard

    real = creator_guard.filter_offer

    def lossy(schemas):
        return [entry for entry in real(schemas)
                if entry["function"]["name"] != "install_plugin_bundle"]

    monkeypatch.setattr(creator_guard, "filter_offer", lossy)
    verdict = _verdicts(_run(home, _grant_case(["code"])))["offer_matches_grant"]
    assert verdict.ok is False
    assert "install_plugin_bundle" in verdict.detail, verdict.detail


def test_an_offered_call_the_grant_does_not_buy_is_named(home, monkeypatch) -> None:
    """GIVEN an offer that carries a call the grant never bought WHEN the check runs
    THEN the verdict is a fail: the model would be invited to a call the gate refuses."""
    from core.tools import creator_guard

    monkeypatch.setattr(creator_guard, "filter_offer", lambda schemas: list(schemas))
    verdict = _verdicts(_run(home, _grant_case(["code"])))["offer_matches_grant"]
    assert verdict.ok is False
    assert "create_plugin_scaffold" in verdict.detail, verdict.detail


def test_a_named_call_no_authority_rules_fails_the_case_closed(home, monkeypatch, tmp_path) -> None:
    """GIVEN a home that declares no bundle for the network calls a case names
    WHEN the offer check reads the case THEN the verdict is a fail naming the call: the
    case grades a refusal nothing in this home can perform, so no green row is printed."""
    from core import plugin_manifest

    empty = tmp_path / "declares-nothing"
    empty.mkdir()
    monkeypatch.setenv(plugin_manifest.ENV_BUILTIN_PLUGINS_ROOT, str(empty))
    from core.tools import creator_guard

    creator_guard.invalidate_family_map()

    case = _grant_case(["code", "files"])
    case["tools"] = [*case["tools"], "fetch_url", "web_search"]
    verdict = _verdicts(_run(home, case))["offer_matches_grant"]
    assert verdict.ok is False
    assert "fetch_url" in verdict.detail, verdict.detail
    assert "unlisted" in verdict.detail, verdict.detail


def test_a_declared_bundle_gives_the_network_calls_their_ruling(home, monkeypatch, tmp_path) -> None:
    """GIVEN the shipped web-research bundle declared in the home WHEN the check reads the
    same case THEN the network calls are ruled and withheld from a grant without `network`,
    so a home that declares the bundle grades the case and one that does not says why."""
    from core import plugin_manifest

    declared = tmp_path / "declared"
    declared.mkdir()
    shutil.copytree(ROOT / "plugins" / "web-research", declared / "web-research")
    monkeypatch.setenv(plugin_manifest.ENV_BUILTIN_PLUGINS_ROOT, str(declared))
    from core.tools import creator_guard

    creator_guard.invalidate_family_map()

    case = _grant_case(["code", "files"])
    case["tools"] = [*case["tools"], "fetch_url", "web_search"]
    verdict = _verdicts(_run(home, case))["offer_matches_grant"]
    assert verdict.ok is True, verdict.detail
    assert "fetch_url" in verdict.detail or "network" in verdict.detail, verdict.detail


def test_the_shipped_refusal_cases_grade_the_offer_they_were_given() -> None:
    """GIVEN the three refusal cases WHEN their checks are read
    THEN each asks the offer check: the call it watches was withheld, not merely unused."""
    from evals.creation_eval import load_cases

    refused = [case for case in load_cases() if case["expect"]["kind"] == "tool_refused"]
    assert refused, "the set carries no refusal case"
    for case in refused:
        assert "offer_matches_grant" in case["checks"], case["id"]


def test_a_bundle_check_without_a_subject_reports_the_count_it_found(home) -> None:
    """Zero staged bundles cannot answer a bundle check, and the verdict says zero."""
    verdicts, not_run = _run(home, _case(["manifest_valid", "surface_files"]))
    by_name = _verdicts((verdicts, not_run))
    assert [by_name[name].ok for name in ("manifest_valid", "surface_files")] == [False, False]
    assert "0" in by_name["manifest_valid"].detail, by_name["manifest_valid"].detail


def test_the_two_check_groups_are_every_check_and_never_overlap() -> None:
    """The partition the runner publishes rates from: offline here, browser in #51c."""
    from evals.creation_checks import BROWSER_CHECKS, OFFLINE_CHECKS
    from evals.creation_eval import CHECKS

    assert set(OFFLINE_CHECKS) | set(BROWSER_CHECKS) == set(CHECKS)
    assert not set(OFFLINE_CHECKS) & set(BROWSER_CHECKS)
    assert {"manifest_valid", "surface_files", "capability_declared",
            "capability_undeclared_refused", "staging_empty", "state_bridge_used",
            "offer_matches_grant"} \
        == set(OFFLINE_CHECKS)


def test_a_browser_check_reports_no_verdict_offline(home_and_bundle) -> None:
    """`mounts` is not run here, so it must arrive as not-run rather than as a pass."""
    verdicts, not_run = _run(home_and_bundle[0], _case(["manifest_valid", "mounts"]))
    names = {verdict.check for verdict in verdicts}
    assert names == {"manifest_valid"}
    assert list(not_run) == ["mounts"]


def test_state_bridge_used_reads_the_persistence_a_scaffold_ships_with(home_and_bundle) -> None:
    """A scaffold keeps nothing anywhere, so the check says which call it looked for."""
    verdict = _verdicts(_run(home_and_bundle[0], _case(["state_bridge_used"])))
    assert verdict["state_bridge_used"].ok is False
    assert "ephe.storage" in verdict["state_bridge_used"].detail


def test_state_bridge_used_passes_on_the_sdks_own_call(home_and_bundle) -> None:
    """`ephe.storage` is the product path, and a bundle that asks it is graded a pass."""
    home, directory = home_and_bundle
    _write_source(directory / "ui" / "app.js", 'ephe.storage.set("entries", []);\n')
    verdict = _verdicts(_run(home, _case(["state_bridge_used"])))["state_bridge_used"]
    assert verdict.ok is True, verdict.detail
    assert "app.js" in verdict.detail, verdict.detail


def test_state_bridge_used_names_the_page_storage_a_bundle_wrote(home_and_bundle) -> None:
    """A widget that keeps its entries in the page is off the graded path.

    The mount's shim keeps that write alive, so the verdict may not read as "the state
    is lost"; it has to name the path the definition of done asks for.
    """
    home, directory = home_and_bundle
    _write_source(directory / "ui" / "app.js", 'localStorage.setItem("entries", "[]");\n')
    verdict = _verdicts(_run(home, _case(["state_bridge_used"])))["state_bridge_used"]
    assert verdict.ok is False
    assert "localStorage" in verdict.detail, verdict.detail
    assert "shim" in verdict.detail, verdict.detail
    assert "grades ephe.storage" in verdict.detail, verdict.detail


def test_state_bridge_used_passes_when_the_bridge_is_there_beside_page_calls(home_and_bundle) -> None:
    """The row asks for the documented path."""
    home, directory = home_and_bundle
    _write_source(
        directory / "ui" / "app.js",
        'ephe.storage.set("entries", []);\nlocalStorage.setItem("legacy", "1");\n',
    )
    verdict = _verdicts(_run(home, _case(["state_bridge_used"])))["state_bridge_used"]
    assert verdict.ok is True, verdict.detail


def test_a_bundle_that_loads_the_sdk_and_calls_it_satisfies_both_rows(home_and_bundle) -> None:
    """The definition of done has to be satisfiable on one bundle.

    `ephe.js` is the one script a `ephe.storage` call needs, and the mount serves it
    under a reserved name (`scripts/plugin_dod_surface.py` knows that name), so the
    surface scan and the state row cannot contradict each other on the same bundle.
    """
    home, directory = home_and_bundle
    entry = directory / "ui" / "index.html"
    entry.write_text(
        entry.read_text(encoding="utf-8").replace(
            '<script type="module" src="app.js"></script>',
            '<script src="ephe.js"></script>\n<script type="module" src="app.js"></script>',
        ),
        encoding="utf-8",
    )
    _write_source(directory / "ui" / "app.js", 'ephe.storage.set("entries", []);\n')
    verdicts = _verdicts(_run(home, _case(["surface_files", "state_bridge_used"])))
    for name in ("surface_files", "state_bridge_used"):
        assert verdicts[name].ok is True, verdicts[name].detail


def test_state_bridge_used_does_not_read_a_vendored_library(home_and_bundle) -> None:
    """Vendor bytes are pinned and uneditable, so a call inside one grants nothing."""
    home, directory = home_and_bundle
    _write_source(directory / "vendor" / "legacy.js", 'ephe.storage.set("a", "b");\n')
    verdict = _verdicts(_run(home, _case(["state_bridge_used"])))["state_bridge_used"]
    assert verdict.ok is False, verdict.detail
    assert "legacy.js" not in verdict.detail, verdict.detail


def _install_neighbour(home: Path, name: str, directory: Path) -> Path:
    """A second bundle in the config's plugin folder, holding the staged bundle's names.

    The staging folder holds a turn's output; the activation scan reads the plugin
    folder, so a neighbour is how the test puts a name in the platform's mouth. The
    tree is copied and renamed, because the loader decides what an installed bundle is.
    """
    installed = home.parent.parent / "plugins" / name
    shutil.copytree(directory, installed)
    _write_manifest(installed, {**_manifest(installed), "name": name})
    return installed


def _write_source(path: Path, text: str) -> Path:
    """One source file inside the staged bundle, with its folders."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _add_tool(directory: Path, tool: dict) -> None:
    """One contributed tool in the staged manifest, with the family permissions to match."""
    manifest = _manifest(directory)
    components = manifest.setdefault("components", {})
    components["tools"] = [tool]
    families = set(manifest.setdefault("permissions", {}).setdefault("tool_families", []))
    families.add(tool["family"])
    manifest["permissions"]["tool_families"] = sorted(families)
    _write_manifest(directory, manifest)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return _home(tmp_path, monkeypatch)


@pytest.fixture
def home_and_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    root = _home(tmp_path, monkeypatch)
    return root, _scaffold(root)
