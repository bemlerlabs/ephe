from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import List, Dict, Any
from core.export import format_chat_markdown

router = APIRouter()

class ExportRequest(BaseModel):
    messages: List[Dict[str, Any]]

@router.post("/export", tags=["Export"])
async def export_chat(request: ExportRequest):
    """Accepts the chat messages and returns a Markdown file as the response."""
    md_content = format_chat_markdown(request.messages)
    return PlainTextResponse(
        content=md_content,
        media_type="text/markdown",
        headers={
            "Content-Disposition": 'attachment; filename="chat_export.md"'
        }
    )
