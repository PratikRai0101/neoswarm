"""Provider inference and session-selection behaviour."""

import asyncio
import os
import tempfile
from unittest.mock import AsyncMock

import pytest

# Must be set before backend path modules are imported.
os.environ.setdefault("NEOSWARM_DATA_DIR", tempfile.mkdtemp(prefix="neoswarm-provider-tests-"))

from backend.apps.agents.agent_manager import AgentManager
from backend.apps.agents.models import AgentConfig
from backend.apps.settings.models import AppSettings
from backend.apps.agents.providers.registry import (
    get_api_type,
    provider_for_model,
    resolve_provider_name,
)


def test_known_models_have_one_canonical_provider():
    assert provider_for_model("sonnet") == "anthropic"
    assert provider_for_model("llama3.3") == "ollama"
    assert provider_for_model("gpt-5.4") == "openai"
    assert get_api_type("gpt-5.4") == "openai"


def test_explicit_provider_aliases_are_normalized():
    assert resolve_provider_name("Ollama", "llama3.3") == "ollama"
    assert resolve_provider_name("Codex", "gpt-5.4") == "openai"
    assert resolve_provider_name(None, "llama3.3") == "ollama"


@pytest.mark.asyncio
async def test_model_catalog_exposes_direct_openai_models_with_a_key(monkeypatch):
    import backend.apps.agents.agents as agents_api
    import backend.apps.settings.settings as settings_api

    monkeypatch.setattr(
        settings_api, "load_settings", lambda: AppSettings(openai_api_key="test-key")
    )

    catalog = await agents_api.list_models()

    assert all(item["provider"] == "OpenAI" for item in catalog["models"]["OpenAI"])
    assert {item["value"] for item in catalog["models"]["OpenAI"]} == {
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.3-codex",
    }


@pytest.mark.asyncio
async def test_session_infers_provider_from_launch_and_model_switch(tmp_path, monkeypatch):
    manager = AgentManager()
    monkeypatch.setattr(manager, "_run_agent_loop", AsyncMock())

    session = await manager.launch_agent(
        AgentConfig(model="llama3.3", mode="chat", target_directory=str(tmp_path))
    )
    assert session.provider == "ollama"

    await manager.send_message(session.id, "Switch providers", model="sonnet")
    await asyncio.sleep(0)

    assert session.model == "sonnet"
    assert session.provider == "anthropic"
    assert session.needs_fork is True
