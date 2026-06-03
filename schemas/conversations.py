from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import Any, Literal

from pydantic import BaseModel, Field


class ConversationThreadCreate(BaseModel):
    project: str
    title: str
    source: str = "manual"


class ConversationThreadOut(BaseModel):
    id: int
    project: str
    title: str
    source: str
    created_at: datetime
    updated_at: datetime
    created_by_username: str | None = None


class ConversationMessageInput(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    timestamp: str | None = None
    metadata: dict[str, Any] | None = None


class ConversationMessagesAppendRequest(BaseModel):
    messages: list[ConversationMessageInput] = Field(default_factory=list)


class ConversationMessageOut(BaseModel):
    id: int
    seq_no: int
    role: str
    content: str
    timestamp: datetime
    created_by_username: str | None = None
    metadata: dict[str, Any] | None = None


class ConversationImportJsonRequest(BaseModel):
    project: str
    title: str
    messages: list[ConversationMessageInput] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationImportTextRequest(BaseModel):
    project: str
    title: str
    text: str
    delimiter: str = "=== TURN ==="


class ConversationImportOut(BaseModel):
    import_id: int
    thread_id: int
    status: str
    format: str
    error_message: str | None = None


class ConversationAnalyzeOut(BaseModel):
    thread_id: int
    turns: int
    user_turns: int
    assistant_turns: int
    system_turns: int
    tool_turns: int
    total_chars: int
    started_at: datetime | None = None
    ended_at: datetime | None = None


class ConversationAnalysisLogOut(BaseModel):
    thread_id: int
    generated_at: datetime
    log_path: str
    analysis: ConversationAnalyzeOut
    log_text: str
