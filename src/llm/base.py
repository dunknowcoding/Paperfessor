"""Provider-agnostic chat completion types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class FinishReason(str, Enum):
    STOP = "stop"
    LENGTH = "length"
    TOOL_CALL = "tool_call"
    CONTENT_FILTER = "content_filter"
    ERROR = "error"


@dataclass
class ChatMessage:
    role: Role
    content: str
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list["ToolCall"] = field(default_factory=list)


@dataclass
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatRequest:
    model: str
    messages: list[ChatMessage]
    temperature: float = 1.0
    max_tokens: int | None = None
    top_p: float | None = None
    stop: list[str] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    response_format: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ChatResponse:
    text: str
    finish_reason: FinishReason = FinishReason.STOP
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    provider: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "FinishReason",
    "Role",
    "ToolCall",
    "Usage",
]
