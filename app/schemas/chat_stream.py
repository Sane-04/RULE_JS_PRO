from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatStreamEventData(BaseModel):
    session_id: str = Field(..., description="session id")
    step: str = Field(..., description="workflow step name")
    status: Literal["start", "end", "error"] = Field(..., description="step status")
    message: str = Field(..., description="status text")
    timestamp: str = Field(..., description="event timestamp")
    seq: int = Field(..., ge=1, description="event sequence")
    result: dict[str, Any] | None = Field(default=None, description="final result, only for workflow_end")
    step_payload: dict[str, Any] | None = Field(default=None, description="step payload for incremental UI updates")


class ChatStreamEvent(BaseModel):
    event: Literal["workflow_start", "step_start", "step_end", "workflow_error", "workflow_end"]
    data: ChatStreamEventData
