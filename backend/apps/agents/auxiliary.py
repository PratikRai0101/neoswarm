"""Provider-agnostic text generation for auxiliary application features.

Callers provide text-generation intent; this module owns provider selection,
model resolution, adapter lifecycle, and response extraction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.apps.agents.providers.base import ProviderMessage
from backend.apps.agents.providers.registry import (
    _find_builtin_model,
    create_provider,
    provider_for_model,
)

if TYPE_CHECKING:
    from backend.apps.settings.models import AppSettings


async def _list_ollama_models() -> list[str]:
    """Return locally installed Ollama model names, or an empty list offline."""
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:11434/api/tags", timeout=2.0)
        if response.status_code != 200:
            return []
        return [
            model.get("name", "")
            for model in response.json().get("models", [])
            if model.get("name")
        ]
    except Exception:
        return []


def _provider_is_configured(settings: AppSettings, provider: str) -> bool:
    if provider == "anthropic":
        return bool(settings.anthropic_api_key)
    if provider == "openai":
        return bool(settings.openai_api_key)
    if provider == "google":
        return bool(settings.google_api_key)
    if provider == "openrouter":
        return bool(settings.openrouter_api_key)
    if provider == "ollama":
        return True
    return any(
        custom.name.lower() == provider.lower()
        for custom in settings.custom_providers
    )


def _custom_provider_for_model(settings: AppSettings, model: str) -> str | None:
    for custom in settings.custom_providers:
        if any(
            candidate.get("value", candidate.get("id", "")) == model
            for candidate in custom.models
        ):
            return custom.name
    return None


async def resolve_auxiliary_model(
    settings: AppSettings,
    *,
    preferred_tier: str = "fast",
    model: str | None = None,
    provider: str | None = None,
) -> tuple[str, str]:
    """Resolve an executable ``(model, provider)`` pair.

    An explicit selection is honored or rejected; implicit selection first
    honors the configured default and then chooses a low-cost model from an
    available provider. Ollama discovery is attempted only when needed.
    """
    requested_model = model or None
    if provider:
        if not requested_model:
            raise ValueError("A model is required when a provider is specified.")
        if not _provider_is_configured(settings, provider):
            raise ValueError(f"Provider {provider!r} is not configured.")
        return requested_model, provider

    if requested_model:
        entry = _find_builtin_model(requested_model)
        if entry:
            resolved_provider = provider_for_model(requested_model)
            if resolved_provider == "ollama":
                return requested_model, resolved_provider
            if _provider_is_configured(settings, resolved_provider):
                return requested_model, resolved_provider
            raise ValueError(
                f"Provider {resolved_provider!r} is not configured for model {requested_model!r}."
            )

        custom_provider = _custom_provider_for_model(settings, requested_model)
        if custom_provider:
            return requested_model, custom_provider

        ollama_models = await _list_ollama_models()
        if requested_model in ollama_models:
            return requested_model, "ollama"
        if settings.openrouter_api_key and "/" in requested_model:
            return requested_model, "openrouter"
        raise ValueError(f"Model {requested_model!r} is not available.")

    default_model = settings.default_model
    default_entry = _find_builtin_model(default_model)
    if default_entry:
        default_provider = provider_for_model(default_model)
        if default_provider != "ollama" and _provider_is_configured(
            settings, default_provider
        ):
            return default_model, default_provider
    else:
        custom_provider = _custom_provider_for_model(settings, default_model)
        if custom_provider:
            return default_model, custom_provider

    capable = preferred_tier in {"capable", "sonnet"}
    candidates = [
        ("sonnet" if capable else "haiku", "anthropic"),
        ("gpt-5.4" if capable else "gpt-5.4-mini", "openai"),
        ("gemini-2.5-pro" if capable else "gemini-2.5-flash", "google"),
        ("openrouter/auto", "openrouter"),
    ]
    for candidate_model, candidate_provider in candidates:
        if _provider_is_configured(settings, candidate_provider):
            return candidate_model, candidate_provider

    for custom in settings.custom_providers:
        if custom.models:
            custom_model = custom.models[0]
            value = custom_model.get("value", custom_model.get("id", ""))
            if value:
                return value, custom.name

    ollama_models = await _list_ollama_models()
    if default_model in ollama_models:
        return default_model, "ollama"
    if ollama_models:
        return ollama_models[0], "ollama"

    raise ValueError(
        "No executable AI model is available. Start Ollama or configure a provider in Settings."
    )


async def generate_auxiliary_text(
    prompt: str,
    *,
    system: str,
    max_tokens: int,
    preferred_tier: str = "fast",
    model: str | None = None,
    provider: str | None = None,
    settings: AppSettings | None = None,
) -> str:
    """Generate plain text through any configured provider adapter."""
    if settings is None:
        from backend.apps.settings.settings import load_settings

        settings = load_settings()

    selected_model, selected_provider = await resolve_auxiliary_model(
        settings,
        preferred_tier=preferred_tier,
        model=model,
        provider=provider,
    )
    adapter = create_provider(selected_provider, settings)
    try:
        response = await adapter.create_message(
            model=selected_model,
            system=system,
            messages=[ProviderMessage(role="user", content=prompt)],
            tools=[],
            max_tokens=max_tokens,
        )
        text = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()
        if not text:
            raise RuntimeError("The selected model returned no text.")
        return text
    finally:
        await adapter.close()
