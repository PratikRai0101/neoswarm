"""Centralized credential resolution for LLM API calls.

Supports multiple providers: Anthropic (native), OpenAI, Gemini,
OpenRouter, Ollama (local), and user-configured custom providers.

Credentials are resolved environment-first, then from the platform keychain /
owner-only settings file, then left unset. OAuth tokens acquired through
:mod:`backend.apps.settings.oauth` participate in the same order: the settings
loader overlays them exactly like API keys, and the helpers here decide which
credential type is effective for a provider.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from backend.apps.settings.oauth import OAUTH_PROVIDERS

if TYPE_CHECKING:
    from backend.apps.settings.models import AppSettings

# Map model-family aliases onto the canonical OAuth provider names.
_OAUTH_PROVIDER_ALIASES = {"claude": "anthropic", "codex": "openai"}


def _oauth_field(provider: str) -> str | None:
    name = _OAUTH_PROVIDER_ALIASES.get(provider, provider)
    config = OAUTH_PROVIDERS.get(name)
    return config.access_token_field if config else None


def oauth_token(settings: AppSettings, provider: str) -> str | None:
    """Return an OAuth-acquired access token for a provider, if configured."""
    field = _oauth_field(provider.lower().strip())
    if not field:
        return None
    return getattr(settings, field, None) or None


def resolve_credential(settings: AppSettings, provider: str) -> tuple[str, str] | None:
    """Return ``(credential_type, value)`` for a provider without raising.

    ``credential_type`` is one of ``api_key``, ``oauth`` or ``subscription_token``.
    Returns ``None`` when the provider has no usable credential.
    """
    p = provider.lower().strip()

    if p in ("anthropic", "claude"):
        if settings.anthropic_api_key:
            return ("api_key", settings.anthropic_api_key)
        token = oauth_token(settings, "anthropic")
        if token:
            return ("oauth", token)
        subscription = getattr(settings, "claude_subscription_token", None)
        if subscription:
            return ("subscription_token", subscription)
        return None

    if p in ("openai", "codex"):
        if settings.openai_api_key:
            return ("api_key", settings.openai_api_key)
        token = oauth_token(settings, "openai")
        if token:
            return ("oauth", token)
        subscription = getattr(settings, "openai_subscription_token", None)
        if subscription:
            return ("subscription_token", subscription)
        return None

    if p in ("gemini", "google"):
        if getattr(settings, "google_api_key", None):
            return ("api_key", settings.google_api_key)
        return None

    if p == "openrouter":
        if getattr(settings, "openrouter_api_key", None):
            return ("api_key", settings.openrouter_api_key)
        return None

    if p == "ollama":
        return ("none", "")

    return None


def validate_credentials(settings: AppSettings, provider: str = "anthropic") -> None:
    """Raise ValueError if credentials are missing for the given provider.

    Supports: Anthropic, OpenAI, Gemini, OpenRouter, Ollama
    """
    p = provider.lower().strip()

    if p == "ollama":
        return

    if p in ("anthropic", "claude"):
        if resolve_credential(settings, "anthropic") is not None:
            return
        raise ValueError(
            "Anthropic credentials not configured. Add an API key or connect OAuth in Settings."
        )
    elif p == "openai":
        if resolve_credential(settings, "openai") is not None:
            return
        raise ValueError(
            "OpenAI credentials not configured. Add an API key or connect OAuth in Settings."
        )
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
    """Return the effective credential dict for a specific provider.

    The dict carries a ``credential_type`` marker so callers can pick the right
    transport (``api_key`` vs bearer ``auth_token``) without re-implementing the
    resolution order.
    """
    p = provider.lower().strip()
    validate_credentials(settings, provider)

    if p in ("anthropic", "claude"):
        resolved = resolve_credential(settings, "anthropic")
        if resolved:
            return _credential_dict(resolved)
        return {"api_key": settings.anthropic_api_key or ""}

    if p in ("openai", "codex"):
        resolved = resolve_credential(settings, "openai")
        if resolved:
            return _credential_dict(resolved)
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


def _credential_dict(resolved: tuple[str, str]) -> dict[str, str]:
    credential_type, value = resolved
    if credential_type == "api_key":
        return {"api_key": value, "credential_type": "api_key"}
    if credential_type == "oauth":
        return {"auth_token": value, "credential_type": "oauth"}
    return {"auth_token": value, "credential_type": "subscription_token"}
