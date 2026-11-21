"""The repair taxonomy a malformed tool call is refused under.

A malformed tool call is refused under a named class and told the repair it
wants. ``REPAIR_TAXONOMY`` is that class set, ``REPAIR_CLASS_TOKEN`` the bracket
token a refusal carries, ``refuse`` renders the refusal and ``repair_class_of``
reads the class back — so the class set and the token are one table rather than
two.

It sat in ``core/provider_errors.py`` beside the engine-failure classifier; it
lives here now as its own seam. It is re-exported from ``core.provider_errors``
and from ``core.tools.registry`` so every existing importer keeps reading one
table without changing a line.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RepairClass:
    """One class of malformed tool call and the repair it asks for.

    ``name`` is the machine-readable token a refusal carries in brackets and the
    one ``repair_class_of`` reads back. ``hint`` is the repair instruction,
    rendered with the offending parameters so the caller can act on it.
    """

    name: str
    hint: str


REPAIR_CLASSES: tuple[RepairClass, ...] = (
    RepairClass("missing-param", "pass the required parameter(s): {names}"),
    RepairClass("enum-mismatch", "set {key!r} to one of the allowed values: {values}"),
    RepairClass("unknown-param", "drop the parameter(s) the schema does not declare: {names}"),
)

#: class name → entry. A dict, so a membership test (`name in REPAIR_TAXONOMY`)
#: and a lookup both work for a surface that imports it.
REPAIR_TAXONOMY: dict[str, RepairClass] = {rc.name: rc for rc in REPAIR_CLASSES}

#: The class token a refusal carries — the authoritative thing a reader matches.
#: Built from REPAIR_CLASSES, so a class and its token cannot drift apart.
REPAIR_CLASS_TOKEN = re.compile(
    r"\[(" + "|".join(re.escape(rc.name) for rc in REPAIR_CLASSES) + r")\]"
)


def repair_class_of(text: str) -> str | None:
    """The repair class a refusal names, read from its bracket token.

    None when the text carries no token, so a caller keeps its own wording for a
    string written before the token existed.
    """
    match = REPAIR_CLASS_TOKEN.search(text)
    return match.group(1) if match else None


def refuse(name: str, tool_class: str, detail: str, **hint_fields: object) -> str:
    """Renders the named refusal a malformed call gets.

    Shape: ``[TOOL-ERROR] <tool> [<class>]: <detail>. Repair: <hint>.`` The class
    token and the hint both come from the taxonomy, so every caller refuses the
    same way and the words around the token carry no behaviour.
    """
    entry = REPAIR_TAXONOMY[tool_class]
    hint = entry.hint.format(**hint_fields)
    return f"[TOOL-ERROR] {name} [{tool_class}]: {detail}. Repair: {hint}."
