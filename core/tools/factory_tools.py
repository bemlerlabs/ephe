"""R34 Project Factory: the facade the registry imports.

Two deterministic, evidence-gated generators are re-exported here under one
module path: ``scaffold_project`` from ``_factory_templates``, and
``build_document`` from ``_factory_brief`` together with the source readers
``_collect_source_text``, ``_san`` and ``_compose_brief_markdown``.

No generator is implemented in this file, so a tool call and a test reach the
factory the same way and see one ``__all__``.

Both generators write files and therefore travel the normal approval gate.
Their success strings only appear once the internal verification has passed,
and the playbooks relay them unchanged.

Aggregator facade: the implementation lives in _factory_templates/_factory_brief.
"""
from __future__ import annotations

from core.tools._factory_templates import scaffold_project
from core.tools._factory_brief import (
    build_document,
    _collect_source_text,
    _san,
    _compose_brief_markdown,
)

__all__ = [
    "scaffold_project",
    "build_document",
    "_collect_source_text",
    "_san",
    "_compose_brief_markdown",
]
