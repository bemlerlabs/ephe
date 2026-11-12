"""Ephe — `capabilities.evaluator`: the grader presets one manifest declares.

core/plugin_evaluator_contract.py

A bundle may name the checks its own golden suite grades with. It says so once, in a
version 2 manifest, and the kernel decides every consequence: a declared kind is a name for
one of the kernel's five primitives, resolved when that bundle's suite loads, and it grades
only cases in that suite. A case may combine two or more of those presets with `all_of` or
`none_of`. Nothing here imports plugin code, and nothing here runs at turn time — a preset
is data the grader reads, so it needs no permission family and no lifecycle read.

Why the vocabulary stays the kernel's. `core/plugin_golden.grade` is the instrument that
measures every other claim in this tree, so a bundle may name a check the kernel already
runs, never add one: `artifact`, `tool_use`, `contains`, `not_contains` and `tool_refused`
are the five bases, the arguments come from the manifest, and the five primitive names plus
the two composition names stay reserved. A case names the preset in `expect.kind` and
passes nothing else, so the manifest is the one place the fragment list is written and a
case cannot silently disagree with it. Composition is the case's grammar: `expect.kind` is
`all_of` or `none_of`, and `of` lists the declared preset ids it combines — at least two,
each at most once, never an argument of its own.

Why a preset resolves only inside its own suite. A case that reached another bundle's kind
would make a pass³ number depend on which other bundles are installed, and would create a
contested id where none is needed. `core.plugin_golden.load_golden` reads the declarations
from the manifest beside the suite it loads and from nowhere else.

Fail-closed rules, in one list: `capabilities` in a version 1 manifest, an unknown section,
an `evaluator` that is not an object, an unknown field, `kinds` that is not a list or is
empty or holds more than `MAX_EVALUATOR_KINDS`, a kind that is not an object, an unknown
kind field, an id that is not a lowercase slug or is past `MAX_KIND_ID_CHARS`, an id the
kernel owns (a primitive name or a composition name), a duplicate id, a `from` outside the
five bases, the base's own arguments missing or malformed, a fragment that is blank or
shorter than `MIN_FRAGMENT_CHARS`, and a missing or blank description. Each of them
quarantines the whole bundle.

What stays the kernel's: the five primitives and their definitions, the composition
grammar, the pass³ semantics, the case schema and its id prefix, the anti-slop gate, the
receipt format, and the rule that a number names the engine that produced it. A bundle
still cannot add a primitive or a composition, run code in the grader, grade another
bundle's suite, or write the loader's own fields.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

#: The section list belongs to the manifest contract, where every section module adds its
#: own name; this module carries the body rules for `evaluator` and nothing else.
from core.plugin_manifest_contract import CAPABILITY_SECTIONS as CAPABILITY_SECTIONS

__all__ = [
    "CAPABILITY_SECTIONS",
    "COMPOSITIONS",
    "EVALUATOR_FIELDS",
    "KINDS",
    "KIND_FIELDS",
    "MAX_EVALUATOR_KINDS",
    "MAX_KIND_ID_CHARS",
    "MIN_COMPOSITION_MEMBERS",
    "MIN_FRAGMENT_CHARS",
    "PRESET_BASES",
    "EvaluatorKind",
    "argument_error",
    "evaluator_kinds",
    "preset_matcher",
    "validate_evaluator",
]

#: The kernel's grader vocabulary. `core/plugin_golden` re-exports this tuple, so the
#: grader and the contract read one table instead of two that happen to agree.
KINDS: tuple[str, ...] = ("artifact", "tool_use", "contains", "not_contains", "tool_refused")
#: The composition grammar a case may use in `expect.kind`. It combines declared presets;
#: a manifest names a primitive in `from`.
COMPOSITIONS: tuple[str, ...] = ("all_of", "none_of")
#: The bases a declared preset may name: every primitive the kernel already grades.
PRESET_BASES: tuple[str, ...] = KINDS
#: A suite reads up to this many presets; more per-case checks are written as cases.
MAX_EVALUATOR_KINDS = 8
#: Ceiling on a kind id: it rides in a case, a receipt and a refusal sentence.
MAX_KIND_ID_CHARS = 40
#: Floor on a declared fragment. A preset is reused by every case that names it, so a
#: two-character fragment would clear almost any answer the engine writes.
MIN_FRAGMENT_CHARS = 3
#: Below two members a composition is an alias; that case names the single preset
#: directly.
MIN_COMPOSITION_MEMBERS = 2
EVALUATOR_FIELDS: frozenset[str] = frozenset({"kinds"})
KIND_FIELDS: frozenset[str] = frozenset(
    {"id", "from", "any", "suffix", "reason", "description"}
)
#: The arguments each base reads. A declaration that carries another one of these has
#: misstated its check, so the extra key is refused instead of ignored.
_ARGUMENT_FIELDS: dict[str, frozenset[str]] = {
    "artifact": frozenset({"suffix"}),
    "tool_use": frozenset({"any"}),
    "contains": frozenset({"any"}),
    "not_contains": frozenset({"any"}),
    "tool_refused": frozenset({"any", "reason"}),
}
_ALL_ARGUMENTS = frozenset().union(*_ARGUMENT_FIELDS.values())

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


@dataclass(frozen=True)
class EvaluatorKind:
    """One declared preset, normalized the way the suite loader reads it.

    ``kind_id`` is the name a case writes in `expect.kind`; ``base`` is the kernel
    primitive the grader actually runs, and the argument fields hold what the manifest
    fixed for it. ``plugin_id`` owns the declaration, which is what makes a resolution
    own-suite only.
    """

    kind_id: str
    base: str
    any: tuple[str, ...] = ()
    plugin_id: str = ""
    description: str = ""
    suffix: str = ""
    reason: str = ""


def preset_matcher(preset: EvaluatorKind) -> dict[str, Any]:
    """The kernel matcher a declared preset resolves to, its arguments included.

    The loader copies this onto a case and into a composition, so the argument mapping
    exists once, next to the rule that validated it.
    """
    if preset.base == "artifact":
        return {"kind": "artifact", "suffix": preset.suffix}
    matcher: dict[str, Any] = {"kind": preset.base, "any": list(preset.any)}
    if preset.base == "tool_refused" and preset.reason:
        matcher["reason"] = preset.reason
    return matcher


def _evaluator_section(manifest: dict) -> dict | None:
    capabilities = manifest.get("capabilities")
    if not isinstance(capabilities, dict):
        return None
    section = capabilities.get("evaluator")
    return section if isinstance(section, dict) else None


def _fragments_error(any_list: Any, *, kind: str, min_fragment: int) -> str | None:
    """The `any` rule one primitive and one declared preset share.

    A missing list, a non-string member, a blank fragment and a fragment below the floor
    are the same refusal in both places; only the floor differs, and the caller states it.
    """
    if (
        not isinstance(any_list, list)
        or not any_list
        or not all(isinstance(fragment, str) for fragment in any_list)
    ):
        return f"{kind} needs any: [strings]"
    for fragment in any_list:
        if not fragment.strip():
            return f"{kind} needs a non-empty fragment in any"
        if len(fragment.strip()) < min_fragment:
            return (
                f"{kind} fragment {fragment!r} is shorter than "
                f"{min_fragment} characters"
            )
    return None


def argument_error(
    kind: str, arguments: Mapping[str, Any], *, min_fragment: int = 1
) -> str | None:
    """Why a matcher's arguments do not satisfy its primitive, or None when they do.

    The answer is the sentence's detail without a subject, so a case reads
    `<plugin>: <case id> <detail>` and a declaration
    `capabilities.evaluator.kinds[0]: <detail>`; each caller owns its own prefix.
    ``min_fragment`` is the floor a fragment has to clear: a case writes its fragment
    beside its own input, so the grader refuses only the blank one; a declared preset is
    reused by every case that names it and clears `MIN_FRAGMENT_CHARS`.
    """
    used = _ARGUMENT_FIELDS.get(kind)
    if used is None:
        return f"unknown kind {kind!r}"
    extra = sorted((set(arguments) & _ALL_ARGUMENTS) - used)
    if extra:
        return (
            f"{kind} does not read {', '.join(extra)}; "
            f"its arguments are {', '.join(sorted(used))}"
        )
    if kind == "artifact":
        suffix = arguments.get("suffix")
        if not isinstance(suffix, str) or not suffix.startswith("."):
            return "artifact needs a suffix like '.pdf'"
        return None
    if kind in {"tool_use", "contains", "not_contains"}:
        return _fragments_error(
            arguments.get("any"), kind=kind, min_fragment=min_fragment
        )
    if kind == "tool_refused":
        error = _fragments_error(
            arguments.get("any"), kind=kind, min_fragment=min_fragment
        )
        if error:
            return error
        if "reason" in arguments:
            reason = arguments["reason"]
            if not isinstance(reason, str) or len(reason.strip()) < 3:
                return "tool_refused reason must be a phrase to find"
        return None
    return None


def _kind_error(kind: Any, index: int, seen: set[str]) -> str | None:
    where = f"capabilities.evaluator.kinds[{index}]"
    if not isinstance(kind, dict):
        return f"{where}: object expected"
    unknown_fields = sorted(set(kind) - KIND_FIELDS)
    if unknown_fields:
        return f"{where}: unknown field(s): {', '.join(unknown_fields)}"

    kind_id = kind.get("id")
    if not isinstance(kind_id, str):
        return f"{where}.id: lowercase slug expected (a-z0-9-)"
    if kind_id in KINDS:
        return f"{where}.id: {kind_id!r} is a kernel kind id"
    if kind_id in COMPOSITIONS:
        return f"{where}.id: {kind_id!r} is a composition id"
    if not _SLUG_RE.match(kind_id):
        return f"{where}.id: lowercase slug expected (a-z0-9-)"
    if len(kind_id) > MAX_KIND_ID_CHARS:
        return f"{where}.id: at most {MAX_KIND_ID_CHARS} characters expected"
    if kind_id in seen:
        return f"{where}.id: duplicate id {kind_id!r}"
    seen.add(kind_id)

    base = kind.get("from")
    if base not in PRESET_BASES:
        allowed = ", ".join(PRESET_BASES)
        return f"{where}.from: {base!r} is not a base this kernel grades ({allowed})"

    error = argument_error(base, kind, min_fragment=MIN_FRAGMENT_CHARS)
    if error:
        return f"{where}: {error}"

    description = kind.get("description")
    if not isinstance(description, str) or not description.strip():
        return f"{where}.description: non-empty string expected"
    return None


def validate_evaluator(manifest: dict) -> str | None:
    """The `capabilities.evaluator` contract; called once from the manifest contract."""
    capabilities = manifest.get("capabilities")
    if capabilities is None:
        return None
    if manifest.get("manifest_version") != 2:
        return "capabilities: manifest_version 2 required"
    if not isinstance(capabilities, dict):
        return "capabilities: object expected"
    evaluator = capabilities.get("evaluator")
    if evaluator is None:
        return None
    if not isinstance(evaluator, dict):
        return "capabilities.evaluator: object expected"
    unknown_fields = sorted(set(evaluator) - EVALUATOR_FIELDS)
    if unknown_fields:
        return f"capabilities.evaluator: unknown field(s): {', '.join(unknown_fields)}"

    kinds = evaluator.get("kinds")
    if not isinstance(kinds, list):
        return "capabilities.evaluator.kinds: list expected"
    if not kinds:
        return "capabilities.evaluator.kinds: at least one kind expected"
    if len(kinds) > MAX_EVALUATOR_KINDS:
        return (
            "capabilities.evaluator.kinds: at most "
            f"{MAX_EVALUATOR_KINDS} kinds expected"
        )
    seen: set[str] = set()
    for index, kind in enumerate(kinds):
        error = _kind_error(kind, index, seen)
        if error:
            return error
    return None


def evaluator_kinds(manifest: Any) -> dict[str, EvaluatorKind]:
    """The presets one validated manifest declares, keyed by the id a case names.

    An unvalidated or invalid manifest answers no presets: the suite loader resolves
    through the manifest contract, so a declaration no validation saw never grades.
    """
    if not isinstance(manifest, dict) or validate_evaluator(manifest) is not None:
        return {}
    evaluator = _evaluator_section(manifest)
    if evaluator is None:
        return {}
    declared: dict[str, EvaluatorKind] = {}
    for kind in evaluator["kinds"]:
        declared[str(kind["id"])] = EvaluatorKind(
            kind_id=str(kind["id"]),
            base=str(kind["from"]),
            any=tuple(str(fragment) for fragment in kind.get("any") or ()),
            plugin_id=str(manifest.get("name") or ""),
            description=str(kind["description"]),
            suffix=str(kind.get("suffix") or ""),
            reason=str(kind.get("reason") or ""),
        )
    return declared
