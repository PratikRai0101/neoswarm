from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


_SAFE_HOST_CHARS = re.compile(r"^[^\s@/\\;|&`]+$")


class SSHProfile(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str = Field(min_length=1, max_length=100)
    host: str = Field(min_length=1, max_length=255)
    user: str = Field(default="", max_length=100)
    port: int = Field(default=22, ge=1, le=65535)
    identity_file: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("profile name is required")
        return value

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        value = value.strip()
        if value.startswith("-") or not _SAFE_HOST_CHARS.fullmatch(value):
            raise ValueError("host contains unsupported characters")
        return value

    @field_validator("user")
    @classmethod
    def validate_user(cls, value: str) -> str:
        value = value.strip()
        if value.startswith("-") or not value or not _SAFE_HOST_CHARS.fullmatch(value):
            if value:
                raise ValueError("user contains unsupported characters")
            return value
        return value

    @field_validator("identity_file")
    @classmethod
    def normalize_identity_file(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        path = Path(value).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"Identity file does not exist: {path}")
        return str(path)

    @property
    def target(self) -> str:
        destination = f"{self.user}@{self.host}" if self.user else self.host
        return f"{destination}:{self.port}"


class SSHProfileCreate(BaseModel):
    model_config = {"extra": "forbid"}

    name: str = Field(min_length=1, max_length=100)
    host: str = Field(min_length=1, max_length=255)
    user: str = Field(default="", max_length=100)
    port: int = Field(default=22, ge=1, le=65535)
    identity_file: Optional[str] = None

    @model_validator(mode="after")
    def validate_profile(self) -> "SSHProfileCreate":
        SSHProfile(**self.model_dump())
        return self


class SSHProfileUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    host: Optional[str] = Field(default=None, min_length=1, max_length=255)
    user: Optional[str] = Field(default=None, max_length=100)
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    identity_file: Optional[str] = None
