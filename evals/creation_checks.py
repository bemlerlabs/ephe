"""Ephe · Creator — the offline end-state checks of the creation eval set (task #51b).
evals/creation_checks.py

A case in `evals/creation/cases.jsonl` asks for a bundle. This module reads the bundle
back and answers the end-state checks that need no browser and no engine, each with one
verdict naming the layer that answered:

  * `manifest_valid` — `core.plugin_manifest.load_manifest`, the same read the scanner
    and the mount make. Its error text is carried verbatim, so the author hears the
    contract's own words.
  * `surface_files` — the definition-of-done surface scan
    (`scripts/plugin_dod_surface.surface_problems`), which is the only code that asks
    whether every file the entry document names arrives from inside the bundle.
  * `capability_declared` — `core.plugin_tools_contract.descriptors_for` plus the two
    guards the mount itself answers with: `reserved_namespace` for the kernel dispatch
    map and the live MCP catalog, and the activation scan's `owners` for a name another
    bundle already contributes, which is the `name_taken` a mount would meet. A family
    with no tool carrying it is a permission the bundle asked for and nothing served, so
    the check says so.
  * `capability_undeclared_refused` — `core.plugin_tools_contract.validate_tools` asked
    live about the family the case says the bundle must not hold. A contract that
    accepts it is reported as a failure of this check: the case graded a refusal the
    platform never performs.
  * `staging_empty` — the refusal case's end state, which is an empty staging folder.
  * `state_bridge_used` — the bundle's own source, read for the state-path call. A file
    outside `vendor/` that writes through the SDK's `storage` methods answers yes; one
    that writes its own page storage instead answers no, naming what it writes.

The three browser checks in `evals.creation_eval.CHECKS` are not run here. They come back
as `not_run` names, because a rate that counted a green row nobody measured would be the
same defect this set exists to prevent.
"""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evals.creation_eval import CHECKS, DENIAL_CHECK

ROOT = Path(__file__).resolve().parents[1]

#: The end states this module can decide from bytes on disk.
OFFLINE_CHECKS: tuple[str, ...] = (
    "manifest_valid",
    "surface_files",
    "capability_declared",
    "capability_undeclared_refused",
    "staging_empty",
    "state_bridge_used",
)

#: The end states that need a document in an engine: task #51c builds these.
BROWSER_CHECKS: tuple[str, ...] = tuple(
    name for name in CHECKS if name not in OFFLINE_CHECKS
)

#: The manifest file a staged folder has to carry to be a bundle.
MANIFEST_FILENAME = "ephe-plugin.json"

#: How many staged names a detail line lists before it shortens to a count.
LISTED_NAMES = 3

#: The page-facing form of the product state path: `sdk/ephe.js` answers `storage.get`
#: and `storage.set` on the `ephe.sdk` channel, and `app/src/lib/pluginClientHost.ts`
#: routes them to the bundle's own state roots.
STATE_BRIDGE_CALLS: tuple[str, ...] = ("ephe.storage.get", "ephe.storage.set")

#: What a bundle can persist through that dies with its mount.
PAGE_STORAGE_CALLS: tuple[str, ...] = (
    "localStorage", "sessionStorage", "indexedDB", "caches.open",
)

#: The suffixes a bundle's runnable source is written in.
SOURCE_SUFFIXES: frozenset[str] = frozenset({".js", ".mjs", ".cjs", ".html", ".htm"})


@dataclass(frozen=True)
class Verdict:
    """One check, one answer, and the sentence that shows the reader what it asked."""

    check: str
    ok: bool
    detail: str


def staged_names(root: Path | str) -> list[str]:
    """Everything the turn left in the staging folder, files and bundles alike."""
    directory = Path(root)
    if not directory.is_dir():
        return []
    return sorted(child.name for child in directory.iterdir())


def staged_bundles(root: Path | str) -> list[Path]:
    """The staged folders that carry a manifest, in name order."""
    directory = Path(root)
    if not directory.is_dir():
        return []
    return sorted(
        (child for child in directory.iterdir()
         if child.is_dir() and (child / MANIFEST_FILENAME).is_file()),
        key=lambda path: path.name,
    )


def run_offline_checks(
    case: dict, root: Path | str
) -> tuple[list[Verdict], list[str]]:
    """Grade the offline half of one case, and say which half was left for the browser.

    Fail-closed on both ends: a bundle check with no single staged bundle to read gets a
    verdict of its own naming the count, and a browser check gets no verdict at all.
    """
    root_dir = Path(root)
    verdicts: list[Verdict] = []
    not_run: list[str] = []
    for name in case.get("checks", []):
        if name == DENIAL_CHECK:
            verdicts.append(_staging_empty(root_dir))
        elif name in OFFLINE_CHECKS:
            verdicts.append(_bundle_check(name, case, root_dir))
        else:
            not_run.append(name)
    return verdicts, not_run


def _bundle_check(name: str, case: dict, root: Path) -> Verdict:
    """Resolve the one staged bundle a case is about, then read that check against it."""
    bundles = staged_bundles(root)
    if not bundles:
        return Verdict(name, False, _no_subject_detail(root))
    if len(bundles) > 1:
        named = ", ".join(path.name for path in bundles[:LISTED_NAMES])
        return Verdict(
            name, False,
            f"{len(bundles)} staged bundles carry a manifest ({named}); "
            "a turn has to leave one bundle for its end state to be attributable",
        )
    directory = bundles[0]
    if name == "manifest_valid":
        return _manifest_valid(directory)
    if name == "surface_files":
        return _surface_files(directory)
    if name == "state_bridge_used":
        return _state_bridge_used(directory)
    return _capability_check(name, case, directory)


def _no_subject_detail(root: Path) -> str:
    left = staged_names(root)
    if not left:
        return "0 staged bundles carry a manifest - the staging folder is empty"
    named = ", ".join(left[:LISTED_NAMES])
    return (
        f"0 staged bundles carry a manifest; {len(left)} name(s) are staged "
        f"({named}) with no {MANIFEST_FILENAME} in them"
    )


def _load(directory: Path) -> tuple[dict | None, str]:
    """The loader's answer as `(manifest, error)`, with an unreadable folder folded in."""
    from core import plugin_manifest

    try:
        manifest, error = plugin_manifest.load_manifest(directory)
    except OSError as exc:
        return None, f"the bundle folder cannot be read ({exc.__class__.__name__})"
    if error or not isinstance(manifest, dict):
        return None, str(error or "the manifest is unreadable")
    return manifest, ""


def _manifest_valid(directory: Path) -> Verdict:
    from core import plugin_manifest

    manifest, error = _load(directory)
    if error:
        return Verdict("manifest_valid", False, f"core.plugin_manifest.load_manifest: {error}")
    version = manifest.get("manifest_version") if manifest else None
    name = manifest.get("name") if manifest else directory.name
    return Verdict(
        "manifest_valid", True,
        f"core.plugin_manifest.load_manifest reads {name} as manifest "
        f"v{version} ({plugin_manifest.MANIFEST_VERSION_V2} is the declarative tier)",
    )


def _surface_files(directory: Path) -> Verdict:
    problems = _surface_module().surface_problems(directory)
    if problems:
        return Verdict(
            "surface_files", False,
            "scripts/plugin_dod_surface.surface_problems: " + "; ".join(problems),
        )
    return Verdict(
        "surface_files", True,
        "scripts/plugin_dod_surface.surface_problems: the entry document and every file "
        "it names arrive from inside the bundle",
    )


def _state_bridge_used(directory: Path) -> Verdict:
    """Whether the bundle persists through the product state path.

    The read is of the bytes the mount runs, with the vendored libraries left out:
    those are pinned hashes the turn did not write and cannot edit, so a page-storage
    call inside one says nothing about where this widget's entries live.
    """
    sources = _bundle_sources(directory)
    if not sources:
        return Verdict(
            "state_bridge_used", False,
            f"no {', '.join(sorted(SOURCE_SUFFIXES))} file ships outside vendor/, "
            "so nothing here could call the state path",
        )
    bridge = {call for _name, text in sources for call in STATE_BRIDGE_CALLS if call in text}
    if bridge:
        holders = ", ".join(sorted(name for name, text in sources
                                   if any(call in text for call in bridge)))
        return Verdict(
            "state_bridge_used", True,
            f"{holders} call {', '.join(sorted(bridge))} on {len(sources)} source file(s) read",
        )
    page = {call for _name, text in sources for call in PAGE_STORAGE_CALLS if call in text}
    where = f" - it writes {', '.join(sorted(page))} on its own page" if page else ""
    return Verdict(
        "state_bridge_used", False,
        f"none of {', '.join(STATE_BRIDGE_CALLS)} appears in {len(sources)} source file(s){where}",
    )


def _bundle_sources(directory: Path) -> list[tuple[str, str]]:
    """`(relative name, text)` for the bundle's own runnable files."""
    from core.plugin_libraries import VENDOR_DIRNAME

    found: list[tuple[str, str]] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        relative = path.relative_to(directory)
        if VENDOR_DIRNAME in relative.parts:
            continue
        try:
            found.append((relative.as_posix(), path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    return found


def _capability_check(name: str, case: dict, directory: Path) -> Verdict:
    """Grade one capability half of a case, each on the layer that owns its answer.

    `capability_declared` is a promise about a bundle the platform accepts, so it starts
    behind the loader. `capability_undeclared_refused` is a promise about a declaration
    the platform must reject, so it reads the manifest as written and asks the contract
    directly — a refusal there is the pass, and putting it behind the loader would make
    the check report its own subject as unreadable.
    """
    capabilities = case.get("capabilities") or {}
    if name == "capability_declared":
        manifest, error = _load(directory)
        if error:
            return Verdict(
                name, False, f"not graded, the loader refused the bundle: {error}"
            )
        return _capability_declared(manifest, capabilities)
    manifest, error = _raw_manifest(directory)
    if error:
        return Verdict(name, False, error)
    return _capability_undeclared_refused(manifest, directory, capabilities)


def _raw_manifest(directory: Path) -> tuple[dict | None, str]:
    """The staged manifest as the bundle wrote it, with no validation in the way."""
    try:
        loaded = json.loads((directory / MANIFEST_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"the staged {MANIFEST_FILENAME} cannot be read ({exc.__class__.__name__})"
    if not isinstance(loaded, dict):
        return None, f"the staged {MANIFEST_FILENAME} holds no object"
    return loaded, ""


def _capability_declared(manifest: dict, capabilities: dict) -> Verdict:
    from core.plugin_tools_contract import (
        declared_families,
        descriptors_for,
        reserved_namespace,
    )

    declared = [str(family) for family in capabilities.get("declared", [])]
    families = set(declared_families(manifest))
    claims = [descriptor for descriptor in descriptors_for(manifest)]
    owners = _name_owners(str(manifest.get("name") or ""))
    problems: list[str] = []
    served: list[str] = []
    for family in declared:
        if family not in families:
            problems.append(
                f"the case grades {family!r} as declared, permissions.tool_families does not hold it"
            )
        carrying = [item for item in claims if item.tool_family == family]
        if not carrying:
            problems.append(
                f"{family!r} is declared and no tool in this bundle carries it - nothing is served"
            )
        for descriptor in carrying:
            holder = reserved_namespace(descriptor.name)
            if holder:
                problems.append(
                    f"{descriptor.name!r} is held by the {holder} name space, so this bundle cannot serve it"
                )
            elif descriptor.name in owners:
                problems.append(
                    f"{descriptor.name!r} is contributed by bundle {owners[descriptor.name]!r}, "
                    "so the mount would refuse this one"
                )
            else:
                served.append(f"{descriptor.name} ({family})")
    if problems:
        return Verdict("capability_declared", False, "; ".join(problems))
    return Verdict(
        "capability_declared", True,
        f"core.plugin_tools_contract.descriptors_for serves {', '.join(served)} under the "
        "names the manifest spells",
    )


def _capability_undeclared_refused(
    manifest: dict, directory: Path, capabilities: dict
) -> Verdict:
    from core.plugin_tools_contract import (
        declared_families,
        tool_claims,
        validate_tools,
    )

    undeclared = [str(family) for family in capabilities.get("undeclared", [])]
    families = set(declared_families(manifest))
    claims = [claim for claim in tool_claims(manifest) if claim.contributed]
    problems: list[str] = []
    notes: list[str] = []
    for family in undeclared:
        if family in families:
            problems.append(
                f"the bundle declares {family!r} in permissions.tool_families; the case names it undeclared"
            )
            continue
        carrying = [claim for claim in claims if claim.family == family]
        error = validate_tools(manifest, directory)
        if not carrying:
            problems.append(
                f"no tool declares {family!r}, so the contract had nothing to refuse"
            )
        elif error is None:
            problems.append(
                f"core.plugin_tools_contract.validate_tools accepted a bundle holding "
                f"{family!r} without declaring it - nothing refused it"
            )
        elif family not in error:
            problems.append(f"refused, but for another reason: {error}")
        else:
            notes.append(f"{family!r}: {error}")
    if problems:
        return Verdict("capability_undeclared_refused", False, "; ".join(problems))
    return Verdict(
        "capability_undeclared_refused", True,
        "core.plugin_tools_contract.validate_tools refuses the undeclared family - "
        + "; ".join(notes),
    )


def _name_owners(own: str) -> dict[str, str]:
    """Which bundle already contributes each name, from the scan the mount runs.

    The registry answers ``name_taken`` for a name another bundle holds, and the scan
    is the same read from the tree: it covers the shipped bundles without waiting for
    a process to publish them. The bundle under test is left out, because it is not
    its own neighbour.
    """
    from core.plugin_registry import scan_tool_activations

    try:
        owners = dict(scan_tool_activations(None).owners)
    except Exception:  # noqa: BLE001 - an unreadable scan holds nothing
        return {}
    owners.pop(own, None)
    return owners


def _staging_empty(root: Path) -> Verdict:
    left = staged_names(root)
    if not left:
        return Verdict("staging_empty", True, "the staging folder holds nothing")
    named = ", ".join(left[:LISTED_NAMES])
    extra = "" if len(left) <= LISTED_NAMES else f", and {len(left) - LISTED_NAMES} more"
    return Verdict(
        "staging_empty", False,
        f"{len(left)} name(s) are staged where a refused turn should have written nothing: "
        f"{named}{extra}",
    )


def _surface_module() -> Any:
    """The definition-of-done surface scan, loaded from `scripts/` by path.

    `scripts/` is not an importable package, and the rule about a surface's referenced
    files lives in exactly one place, so the file is read rather than restated.
    """
    path = ROOT / "scripts" / "plugin_dod_surface.py"
    spec = importlib.util.spec_from_file_location("plugin_dod_surface", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"{path} cannot be loaded as a module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verdict_rows(verdicts: list[Verdict]) -> list[dict[str, Any]]:
    """The receipt shape: one row per verdict, so #51d can print a rate per category."""
    return [
        {"check": verdict.check, "ok": verdict.ok, "detail": verdict.detail}
        for verdict in verdicts
    ]


__all__ = [
    "BROWSER_CHECKS",
    "OFFLINE_CHECKS",
    "Verdict",
    "run_offline_checks",
    "staged_bundles",
    "staged_names",
    "verdict_rows",
]
