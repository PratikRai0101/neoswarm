"""Persistent schedules and request models for NeoSwarm automations."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


ScheduleKind = Literal["interval", "once"]
ScheduleStatus = Literal["scheduled", "running", "completed", "failed", "disabled"]


def _now() -> datetime:
    return datetime.now().astimezone()


class ScheduleBase(BaseModel):
    name: str
    prompt: str
    kind: ScheduleKind = "interval"
    interval_seconds: int | None = Field(default=None, ge=10, le=31_536_000)
    run_at: datetime | None = None
    model: str = "sonnet"
    provider: str | None = None
    target_directory: str | None = None
    enabled: bool = True

    @model_validator(mode="after")
    def validate_timing(self):
        self.name = self.name.strip()
        self.prompt = self.prompt.strip()
        if not self.name:
            raise ValueError("name is required")
        if not self.prompt:
            raise ValueError("prompt is required")
        if self.kind == "interval" and self.interval_seconds is None:
            raise ValueError("interval_seconds is required for interval schedules")
        if self.kind == "once" and self.run_at is None:
            raise ValueError("run_at is required for one-time schedules")
        return self


class ScheduleCreate(ScheduleBase):
    pass


class ScheduleUpdate(BaseModel):
    name: str | None = None
    prompt: str | None = None
    kind: ScheduleKind | None = None
    interval_seconds: int | None = Field(default=None, ge=10, le=31_536_000)
    run_at: datetime | None = None
    model: str | None = None
    provider: str | None = None
    target_directory: str | None = None
    enabled: bool | None = None


class ScheduledTask(ScheduleBase):
    id: str = Field(default_factory=lambda: uuid4().hex)
    status: ScheduleStatus = "scheduled"
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    last_session_id: str | None = None
    last_error: str | None = None

    @classmethod
    def from_create(cls, request: ScheduleCreate) -> "ScheduledTask":
        task = cls(**request.model_dump())
        task.next_run_at = (
            request.run_at
            if request.kind == "once"
            else _now() + timedelta(seconds=request.interval_seconds or 10)
        )
        return task
