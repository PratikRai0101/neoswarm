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


class GitRemote(BaseModel):
    name: str
    url: str


class GitPushRequest(BaseModel):
    path: str
    remote: str = "origin"
    branch: str | None = None
    set_upstream: bool = True

    @field_validator("remote")
    @classmethod
    def validate_remote(cls, value: str) -> str:
        value = value.strip()
        if not value or value.startswith("-") or any(char.isspace() for char in value):
            raise ValueError("remote must be a non-empty Git remote name")
        return value

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.strip()
            if not value or value.startswith("-") or any(char.isspace() for char in value):
                raise ValueError("branch must be a valid branch name")
        return value


class GitPushResponse(BaseModel):
    path: str
    remote: str
    branch: str
    set_upstream: bool
    output: str = ""


class GitPullRequestCreate(BaseModel):
    path: str
    title: str
    body: str = ""
    base: str = "main"
    head: str | None = None
    remote: str = "origin"
    draft: bool = False

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("pull request title is required")
        if len(value) > 256:
            raise ValueError("pull request title must be 256 characters or fewer")
        return value

    @field_validator("base", "head", "remote")
    @classmethod
    def validate_ref(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value or value.startswith("-") or any(char.isspace() for char in value):
            raise ValueError("Git refs and remotes must be non-empty and contain no whitespace")
        return value


class GitPullRequestResponse(BaseModel):
    path: str
    url: str
    title: str
    base: str
    head: str
    draft: bool


class GitBranch(BaseModel):
    name: str
    current: bool = False
    upstream: str | None = None
