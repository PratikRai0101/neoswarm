"""User-controlled local memory records."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


MemoryCategory = Literal["fact", "preference", "instruction", "note"]


def _now() -> datetime:
    return datetime.now().astimezone()


class MemoryCreate(BaseModel):
    content: str
    category: MemoryCategory = "fact"
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_content(self):
        self.content = self.content.strip()
        self.tags = sorted({tag.strip() for tag in self.tags if tag.strip()})
        if not self.content:
            raise ValueError("content is required")
        if len(self.content) > 4000:
            raise ValueError("content must be 4000 characters or fewer")
        return self


class MemoryUpdate(BaseModel):
    content: str | None = None
    category: MemoryCategory | None = None
    tags: list[str] | None = None


class Memory(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    content: str
    category: MemoryCategory = "fact"
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    last_used_at: datetime | None = None
