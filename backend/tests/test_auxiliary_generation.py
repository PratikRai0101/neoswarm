"""Provider-agnostic auxiliary text generation contracts."""

import pytest

import backend.apps.agents.auxiliary as auxiliary
from backend.apps.agents.providers.base import ContentBlock, ModelResponse
from backend.apps.settings.models import AppSettings, CustomProvider


@pytest.mark.asyncio
async def test_default_model_is_honored_when_its_provider_is_configured():
    selection = await auxiliary.resolve_auxiliary_model(
        AppSettings(default_model="sonnet", anthropic_api_key="test-key")
    )

    assert selection == ("sonnet", "anthropic")


@pytest.mark.asyncio
async def test_fast_cloud_fallback_does_not_require_anthropic():
    selection = await auxiliary.resolve_auxiliary_model(
        AppSettings(openai_api_key="test-key"), preferred_tier="fast"
    )

    assert selection == ("gpt-5.4-mini", "openai")


@pytest.mark.asyncio
async def test_local_model_is_selected_when_ollama_is_the_only_provider(monkeypatch):
    async def installed_models():
        return ["qwen-local:latest"]

    monkeypatch.setattr(auxiliary, "_list_ollama_models", installed_models)

    selection = await auxiliary.resolve_auxiliary_model(AppSettings())

    assert selection == ("qwen-local:latest", "ollama")


@pytest.mark.asyncio
async def test_custom_default_model_preserves_provider_identity():
    settings = AppSettings(
        default_model="private-model",
        custom_providers=[
            CustomProvider(
                name="Private Gateway",
                base_url="https://models.internal.example/v1",
                api_key="key",
                models=[{"value": "private-model", "label": "Private"}],
            )
        ],
    )

    selection = await auxiliary.resolve_auxiliary_model(settings)

    assert selection == ("private-model", "Private Gateway")


@pytest.mark.asyncio
async def test_generation_hides_adapter_lifecycle_and_extracts_text(monkeypatch):
    calls = {}

    class FakeProvider:
        async def create_message(self, **kwargs):
            calls["request"] = kwargs
            return ModelResponse(
                content=[
                    ContentBlock(type="text", text="Generated "),
                    ContentBlock(type="text", text="title"),
                ],
                stop_reason="end_turn",
            )

        async def close(self):
            calls["closed"] = True

    def provider_factory(provider, settings):
        calls["provider"] = provider
        calls["settings"] = settings
        return FakeProvider()

    monkeypatch.setattr(auxiliary, "create_provider", provider_factory)
    settings = AppSettings(openai_api_key="test-key")

    text = await auxiliary.generate_auxiliary_text(
        "Label this prompt",
        system="Return a title",
        max_tokens=20,
        settings=settings,
    )

    assert text == "Generated title"
    assert calls["provider"] == "openai"
    assert calls["request"]["model"] == "gpt-5.4-mini"
    assert calls["request"]["tools"] == []
    assert calls["closed"] is True


@pytest.mark.asyncio
async def test_missing_provider_has_an_actionable_error(monkeypatch):
    async def no_local_models():
        return []

    monkeypatch.setattr(auxiliary, "_list_ollama_models", no_local_models)

    with pytest.raises(ValueError, match="Start Ollama or configure a provider"):
        await auxiliary.resolve_auxiliary_model(AppSettings())
