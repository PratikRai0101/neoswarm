"""Persistent local memory store and REST endpoints."""

from __future__ import annotations

import os
import re
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, Query

from backend.config.Apps import SubApp
from backend.config.paths import MEMORY_DIR
from backend.apps.memory.models import Memory, MemoryCreate, MemoryUpdate


class MemoryStore:
    """Small JSON repository with lexical search for relevant memories."""

    def __init__(self, directory: str | os.PathLike[str]):
        self.directory = Path(directory).expanduser().resolve()
        self.items: dict[str, Memory] = {}
        self.load()

    def load(self) -> None:
        self.items = {}
        if not self.directory.exists():
            return
        for path in self.directory.glob("*.json"):
            try:
                memory = Memory.model_validate_json(path.read_text())
            except Exception:
                continue
            self.items[memory.id] = memory

    def save(self, memory: Memory) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self.directory / f"{memory.id}.json"
        descriptor, temporary = tempfile.mkstemp(
            prefix=f"{memory.id}-", suffix=".tmp", dir=self.directory
        )
        try:
            with os.fdopen(descriptor, "w") as handle:
                handle.write(memory.model_dump_json(indent=2))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        except Exception:
            try:
                os.close(descriptor)
            except OSError:
                pass
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    def delete(self, memory_id: str) -> None:
        self.items.pop(memory_id, None)
        (self.directory / f"{memory_id}.json").unlink(missing_ok=True)

    def list(self, query: str = "", limit: int = 50) -> list[Memory]:
        query_terms = self._terms(query)
        scored: list[tuple[int, Memory]] = []
        for memory in self.items.values():
            haystack = " ".join([memory.content, memory.category, *memory.tags]).lower()
            score = sum(1 for term in query_terms if term in haystack)
            if query_terms and score == 0:
                continue
            scored.append((score, memory))
        scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
        return [memory for _, memory in scored[: max(1, min(limit, 200))]]

    def context_for(self, query: str, max_chars: int = 6000) -> str | None:
        memories = self.list(query, limit=20)
        if not memories:
            return None
        lines = [
            "<long_term_memory>",
            "These are user-approved local memories. Use them when relevant, but do not invent new facts:",
        ]
        used = 0
        for memory in memories:
            line = f"- [{memory.category}] {memory.content}"
            if memory.tags:
                line += f" (tags: {', '.join(memory.tags)})"
            if used + len(line) + 1 > max_chars:
                break
            lines.append(line)
            used += len(line) + 1
        lines.append("</long_term_memory>")
        return "\n".join(lines)

    @staticmethod
    def _terms(query: str) -> list[str]:
        return [term.lower() for term in re.findall(r"[a-zA-Z0-9_'-]+", query) if len(term) > 1]


memory_store = MemoryStore(MEMORY_DIR)


@asynccontextmanager
async def memory_lifespan():
    memory_store.load()
    yield


memory = SubApp("memory", memory_lifespan)


def _get_or_404(memory_id: str) -> Memory:
    item = memory_store.items.get(memory_id)
    if not item:
        raise HTTPException(status_code=404, detail="Memory not found")
    return item


@memory.router.get("")
async def list_memories(q: str = Query(""), limit: int = Query(50, ge=1, le=200)):
    return {"memories": [item.model_dump(mode="json") for item in memory_store.list(q, limit)]}


@memory.router.get("/{memory_id}")
async def get_memory(memory_id: str):
    return {"memory": _get_or_404(memory_id).model_dump(mode="json")}


@memory.router.post("")
async def create_memory(body: MemoryCreate):
    item = Memory(**body.model_dump())
    memory_store.items[item.id] = item
    memory_store.save(item)
    return {"memory": item.model_dump(mode="json")}


@memory.router.patch("/{memory_id}")
async def update_memory(memory_id: str, body: MemoryUpdate):
    item = _get_or_404(memory_id)
    values = item.model_dump()
    for key, value in body.model_dump(exclude_unset=True).items():
        if key == "content" and value is not None:
            value = value.strip()
            if not value:
                raise HTTPException(status_code=422, detail="content is required")
            if len(value) > 4000:
                raise HTTPException(status_code=422, detail="content must be 4000 characters or fewer")
        if key == "tags" and value is not None:
            value = sorted({tag.strip() for tag in value if tag.strip()})
        values[key] = value
    updated = Memory(**values)
    updated.updated_at = datetime.now().astimezone()
    memory_store.items[memory_id] = updated
    memory_store.save(updated)
    return {"memory": updated.model_dump(mode="json")}


@memory.router.delete("/{memory_id}")
async def delete_memory(memory_id: str):
    _get_or_404(memory_id)
    memory_store.delete(memory_id)
    return {"ok": True}


def memory_context(query: str) -> str | None:
    """Return relevant memory text for an agent system prompt."""
    return memory_store.context_for(query)
