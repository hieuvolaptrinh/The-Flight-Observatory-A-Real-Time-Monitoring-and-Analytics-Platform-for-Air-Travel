from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class PipelineOutput(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Results(BaseModel):
    service: str
    storage: Literal["memory"] = "memory"
    ready: bool = False
    updated_at: datetime | None = None
    output: PipelineOutput = Field(default_factory=PipelineOutput)


class Job(BaseModel):
    id: str
    service: str
    trigger: Literal["manual", "schedule"]
    status: Literal["running", "completed", "not_implemented", "failed"]
    started_at: datetime
    finished_at: datetime | None = None
    error: str | None = None
