from datetime import datetime
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


TerminalStatus = Literal["running", "stopped", "exited"]


class Terminal(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    title: str
    cwd: str
    shell: str
    status: TerminalStatus = "stopped"
    pid: Optional[int] = None
    exit_code: Optional[int] = None
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class TerminalCreate(BaseModel):
    cwd: Optional[str] = None
    shell: Optional[str] = None
    title: Optional[str] = Field(default=None, max_length=100)


class TerminalResize(BaseModel):
    cols: int = Field(ge=1, le=500)
    rows: int = Field(ge=1, le=300)
