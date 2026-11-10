"""Ephe — the offline library runtime a plugin surface loads from its own bundle.

core/plugin_libraries.py

A surface is a document someone generated. Asked for a 3D scene, that document names
a renderer, and the shortest path a generator takes is a `<script>` at a public CDN.
Two things are wrong with that URL in this product: the fetch is a network permission
the manifest never asked for, and it is a privacy event on every page load; and the
policy this mount is served under refuses it anyway —
`server/plugin_surface_policy.py` keeps `script-src 'self'` closed for every
capability name a manifest can spell, which
`tests/test_plugin_libraries.py::test_no_capability_declaration_names_a_remote_source`
pins for the whole vocabulary. This module is the working alternative a generator can
be pointed at: the plugin ships the library inside its own bundle and the document
loads it by relative path through the mount the surface route already serves.

The contract, in one paragraph. A plugin that ships code libraries declares each one
in `ephe-libraries.json`, beside the manifest: a name, a version string for the human
reading a store page, a path inside the bundle, how the document loads it, and the
SHA-256 of the bytes it means to ship. Validation re-reads the file and compares
(`core/plugin_manifest._validate` calls `validate_libraries`). A mismatch, a declared
file that does not ship, a file under the vendor root that nothing declared, or a byte
past a stated cap quarantines the whole plugin the way every other manifest violation
does, and because the surface route reads the manifest again before it touches a byte
of the bundle (`server/routes/plugin_ui.py::_surface_behind_the_read`), a library
edited on disk after install stops being served on the very next request.

What the hash is, and what it is not. It pins which bytes shipped. A publisher who
declares the hash of a library nobody likes passes this check — the check answers
"did the bytes change since they were reviewed" (an editor, a bad pack step, a swapped
file), and it holds up on its own only beside a review of the declared bytes. The
directory hash the lockfile already carries (`core/plugin_manifest.dir_sha256`) covers
the same bytes for drift between catalog and disk, so the two checks answer different
questions and neither claims safety.

Where the numbers come from, all measured on 2026-11-05 for this contract. The
per-file cap is 8 MiB, which is `server/plugin_surface.MAX_SURFACE_ASSET_BYTES`
restated here and pinned equal to it by a test: a library past that ceiling cannot be
delivered by this route at all, so declaring one would be a promise the serve layer
breaks. The largest minified single-file 3D-engine bundle measured against that number
is 6,312,709 bytes (6.02 MiB), and the two other engine builds sampled are 1,183,145
and 687,458 bytes; the unminified sibling of the largest measures 44,021,669 bytes and
is refused, which is what the cap is for. The per-plugin total is 24 MiB, three files
at the per-file ceiling: hashing 25,165,824 bytes measures 7.44 ms at the 3.38 GB/s
this machine hashes at, and a realistic declared set of 973,587 bytes (a renderer plus
its mesh-decoder wasm) measures 0.88 ms for a whole manifest read.

Where enforcement lives. Validation carries the whole contract, and the surface route
re-reads the manifest before it touches a byte of the bundle, so a violation shows up
as a refusal on the next request. The serve layer holds a second copy of exactly one
rule, the `application/wasm` capability check in
`server/plugin_surface.ASSET_REQUIRED_CAPABILITIES`, because the request that asks for
a wasm file is the place that knows whether the mount may compile it: a declaration
never says which file the page will fetch. No size cap is re-checked there — the
per-file cap equals the route's own asset ceiling, so a file that passed validation is
deliverable by definition, and a second number would be a second lie waiting to
disagree.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath

from core.plugin_manifest import _SLUG_RE, _under
from core.plugin_ui_capabilities import ui_descriptor

#: The declaration file, beside the manifest. A sidecar keeps this contract out of
#: `ephe-plugin.json`, whose field set is closed (an unknown top-level field
#: quarantines a plugin), and `ephe-plugin.sig.json` is the precedent for a second
#: signed-shape file in a plugin root.
LIBRARIES_FILENAME = "ephe-libraries.json"

#: The one schema this reader understands; anything else is refused unread.
LIBRARIES_SCHEMA = 1

#: The directory a bundle's libraries live in, by convention: `vendor/` beside the
#: entry document, or at the plugin root for a surface whose entry sits there.
VENDOR_DIRNAME = "vendor"

#: One declared file. Equal to the surface route's own asset ceiling on purpose.
MAX_LIBRARY_FILE_BYTES = 8 * 1024 * 1024

#: One plugin. Three files at the ceiling above, which is more renderer weight than a
#: surface loads; the measured cost of re-verifying it is in the module header.
MAX_LIBRARY_TOTAL_BYTES = 3 * MAX_LIBRARY_FILE_BYTES

#: A version tag is display text. 64 is the width of the `sha256` slot beside it, so
#: one row of the table holds both strings.
MAX_LIBRARY_VERSION_CHARS = 64

#: Bytes read per hash step, so an 8 MiB library never sits in memory twice.
HASH_CHUNK_BYTES = 1 * 1024 * 1024

#: The fields one entry may name. A typo in a hash field would otherwise read as an
#: entry with no hash, so unknown fields go the way of unknown manifest fields.
LIBRARY_FIELDS = frozenset({"name", "version", "path", "sha256", "kind"})

#: How the document loads the file. `script` is a classic `<script src>`, `module` a
#: `<script type="module">`, `wasm` a binary the page instantiates itself.
LIBRARY_KINDS = frozenset({"script", "module", "wasm"})

#: The kinds each servable suffix may claim, and the only suffixes a library may be.
#: An image, a font or a stylesheet is an asset the asset route already serves, so it
#: has no place in a declaration that exists to pin executed code. A test pins these
#: suffixes against the route's served-type table.
LIBRARY_KIND_SUFFIXES = {
    ".js": frozenset({"script", "module"}),
    ".mjs": frozenset({"module"}),
    ".wasm": frozenset({"wasm"}),
}

#: A capability a name needs before the mount may load the file. `wasm` compiles bytes
#: into code, and only the widened `script-src` of the surface policy lets that run.
LIBRARY_REQUIRED_CAPABILITIES = {"wasm": "wasm"}

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def _mib(value: int) -> str:
    """A byte count as the unit the cap is stated in, read off the constant."""
    return f"{value // (1024 * 1024)} MiB"


def _relative(path: str) -> str:
    """A declared path as one relative posix path, `./` noise removed."""
    parts = [part for part in str(path).replace("\\", "/").split("/") if part not in ("", ".")]
    return "/".join(parts)


def _shape_error(entry: object, position: int) -> str | None:
    """The structural check of one declaration row, before any file is opened."""
    if not isinstance(entry, dict):
        return f"libraries[{position}]: object with name, version, path, sha256, kind expected"
    unknown = sorted(set(entry) - LIBRARY_FIELDS)
    if unknown:
        return f"libraries[{position}]: unknown field(s): {', '.join(unknown)}"
    missing = sorted(LIBRARY_FIELDS - set(entry))
    if missing:
        return f"libraries[{position}]: missing field(s): {', '.join(missing)}"
    name = entry["name"]
    if not isinstance(name, str) or not _SLUG_RE.match(name):
        return f"libraries[{position}]: name must be a lowercase slug (a-z0-9-)"
    version = entry["version"]
    if (
        not isinstance(version, str)
        or not version.strip()
        or len(version) > MAX_LIBRARY_VERSION_CHARS
    ):
        return (
            f"libraries[{position}]: version must be a non-empty string of at most "
            f"{MAX_LIBRARY_VERSION_CHARS} characters"
        )
    if not isinstance(entry["path"], str) or not _relative(entry["path"]):
        return f"libraries[{position}]: path must be a non-empty path inside the plugin"
    digest = entry["sha256"]
    if not isinstance(digest, str) or not _HEX64_RE.match(digest):
        return f"libraries[{position}]: sha256 must be 64 lowercase hex characters ({name})"
    kind = entry["kind"]
    if kind not in LIBRARY_KINDS:
        return (
            f"libraries[{position}]: kind {kind!r} is not one of "
            f"{sorted(LIBRARY_KINDS)} ({name})"
        )
    return None


def _read_declaration(plugin_dir: Path) -> tuple[list[dict], str | None]:
    """`(entries, None)` or `([], None)` when nothing is declared, else an error."""
    declared_file = _under(plugin_dir, LIBRARIES_FILENAME)
    if declared_file is None or not declared_file.is_file():
        return [], None
    try:
        raw = json.loads(declared_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], f"{LIBRARIES_FILENAME}: unreadable JSON"
    if not isinstance(raw, dict):
        return [], f"{LIBRARIES_FILENAME}: object with schema and libraries expected"
    unknown = sorted(set(raw) - {"schema", "libraries"})
    if unknown:
        return [], f"{LIBRARIES_FILENAME}: unknown top-level field(s): {', '.join(unknown)}"
    if raw.get("schema") != LIBRARIES_SCHEMA:
        return [], (
            f"{LIBRARIES_FILENAME}: schema must be {LIBRARIES_SCHEMA} "
            f"(got {raw.get('schema')!r})"
        )
    entries = raw.get("libraries")
    if not isinstance(entries, list):
        return [], f"{LIBRARIES_FILENAME}.libraries: list of library entries expected"
    if not entries:
        return [], (
            f"{LIBRARIES_FILENAME}.libraries: names nothing; delete the file when the "
            "plugin ships no library"
        )
    checked: list[dict] = []
    for position, entry in enumerate(entries):
        error = _shape_error(entry, position)
        if error:
            return [], error
        checked.append(entry)  # type: ignore[arg-type]
    return checked, None


def _entry_dir(descriptor: dict) -> PurePosixPath:
    """The directory the mount resolves its relative URLs against."""
    return PurePosixPath(descriptor["entry"]).parent


def _in_entry_tree(entry_dir: PurePosixPath, relative: str) -> bool:
    """Whether a declared path sits where the document can reach it.

    A browser resolves `vendor/x.js` against the directory of the document URL, and
    `server/plugin_surface._request_parts` refuses a `..` segment, so a surface whose
    entry is `ui/index.html` has no way to load a file that lives above `ui/`. A
    declaration the mount cannot honour is refused at validation, where the reason can
    still name the field.
    """
    parts = PurePosixPath(relative).parts
    if str(entry_dir) == ".":
        return True
    return parts[: len(entry_dir.parts)] == entry_dir.parts


def _vendor_dir(plugin_dir: Path, entry_dir: PurePosixPath) -> Path | None:
    """The declared library root of this bundle, or None when the plugin ships none."""
    candidates = [plugin_dir / VENDOR_DIRNAME]
    if str(entry_dir) != ".":
        candidates.insert(0, plugin_dir.joinpath(*entry_dir.parts) / VENDOR_DIRNAME)
    for candidate in candidates:
        held = _under(plugin_dir, *candidate.relative_to(plugin_dir).parts)
        if held is not None and held.is_dir():
            return held
    return None


def _vendor_files(vendor: Path) -> list[Path]:
    """Every file under one vendor root, sorted and deterministic.

    The same walk `dir_sha256` runs, so the two instruments look at one corpus.
    """
    return sorted(p for p in vendor.rglob("*") if p.is_file())


def _file_sha256(target: Path) -> tuple[str, str]:
    """`(hex, "")` for the bytes of one file, read in chunks.

    A file that cannot be opened is a refusal carrying the reason, because a
    declaration that cannot be verified is never a pass.
    """
    digest = hashlib.sha256()
    try:
        with target.open("rb") as handle:
            while chunk := handle.read(HASH_CHUNK_BYTES):
                digest.update(chunk)
    except OSError:
        return "", "the declared file is not readable"
    return digest.hexdigest(), ""


def validate_libraries(manifest: dict, plugin_dir: Path) -> str | None:
    """The contract check for a bundle's vendored code: an error string, or None.

    Called from `core/plugin_manifest._validate` for every manifest, so a plugin with
    no declaration pays two `is_file`/`is_dir` stats and nothing else. Everything here
    answers one of four questions: is the declaration a declaration of this contract,
    does the path it names stay inside the bundle and under the entry document, does
    the surface have the capability the file type needs, and do the bytes on disk match
    the bytes that were promised.
    """
    entries, error = _read_declaration(plugin_dir)
    if error:
        return error
    descriptor = ui_descriptor(manifest)
    vendor = _vendor_dir(plugin_dir, _entry_dir(descriptor) if descriptor else PurePosixPath("."))
    if not entries:
        if vendor is None:
            return None
        return (
            f"libraries: {os.path.relpath(vendor, os.path.realpath(plugin_dir))!r} ships "
            f"files with no {LIBRARIES_FILENAME}; every vendored file has to be declared"
        )
    if not descriptor:
        return (
            f"{LIBRARIES_FILENAME}: a declared library needs a components.ui surface, "
            "and this manifest declares none"
        )
    entry_dir = _entry_dir(descriptor)
    capabilities = set(descriptor.get("capabilities") or ())
    declared_paths: list[str] = []
    total_bytes = 0
    for position, entry in enumerate(entries):
        name = str(entry["name"])
        raw_path = str(entry["path"])
        if raw_path.startswith("/") or "\\" in raw_path:
            return (
                f"libraries[{position}]: {raw_path!r} must be a relative path inside the "
                "plugin directory, the way the surface route reads a URL remainder"
            )
        relative = _relative(raw_path)
        if ".." in PurePosixPath(relative).parts:
            return f"libraries[{position}]: {relative!r} must stay inside the plugin directory"
        if relative in declared_paths:
            return f"libraries[{position}]: duplicate declaration of {relative!r}"
        suffix = PurePosixPath(relative).suffix.lower()
        allowed = LIBRARY_KIND_SUFFIXES.get(suffix)
        if allowed is None:
            return (
                f"libraries[{position}]: {relative!r} is a {suffix or 'suffixless'} file; "
                f"a vendored library is one of {sorted(LIBRARY_KIND_SUFFIXES)}"
            )
        if entry["kind"] not in allowed:
            return (
                f"libraries[{position}]: kind {entry['kind']!r} cannot load a {suffix} "
                f"file ({name}); a {suffix} file loads as {sorted(allowed)}"
            )
        needed = LIBRARY_REQUIRED_CAPABILITIES.get(suffix.lstrip("."))
        if needed is not None and needed not in capabilities:
            return (
                f"libraries[{position}]: {name!r} is a {suffix} library and needs "
                f"components.ui.capabilities to declare {needed!r}, because a surface "
                "that may not compile WebAssembly cannot run it"
            )
        if not _in_entry_tree(entry_dir, relative):
            return (
                f"libraries[{position}]: {relative!r} sits above the entry document's "
                f"directory {str(entry_dir)!r}, and a surface loads nothing there"
            )
        ships = _under(plugin_dir, *PurePosixPath(relative).parts)
        if ships is None or not ships.is_file():
            return f"libraries[{position}]: declared library {relative!r} does not ship"
        size = ships.stat().st_size
        if size > MAX_LIBRARY_FILE_BYTES:
            return (
                f"libraries[{position}]: {relative!r} is {size} bytes, past the "
                f"{_mib(MAX_LIBRARY_FILE_BYTES)} per-file limit"
            )
        total_bytes += size
        if total_bytes > MAX_LIBRARY_TOTAL_BYTES:
            return (
                f"libraries: the declared libraries total {total_bytes} bytes, past the "
                f"{_mib(MAX_LIBRARY_TOTAL_BYTES)} per-plugin limit"
            )
        declared_paths.append(relative)
        expected = str(entry["sha256"])
        actual, read_error = _file_sha256(ships)
        if read_error:
            return f"libraries[{position}]: {read_error} ({relative!r})"
        if actual != expected:
            return (
                f"libraries[{position}]: {relative!r} hashes to {actual}, and "
                f"{LIBRARIES_FILENAME} declares {expected} for {name}"
            )
    if vendor is not None:
        declared_real = {os.path.realpath(plugin_dir / one) for one in declared_paths}
        root = os.path.realpath(plugin_dir)
        for shipped in _vendor_files(vendor):
            if os.path.realpath(shipped) not in declared_real:
                # `os.path.relpath` over `Path.relative_to`: the vendor root arrives
                # resolved through `_under`, and on macOS a temp dir's real path and its
                # `/var` alias differ, where `relative_to` raises `ValueError` inside a
                # manifest read that a route then answers with a 500.
                return (
                    f"libraries: {os.path.relpath(shipped, root)!r} sits in "
                    f"{VENDOR_DIRNAME}/ and nothing declares it"
                )
    return None
