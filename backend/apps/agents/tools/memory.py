"""Native tools for explicit, user-controlled long-term memory."""

from __future__ import annotations

import json

from backend.apps.agents.tools.base import BaseTool, ToolContext


def _text(value: str) -> list[dict]:
    return [{"type": "text", "text": value}]


class MemorySearchTool(BaseTool):
    name = "MemorySearch"
    description = "Search local user-approved memories for information relevant to the current task."

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Terms to search for."},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
            },
            "required": ["query"],
            "additionalProperties": False,
        }

    async def execute(self, input_data: dict, context: ToolContext) -> list[dict]:
        from backend.apps.memory.memory import memory_store

        results = [
            item.model_dump(mode="json")
            for item in memory_store.list(input_data.get("query", ""), input_data.get("limit", 8))
        ]
        return _text(json.dumps(results))


class MemorySaveTool(BaseTool):
    name = "MemorySave"
    description = "Save a durable local memory only when the user explicitly asks you to remember it."

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The fact, preference, instruction, or note to remember."},
                "category": {"type": "string", "enum": ["fact", "preference", "instruction", "note"], "default": "fact"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["content"],
            "additionalProperties": False,
        }

    async def execute(self, input_data: dict, context: ToolContext) -> list[dict]:
        from backend.apps.memory.memory import memory_store
        from backend.apps.memory.models import Memory, MemoryCreate

        try:
            request = MemoryCreate(**input_data)
            item = Memory(**request.model_dump())
            memory_store.items[item.id] = item
            memory_store.save(item)
        except Exception as exc:
            return _text(f"Unable to save memory: {exc}")
        return _text(json.dumps({"id": item.id, "content": item.content, "category": item.category}))


class MemoryDeleteTool(BaseTool):
    name = "MemoryDelete"
    description = "Delete a local memory by ID when the user asks to forget it."

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"memory_id": {"type": "string", "description": "Memory ID."}},
            "required": ["memory_id"],
            "additionalProperties": False,
        }

    async def execute(self, input_data: dict, context: ToolContext) -> list[dict]:
        from backend.apps.memory.memory import memory_store

        memory_id = input_data.get("memory_id", "")
        if memory_id not in memory_store.items:
            return _text(f"Memory not found: {memory_id}")
        memory_store.delete(memory_id)
        return _text(f"Deleted memory {memory_id}.")
