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
from backend.apps.settings.models import AppSettings, CustomProvider
from backend.apps.agents.providers.registry import (
    get_api_type,
    create_provider,
    provider_for_model,
    resolve_provider_name,
)


def test_known_models_have_one_canonical_provider():
    assert provider_for_model("sonnet") == "anthropic"
    assert provider_for_model("llama3.3") == "ollama"
    assert provider_for_model("gpt-5.4") == "openai"
    assert provider_for_model("locally-pulled-model:latest", "ollama") == "ollama"
    assert get_api_type("gpt-5.4") == "openai"


def test_explicit_provider_aliases_are_normalized():
    assert resolve_provider_name("Ollama", "llama3.3") == "ollama"
    assert resolve_provider_name("Codex", "gpt-5.4") == "openai"
    assert resolve_provider_name(None, "llama3.3") == "ollama"


@pytest.mark.asyncio
async def test_offline_ollama_examples_are_not_advertised(monkeypatch):
    import httpx
    import backend.apps.agents.agents as agents_api
    import backend.apps.settings.settings as settings_api

    class OfflineClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            raise httpx.ConnectError("Ollama unavailable")

    monkeypatch.setattr(httpx, "AsyncClient", OfflineClient)
    monkeypatch.setattr(settings_api, "load_settings", AppSettings)

    catalog = await agents_api.list_models()

    assert "Ollama" not in catalog["models"]


@pytest.mark.asyncio
async def test_model_catalog_exposes_direct_openai_models_with_a_key(monkeypatch):
    import backend.apps.agents.agents as agents_api
    import backend.apps.settings.settings as settings_api

    monkeypatch.setattr(
        settings_api,
        "load_settings",
        lambda: AppSettings(
            openai_api_key="test-key",
            google_api_key="google-key",
            copilot_github_token="copilot-token-without-an-adapter",
        ),
    )

    catalog = await agents_api.list_models()

    assert all(item["provider"] == "OpenAI" for item in catalog["models"]["OpenAI"])
    assert {item["value"] for item in catalog["models"]["OpenAI"]} == {
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.3-codex",
    }
    assert {item["value"] for item in catalog["models"]["Google"]} >= {
        "gemini-2.5-pro",
        "gemini-2.5-flash",
    }
    assert "Copilot" not in catalog["models"]
    assert "GitHub Models" not in catalog["models"]


def test_google_provider_uses_the_supported_openai_compatible_endpoint():
    provider = create_provider("google", AppSettings(google_api_key="google-key"))

    assert provider.__class__.__name__ == "OpenAICompatProvider"
    assert str(provider.client.base_url) == (
        "https://generativelanguage.googleapis.com/v1beta/openai/"
    )


def test_custom_provider_is_resolved_before_openrouter_fallback():
    settings = AppSettings(
        custom_providers=[
            CustomProvider(
                name="Private Gateway",
                base_url="https://models.internal.example/v1",
                api_key="custom-key",
                models=[{"value": "private-model", "label": "Private Model"}],
            )
        ]
    )

    provider = create_provider("Private Gateway", settings)

    assert provider.__class__.__name__ == "OpenAICompatProvider"
    assert str(provider.client.base_url) == "https://models.internal.example/v1/"


@pytest.mark.asyncio
async def test_model_catalog_includes_openrouter_and_custom_models(monkeypatch):
    import httpx
    import backend.apps.agents.agents as agents_api
    import backend.apps.settings.settings as settings_api

    class FakeResponse:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, **_kwargs):
            if "openrouter.ai" in url:
                return FakeResponse(
                    {
                        "data": [
                            {
                                "id": "vendor/agent-model",
                                "name": "Vendor: Agent Model",
                                "context_length": 262_144,
                                "architecture": {"output_modalities": ["text"]},
                                "supported_parameters": ["tools", "reasoning"],
                            },
                            {
                                "id": "vendor/image-only",
                                "name": "Image only",
                                "architecture": {"output_modalities": ["image"]},
                            },
                        ]
                    }
                )
            raise httpx.ConnectError("Ollama unavailable")

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    monkeypatch.setattr(
        settings_api,
        "load_settings",
        lambda: AppSettings(
            openrouter_api_key="openrouter-key",
            custom_providers=[
                CustomProvider(
                    name="Private Gateway",
                    base_url="https://models.internal.example/v1",
                    api_key="custom-key",
                    models=[
                        {
                            "value": "private-model",
                            "label": "Private Model",
                            "context_window": 64_000,
                        }
                    ],
                )
            ],
        ),
    )

    catalog = (await agents_api.list_models())["models"]

    assert catalog["OpenRouter"] == [
        {
            "provider": "OpenRouter",
            "value": "vendor/agent-model",
            "label": "Vendor: Agent Model",
            "context_window": 262_144,
            "reasoning": True,
        }
    ]
    assert catalog["Private Gateway"][0]["value"] == "private-model"


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
