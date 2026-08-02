"""Persistent memory storage, API, and native-tool behavior."""

import asyncio
import json

from fastapi.testclient import TestClient

from backend.apps.agents.tools.base import ToolContext
from backend.apps.agents.tools.memory import MemorySaveTool, MemorySearchTool
from backend.apps.memory.memory import MemoryStore
from backend.apps.memory.models import Memory, MemoryCreate
from backend.main import app


def test_memory_store_persists_and_searches_relevant_records(tmp_path):
    store = MemoryStore(tmp_path / "memory")
    memory = Memory(
        **MemoryCreate(
            content="The user prefers concise release notes.",
            category="preference",
            tags=["writing"],
        ).model_dump()
    )
    store.items[memory.id] = memory
    store.save(memory)

    reloaded = MemoryStore(tmp_path / "memory")
    results = reloaded.list("release notes")
    assert [item.id for item in results] == [memory.id]
    assert "concise release notes" in (reloaded.context_for("release") or "")


def test_memory_api_supports_create_search_update_and_delete(tmp_path, monkeypatch):
    import backend.apps.memory.memory as memory_module

    store = MemoryStore(tmp_path / "memory")
    monkeypatch.setattr(memory_module, "memory_store", store)

    with TestClient(app) as client:
        created = client.post(
            "/api/memory",
            json={
                "content": "Use UTC timestamps in reports",
                "category": "instruction",
                "tags": ["reports"],
            },
        )
        assert created.status_code == 200
        memory_id = created.json()["memory"]["id"]

        searched = client.get("/api/memory", params={"q": "UTC"})
        assert searched.status_code == 200
        assert searched.json()["memories"][0]["id"] == memory_id

        updated = client.patch(
            f"/api/memory/{memory_id}",
            json={"content": "Use ISO-8601 UTC timestamps in reports"},
        )
        assert updated.status_code == 200
        assert "ISO-8601" in updated.json()["memory"]["content"]

        deleted = client.delete(f"/api/memory/{memory_id}")
        assert deleted.status_code == 200
        assert client.get(f"/api/memory/{memory_id}").status_code == 404


def test_memory_tools_save_and_search(tmp_path, monkeypatch):
    import backend.apps.memory.memory as memory_module

    store = MemoryStore(tmp_path / "memory")
    monkeypatch.setattr(memory_module, "memory_store", store)
    context = ToolContext(cwd=str(tmp_path), session_id="test-session")

    saved = asyncio.run(
        MemorySaveTool().execute(
            {
                "content": "The project uses Python 3.11 for backend tests.",
                "category": "fact",
                "tags": ["testing"],
            },
            context,
        )
    )
    payload = json.loads(saved[0]["text"])
    assert payload["category"] == "fact"

    found = asyncio.run(
        MemorySearchTool().execute({"query": "Python backend"}, context)
    )
    results = json.loads(found[0]["text"])
    assert len(results) == 1
    assert results[0]["id"] == payload["id"]
