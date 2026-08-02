"""Request and response models for the local Git workspace."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class GitStatusEntry(BaseModel):
    index: str
    worktree: str
    path: str
    original_path: str | None = None


class GitStatus(BaseModel):
    path: str
    root: str
    branch: str
    upstream: str | None = None
    ahead: int = 0
    behind: int = 0
    clean: bool
    entries: list[GitStatusEntry] = Field(default_factory=list)


class GitDiff(BaseModel):
    path: str
    staged: bool = False
    diff: str
    truncated: bool = False


class GitCommitRequest(BaseModel):
    path: str
    message: str
    stage_all: bool = False

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("commit message is required")
        if len(value) > 500:
            raise ValueError("commit message must be 500 characters or fewer")
        return value


class GitCommitResponse(BaseModel):
    path: str
    commit: str
    message: str


class GitBranch(BaseModel):
    name: str
    current: bool = False
    upstream: str | None = None
