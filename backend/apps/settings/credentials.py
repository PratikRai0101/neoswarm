"""Centralized credential resolution for LLM API calls.

Supports multiple providers: Anthropic (native), OpenAI, Gemini,
OpenRouter, Ollama (local), and user-configured custom providers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import anthropic
    from backend.apps.settings.models import AppSettings


def validate_credentials(settings: AppSettings, provider: str = "anthropic") -> None:
    """Raise ValueError if credentials are missing for the given provider.

    Supports: Anthropic, OpenAI, Gemini, OpenRouter, Ollama
    """
    p = provider.lower().strip()

    if p == "ollama":
        return

    if p in ("anthropic", "claude"):
        if settings.anthropic_api_key:
            return
        raise ValueError("Anthropic API key not configured. Set it in Settings.")
    elif p == "openai":
        if settings.openai_api_key:
            return
        raise ValueError("OpenAI API key not configured. Set it in Settings.")
    elif p in ("gemini", "google"):
        if getattr(settings, "google_api_key", None):
            return
        raise ValueError("Google API key not configured. Set it in Settings.")
    elif p == "openrouter":
        if getattr(settings, "openrouter_api_key", None):
            return
        raise ValueError("OpenRouter API key not configured. Set it in Settings.")
    elif p in ("xai", "meta", "deepseek", "mistral", "qwen", "cohere"):
        if getattr(settings, "openrouter_api_key", None):
            return
        raise ValueError(f"{provider} requires an OpenRouter API key.")
    else:
        for cp in getattr(settings, "custom_providers", []):
            if cp.name.lower() == p:
                return
        return


def get_provider_credentials(settings: AppSettings, provider: str) -> dict[str, str]:
    """Return credential dict for a specific provider."""
    p = provider.lower().strip()
    validate_credentials(settings, provider)

    if p in ("anthropic", "claude"):
        return {"api_key": settings.anthropic_api_key or ""}

    if p in ("openai", "codex"):
        return {"api_key": settings.openai_api_key or ""}

    if p in ("gemini", "google", "gemini-cli"):
        return {"api_key": getattr(settings, "google_api_key", "") or ""}

    if p == "openrouter":
        return {"api_key": getattr(settings, "openrouter_api_key", "") or ""}

    if p == "ollama":
        return {}

    for cp in getattr(settings, "custom_providers", []):
        if cp.name.lower() == p:
            return {"api_key": cp.api_key, "base_url": cp.base_url}

    raise ValueError(f"No credentials for provider: {provider}")


def get_anthropic_client(settings: AppSettings) -> anthropic.AsyncAnthropic:
    """Return a configured AsyncAnthropic client."""
    import anthropic

    if settings.anthropic_api_key:
        return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    raise ValueError("No AI provider configured. Set an Anthropic API key.")
