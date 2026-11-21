"""The deck, diagram and drawing tools. Each one asks the host.

The worker has no store and cannot import the application. The bridge
handle is the third argument. The text it brings back is the tool result,
including the failure line the kernel tool already writes.
"""

from __future__ import annotations


def _text(page) -> str:
    body = str((page or {}).get("text") or "")
    if (page or {}).get("truncated"):
        return body + "\n[truncated]"
    return body


def _failure(name: str, exc: BaseException) -> str:
    detail = getattr(exc, "detail", "") or getattr(exc, "code", "") or type(exc).__name__
    return f"[tool-error '{name}': {detail}]"


def _ask(name: str, call):
    try:
        page = call()
    except Exception as exc:
        return _failure(name, exc)
    return _text(page)


def _kwargs(arguments, names):
    arguments = arguments or {}
    extra = {}
    for name in names:
        if name in arguments and arguments[name] is not None:
            extra[name] = arguments[name]
    return extra


def _required(arguments, key: str) -> str:
    arguments = arguments or {}
    value = arguments.get(key)
    return "" if value is None else str(value)


def _body(arguments, key: str):
    arguments = arguments or {}
    value = arguments.get(key)
    return "" if value is None else value


def create_pptx_deck(arguments, _state_dir, bridge):
    arguments = arguments or {}
    extra = _kwargs(
        arguments,
        (
            "audience", "thesis", "filename", "deck_profile", "design_theme",
            "source_notes", "evidence_level", "enterprise_grade",
            "template_path", "brand_name", "brand_primary", "brand_secondary",
            "deck_quality_profile", "source_notebook_path", "asset_paths",
        ),
    )
    if arguments.get("slides") is not None:
        extra["slides"] = arguments.get("slides")
    return _ask(
        "create_pptx_deck",
        lambda: bridge.create_pptx_deck(_required(arguments, "topic"), **extra),
    )


def create_pitch_deck(arguments, _state_dir, bridge):
    arguments = arguments or {}
    extra = _kwargs(
        arguments,
        (
            "audience", "thesis", "filename", "include_animation_preview",
            "deck_profile", "design_theme", "source_notes", "evidence_level",
            "enterprise_grade", "deck_quality_profile", "brand_kit",
            "source_notebook_path", "asset_paths",
        ),
    )
    if arguments.get("slides") is not None:
        extra["slides"] = arguments.get("slides")
    return _ask(
        "create_pitch_deck",
        lambda: bridge.create_pitch_deck(_required(arguments, "topic"), **extra),
    )


def inspect_pptx_template(arguments, _state_dir, bridge):
    return _ask(
        "inspect_pptx_template",
        lambda: bridge.inspect_pptx_template(
            _required(arguments, "path"),
            **_kwargs(arguments, ("filename",)),
        ),
    )


def edit_pptx_template(arguments, _state_dir, bridge):
    arguments = arguments or {}
    replacements = arguments.get("replacements")
    if replacements is None:
        replacements = {}
    return _ask(
        "edit_pptx_template",
        lambda: bridge.edit_pptx_template(
            _required(arguments, "template_path"),
            replacements,
            **_kwargs(arguments, ("filename",)),
        ),
    )


def qa_pptx_deck(arguments, _state_dir, bridge):
    return _ask(
        "qa_pptx_deck",
        lambda: bridge.qa_pptx_deck(_required(arguments, "pptx_path")),
    )


def create_diagram(arguments, _state_dir, bridge):
    return _ask(
        "create_diagram",
        lambda: bridge.create_diagram(
            _required(arguments, "kind"),
            _required(arguments, "title"),
            _body(arguments, "items"),
            **_kwargs(arguments, ("filename", "theme")),
        ),
    )


def create_svg(arguments, _state_dir, bridge):
    return _ask(
        "create_svg",
        lambda: bridge.create_svg(
            _required(arguments, "svg_code"),
            **_kwargs(arguments, ("filename",)),
        ),
    )
