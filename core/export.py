"""
◑ Ephe – Chat Export
core/export.py

Formats a list of chat messages as a clean Markdown document.
"""
from datetime import datetime
from typing import List, Dict, Any

def format_chat_markdown(messages: List[Dict[str, Any]]) -> str:
    """
    Convert a list of chat messages into a formatted Markdown string.

    Args:
        messages: list of dicts with 'role' and 'content'

    Returns:
        Markdown string
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    md_lines = [
        "## Chat Export",
        f"**Datum:** {now}",
        "",
        "---",
        ""
    ]

    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")

        # Map role to display name
        if role == "user":
            name = "Nutzer"
        elif role == "assistant":
            name = "Ephe"
        elif role == "system":
            name = "System"
        else:
            name = role.capitalize()

        md_lines.append(f"**{name}:**")
        md_lines.append(content.strip())
        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

    return "\n".join(md_lines)
