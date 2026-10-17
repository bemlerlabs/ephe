"""
Shared type definitions for Ephe.

Defines the Message TypedDict used as the shared contract
between all modules (chat, session, ui).
"""

from __future__ import annotations

from typing import Literal, TypedDict


class Message(TypedDict):
    """An Ollama-compatible chat message."""

    role: Literal["user", "assistant", "system"]
    content: str
