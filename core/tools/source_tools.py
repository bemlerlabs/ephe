"""Ephe – Source notebook tools."""

from __future__ import annotations

import asyncio

from core.source_notebook import (
    create_source_notebook_index,
    export_source_brief_file,
    format_notebook_created,
    format_notebook_query,
    query_source_notebook_index,
)


async def create_source_notebook(
    paths: list[str] | str,
    title: str = "Ephe Source Notebook",
    notebook_id: str = "",
    extensions: list[str] | None = None,
) -> str:
    out = await asyncio.to_thread(
        create_source_notebook_index,
        paths=paths,
        title=title,
        notebook_id=notebook_id,
        extensions=extensions,
    )
    return format_notebook_created(out)


async def query_source_notebook(
    notebook_path: str,
    question: str,
    max_chunks: int = 6,
) -> str:
    result = await asyncio.to_thread(
        query_source_notebook_index,
        notebook_path=notebook_path,
        question=question,
        max_chunks=max_chunks,
    )
    return format_notebook_query(result)


async def export_source_brief(
    notebook_path: str,
    question: str = "",
    filename: str = "",
) -> str:
    out = await asyncio.to_thread(
        export_source_brief_file,
        notebook_path=notebook_path,
        question=question,
        filename=filename,
    )
    return f"SOURCE_BRIEF_FILE:{out}"
