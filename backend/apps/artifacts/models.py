from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class Artifact(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str
    description: str = ""
    filename: str
    media_type: str = "application/octet-stream"
    size_bytes: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
