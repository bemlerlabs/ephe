"""The document tools. Each one asks the host.

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


def create_pdf(arguments, _state_dir, bridge):
    arguments = arguments or {}
    return _ask(
        "create_pdf",
        lambda: bridge.create_pdf(
            _required(arguments, "title"),
            _required(arguments, "content"),
            **_kwargs(arguments, ("filename", "template", "document")),
        ),
    )


def create_docx(arguments, _state_dir, bridge):
    arguments = arguments or {}
    return _ask(
        "create_docx",
        lambda: bridge.create_docx(
            _required(arguments, "title"),
            _required(arguments, "content"),
            **_kwargs(arguments, ("filename",)),
        ),
    )


def create_qrcode(arguments, _state_dir, bridge):
    arguments = arguments or {}
    return _ask(
        "create_qrcode",
        lambda: bridge.create_qrcode(
            _required(arguments, "data"),
            **_kwargs(arguments, ("filename", "fill_color", "back_color")),
        ),
    )


def extract_pdf_text(arguments, _state_dir, bridge):
    arguments = arguments or {}
    return _ask(
        "extract_pdf_text",
        lambda: bridge.extract_pdf_text(
            _required(arguments, "path"),
            **_kwargs(arguments, ("max_chars",)),
        ),
    )


def build_document(arguments, _state_dir, bridge):
    arguments = arguments or {}
    return _ask(
        "build_document",
        lambda: bridge.build_document(
            _required(arguments, "topic"),
            **_kwargs(arguments, ("source_paths", "include_web_research", "filename")),
        ),
    )


def export_source_brief(arguments, _state_dir, bridge):
    arguments = arguments or {}
    return _ask(
        "export_source_brief",
        lambda: bridge.export_source_brief(
            _required(arguments, "notebook_path"),
            **_kwargs(arguments, ("question", "filename")),
        ),
    )


def create_source_notebook(arguments, _state_dir, bridge):
    arguments = arguments or {}
    paths = arguments.get("paths")
    if paths is None:
        paths = []
    return _ask(
        "create_source_notebook",
        lambda: bridge.create_source_notebook(
            paths, **_kwargs(arguments, ("title", "notebook_id", "extensions"))
        ),
    )


def query_source_notebook(arguments, _state_dir, bridge):
    arguments = arguments or {}
    return _ask(
        "query_source_notebook",
        lambda: bridge.query_source_notebook(
            _required(arguments, "notebook_path"),
            _required(arguments, "question"),
            **_kwargs(arguments, ("max_chunks",)),
        ),
    )


def verify_artifact(arguments, _state_dir, bridge):
    arguments = arguments or {}
    return _ask(
        "verify_artifact",
        lambda: bridge.verify_artifact(
            _required(arguments, "path"),
            **_kwargs(arguments, ("checks",)),
        ),
    )
