"""Direct model-provider OAuth acquisition for Anthropic and OpenAI.

Two flow shapes are supported, mirroring the patterns already used in the tree
for GitHub Copilot (device code) and the tools library OAuth providers
(browser PKCE):

* ``device_code`` — request a user code, poll until the user approves, then
  exchange the returned authorization code for tokens (OpenAI / Codex).
* ``browser_pkce`` — build an authorization URL with an S256 PKCE challenge and
  exchange the authorization code the user pastes back (Anthropic / Claude).

This module is deliberately storage-agnostic: :class:`OAuthFlowManager` returns
tokens to its caller and never touches the keychain or settings file. The
settings layer owns persistence so acquired tokens flow through the existing
``secret_store`` and the normal environment > keychain > settings > defaults
resolution order. Tokens are only ever exposed through
:attr:`OAuthResult.tokens`; :meth:`OAuthResult.public` is the redacted shape
intended for CLI/API status output.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Mapping
from urllib.parse import urlencode

import httpx


class OAuthState(str, Enum):
    """Lifecycle of a provider OAuth connection."""

    DISCONNECTED = "disconnected"
    PENDING = "pending"
    CONNECTED = "connected"
    EXPIRED = "expired"
    FAILED = "failed"


# Public OAuth client identifiers. These are not secrets: they are the client
# IDs shipped by the official Claude Code and Codex CLI clients, which is what
# the respective providers authorize today.
ANTHROPIC_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
OPENAI_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"

# Default pending-flow lifetime. Providers may shorten it via ``expires_in``.
DEFAULT_FLOW_TTL_SECONDS = 900.0
DEFAULT_POLL_INTERVAL_SECONDS = 5.0
MAX_POLL_INTERVAL_SECONDS = 30.0


@dataclass(frozen=True)
class OAuthProviderConfig:
    """Static description of one provider's OAuth acquisition path."""

    name: str
    flow: str  # "device_code" | "browser_pkce"
    client_id: str
    scopes: str = ""
    token_url: str = ""
    token_request_style: str = "form"  # "form" | "json"
    # device-code flow
    device_code_url: str = ""
    device_token_url: str = ""
    verification_uri: str = ""
    # browser PKCE flow
    authorize_url: str = ""
    redirect_uri: str = ""
    # Persistence field names. Declared here so the settings layer and the
    # credential resolver agree on where tokens are read and written.
    access_token_field: str = ""
    refresh_token_field: str = ""
    expires_at_field: str = ""
    account_field: str = ""


OAUTH_PROVIDERS: dict[str, OAuthProviderConfig] = {
    "anthropic": OAuthProviderConfig(
        name="anthropic",
        flow="browser_pkce",
        client_id=ANTHROPIC_CLIENT_ID,
        scopes="user:profile user:inference",
        authorize_url="https://claude.ai/oauth/authorize",
        token_url="https://console.anthropic.com/v1/oauth/token",
        token_request_style="json",
        redirect_uri="https://console.anthropic.com/oauth/code/callback",
        access_token_field="anthropic_oauth_token",
        refresh_token_field="anthropic_oauth_refresh_token",
        expires_at_field="anthropic_oauth_expires_at",
        account_field="anthropic_oauth_account",
    ),
    "openai": OAuthProviderConfig(
        name="openai",
        flow="device_code",
        client_id=OPENAI_CLIENT_ID,
        device_code_url="https://auth.openai.com/api/accounts/deviceauth/usercode",
        device_token_url="https://auth.openai.com/api/accounts/deviceauth/token",
        token_url="https://auth.openai.com/oauth/token",
        token_request_style="form",
        verification_uri="https://auth.openai.com/codex/device",
        redirect_uri="https://auth.openai.com/deviceauth/callback",
        access_token_field="openai_oauth_token",
        refresh_token_field="openai_oauth_refresh_token",
        expires_at_field="openai_oauth_expires_at",
        account_field="openai_oauth_account",
    ),
}

# Common aliases so callers can use the model-family name they already know.
_PROVIDER_ALIASES = {"claude": "anthropic", "codex": "openai"}


@dataclass
class OAuthResult:
    """One observation of an OAuth flow's state.

    ``tokens`` carries secret material and must never be serialized into a
    status payload. Use :meth:`public` for anything user-facing.
    """

    provider: str
    state: str
    flow: str
    user_code: str | None = None
    verification_uri: str | None = None
    auth_url: str | None = None
    interval: float | None = None
    expires_at: float | None = None
    account: str | None = None
    error: str | None = None
    tokens: dict[str, Any] | None = field(default=None, repr=False)

    def public(self) -> dict[str, Any]:
        """Return a status payload that never contains token material."""
        payload: dict[str, Any] = {
            "provider": self.provider,
            "state": self.state,
            "flow": self.flow,
        }
        for key in (
            "user_code",
            "verification_uri",
            "auth_url",
            "interval",
            "expires_at",
            "account",
            "error",
        ):
            value = getattr(self, key)
            if value is not None:
                payload[key] = value
        return payload


@dataclass
class _PendingFlow:
    provider: str
    flow: str
    device_ref: str | None = None
    user_code: str | None = None
    verification_uri: str | None = None
    auth_url: str | None = None
    code_verifier: str | None = None
    state_value: str | None = None
    interval: float = DEFAULT_POLL_INTERVAL_SECONDS
    expires_at: float = 0.0


def _pkce_pair() -> tuple[str, str]:
    """Return an S256 ``(code_verifier, code_challenge)`` pair."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _safe_json(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _short_error(data: Mapping[str, Any], fallback: str) -> str:
    """Extract a provider error code without echoing raw response bodies."""
    for key in ("error", "detail", "message", "error_description"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value[:200]
    return fallback


def _account_from_id_token(id_token: str) -> str | None:
    """Best-effort, unverified read of an identity-claim label from a JWT.

    This is only used to show *which* account is connected; the token value is
    never logged or persisted.
    """
    try:
        parts = id_token.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1]
        padded = payload + "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded))
    except Exception:
        return None
    if not isinstance(claims, dict):
        return None
    for key in ("email", "preferred_username", "name"):
        value = claims.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _parse_tokens(payload: Mapping[str, Any], now: float) -> dict[str, Any]:
    """Normalize a token response, raising when no access token is present."""
    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise ValueError("token response did not include an access_token")

    tokens: dict[str, Any] = {"access_token": access_token}

    refresh_token = payload.get("refresh_token")
    if isinstance(refresh_token, str) and refresh_token:
        tokens["refresh_token"] = refresh_token

    if payload.get("expires_in") is not None:
        tokens["expires_at"] = now + _coerce_float(payload.get("expires_in"), 0.0)

    account = payload.get("account") or payload.get("email")
    if not isinstance(account, str) or not account:
        id_token = payload.get("id_token")
        account = _account_from_id_token(id_token) if isinstance(id_token, str) else None
    if isinstance(account, str) and account:
        tokens["account"] = account

    return tokens


class OAuthFlowManager:
    """Drive provider OAuth flows from start to token acquisition.

    The manager only holds in-flight flow state. Whether a provider is
    *connected* is derived by the settings layer from persisted credentials, so
    a fresh process still reports the right state.
    """

    def __init__(
        self,
        providers: Mapping[str, OAuthProviderConfig] | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.providers = dict(providers or OAUTH_PROVIDERS)
        self._transport = transport
        self._clock = clock
        self._pending: dict[str, _PendingFlow] = {}
        self._last: dict[str, OAuthResult] = {}

    # -- helpers ----------------------------------------------------------

    def _normalize(self, provider: str) -> str:
        name = (provider or "").strip().lower()
        return _PROVIDER_ALIASES.get(name, name)

    def _config(self, provider: str) -> OAuthProviderConfig:
        name = self._normalize(provider)
        config = self.providers.get(name)
        if config is None:
            raise ValueError(f"OAuth is not supported for provider: {provider}")
        return config

    def _client(self) -> httpx.AsyncClient:
        kwargs: dict[str, Any] = {"timeout": 30.0}
        if self._transport is not None:
            kwargs["transport"] = self._transport
        return httpx.AsyncClient(**kwargs)

    def _failed(self, config: OAuthProviderConfig, message: str) -> OAuthResult:
        result = OAuthResult(
            provider=config.name,
            state=OAuthState.FAILED.value,
            flow=config.flow,
            error=message,
        )
        self._last[config.name] = result
        return result

    def _connected(self, config: OAuthProviderConfig, tokens: dict[str, Any]) -> OAuthResult:
        self._pending.pop(config.name, None)
        result = OAuthResult(
            provider=config.name,
            state=OAuthState.CONNECTED.value,
            flow=config.flow,
            account=tokens.get("account"),
            expires_at=tokens.get("expires_at"),
            tokens=tokens,
        )
        self._last[config.name] = result
        return result

    def _expired(self, config: OAuthProviderConfig, pending: _PendingFlow) -> OAuthResult:
        self._pending.pop(config.name, None)
        result = OAuthResult(
            provider=config.name,
            state=OAuthState.EXPIRED.value,
            flow=config.flow,
            expires_at=pending.expires_at,
            error="authorization request expired",
        )
        self._last[config.name] = result
        return result

    # -- public API -------------------------------------------------------

    def supports(self, provider: str) -> bool:
        return self._normalize(provider) in self.providers

    def status(self, provider: str) -> OAuthResult:
        """Return in-flight state, falling back to the last observed result."""
        config = self._config(provider)
        pending = self._pending.get(config.name)
        if pending is not None:
            if self._clock() >= pending.expires_at:
                return self._expired(config, pending)
            return OAuthResult(
                provider=config.name,
                state=OAuthState.PENDING.value,
                flow=config.flow,
                user_code=pending.user_code,
                verification_uri=pending.verification_uri,
                auth_url=pending.auth_url,
                interval=pending.interval,
                expires_at=pending.expires_at,
            )
        return self._last.get(config.name) or OAuthResult(
            provider=config.name,
            state=OAuthState.DISCONNECTED.value,
            flow=config.flow,
        )

    def cancel(self, provider: str) -> OAuthResult:
        """Drop any in-flight flow and forget the last result."""
        config = self._config(provider)
        self._pending.pop(config.name, None)
        self._last.pop(config.name, None)
        return OAuthResult(
            provider=config.name,
            state=OAuthState.DISCONNECTED.value,
            flow=config.flow,
        )

    async def start(self, provider: str) -> OAuthResult:
        """Begin an OAuth flow and return the user-facing instructions."""
        config = self._config(provider)
        self._pending.pop(config.name, None)
        if config.flow == "device_code":
            return await self._start_device_code(config)
        return self._start_browser_pkce(config)

    async def poll(self, provider: str) -> OAuthResult:
        """Advance a device-code flow by one polling attempt."""
        config = self._config(provider)
        pending = self._pending.get(config.name)
        if pending is None:
            return self._last.get(config.name) or OAuthResult(
                provider=config.name,
                state=OAuthState.DISCONNECTED.value,
                flow=config.flow,
            )
        if self._clock() >= pending.expires_at:
            return self._expired(config, pending)
        if pending.flow != "device_code":
            return OAuthResult(
                provider=config.name,
                state=OAuthState.PENDING.value,
                flow=config.flow,
                auth_url=pending.auth_url,
                expires_at=pending.expires_at,
            )

        try:
            async with self._client() as client:
                response = await client.post(
                    config.device_token_url,
                    json={
                        "device_auth_id": pending.device_ref,
                        "user_code": pending.user_code,
                    },
                )
        except httpx.HTTPError:
            return OAuthResult(
                provider=config.name,
                state=OAuthState.PENDING.value,
                flow=config.flow,
                user_code=pending.user_code,
                verification_uri=pending.verification_uri,
                interval=pending.interval,
                expires_at=pending.expires_at,
            )

        if response.status_code in (403, 404, 428):
            return OAuthResult(
                provider=config.name,
                state=OAuthState.PENDING.value,
                flow=config.flow,
                user_code=pending.user_code,
                verification_uri=pending.verification_uri,
                interval=pending.interval,
                expires_at=pending.expires_at,
            )

        if response.status_code == 429:
            pending.interval = min(pending.interval * 1.5, MAX_POLL_INTERVAL_SECONDS)
            return OAuthResult(
                provider=config.name,
                state=OAuthState.PENDING.value,
                flow=config.flow,
                user_code=pending.user_code,
                verification_uri=pending.verification_uri,
                interval=pending.interval,
                expires_at=pending.expires_at,
            )

        if response.status_code >= 400:
            data = _safe_json(response)
            return self._failed(
                config,
                _short_error(data, f"device authorization failed ({response.status_code})"),
            )

        data = _safe_json(response)
        code = data.get("authorization_code")
        if not isinstance(code, str) or not code:
            return self._failed(config, "device authorization response was incomplete")
        verifier = data.get("code_verifier")

        tokens = await self._exchange_code(
            config,
            code,
            verifier=verifier if isinstance(verifier, str) else None,
        )
        if tokens is None:
            return self._failed(config, "token exchange failed")
        return self._connected(config, tokens)

    async def complete(self, provider: str, code: str) -> OAuthResult:
        """Finish a browser-PKCE flow with the authorization code."""
        config = self._config(provider)
        pending = self._pending.get(config.name)
        if pending is None or pending.flow != "browser_pkce":
            return self._failed(config, "no browser OAuth flow is in progress")
        if self._clock() >= pending.expires_at:
            return self._expired(config, pending)

        raw = (code or "").strip()
        if not raw:
            return OAuthResult(
                provider=config.name,
                state=OAuthState.PENDING.value,
                flow=config.flow,
                auth_url=pending.auth_url,
                error="authorization code is required",
            )

        state = pending.state_value
        # Anthropic's callback page shows "<code>#<state>"; accept both forms.
        if "#" in raw:
            code_part, _, returned_state = raw.partition("#")
            raw = code_part.strip()
            state = returned_state.strip() or state

        tokens = await self._exchange_code(
            config,
            raw,
            verifier=pending.code_verifier,
            state=state,
        )
        if tokens is None:
            return self._failed(config, "token exchange failed")
        return self._connected(config, tokens)

    # -- flow implementations --------------------------------------------

    async def _start_device_code(self, config: OAuthProviderConfig) -> OAuthResult:
        try:
            async with self._client() as client:
                response = await client.post(
                    config.device_code_url,
                    json={"client_id": config.client_id},
                )
        except httpx.HTTPError as exc:
            return self._failed(config, f"device authorization request failed: {type(exc).__name__}")

        if response.status_code >= 400:
            return self._failed(
                config,
                f"device authorization request failed ({response.status_code})",
            )

        data = _safe_json(response)
        user_code = data.get("user_code")
        device_ref = data.get("device_auth_id") or data.get("device_code")
        if not isinstance(user_code, str) or not user_code or not device_ref:
            return self._failed(config, "device authorization response was incomplete")

        interval = max(_coerce_float(data.get("interval"), DEFAULT_POLL_INTERVAL_SECONDS), 0.5)
        expires_in = _coerce_float(data.get("expires_in"), DEFAULT_FLOW_TTL_SECONDS)
        verification_uri = data.get("verification_uri") or config.verification_uri or None
        pending = _PendingFlow(
            provider=config.name,
            flow=config.flow,
            device_ref=str(device_ref),
            user_code=user_code,
            verification_uri=verification_uri,
            interval=interval,
            expires_at=self._clock() + expires_in,
        )
        self._pending[config.name] = pending
        return OAuthResult(
            provider=config.name,
            state=OAuthState.PENDING.value,
            flow=config.flow,
            user_code=user_code,
            verification_uri=verification_uri,
            interval=interval,
            expires_at=pending.expires_at,
        )

    def _start_browser_pkce(self, config: OAuthProviderConfig) -> OAuthResult:
        verifier, challenge = _pkce_pair()
        state_value = secrets.token_urlsafe(24)
        params = {
            "code": "true",
            "client_id": config.client_id,
            "response_type": "code",
            "redirect_uri": config.redirect_uri,
            "scope": config.scopes,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state_value,
        }
        auth_url = f"{config.authorize_url}?{urlencode(params)}"
        pending = _PendingFlow(
            provider=config.name,
            flow=config.flow,
            auth_url=auth_url,
            code_verifier=verifier,
            state_value=state_value,
            expires_at=self._clock() + DEFAULT_FLOW_TTL_SECONDS,
        )
        self._pending[config.name] = pending
        return OAuthResult(
            provider=config.name,
            state=OAuthState.PENDING.value,
            flow=config.flow,
            auth_url=auth_url,
            expires_at=pending.expires_at,
        )

    async def _exchange_code(
        self,
        config: OAuthProviderConfig,
        code: str,
        *,
        verifier: str | None = None,
        state: str | None = None,
    ) -> dict[str, Any] | None:
        payload: dict[str, Any] = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": config.client_id,
            "redirect_uri": config.redirect_uri,
        }
        if verifier:
            payload["code_verifier"] = verifier
        if state:
            payload["state"] = state

        try:
            async with self._client() as client:
                if config.token_request_style == "json":
                    response = await client.post(config.token_url, json=payload)
                else:
                    response = await client.post(config.token_url, data=payload)
        except httpx.HTTPError:
            return None

        if response.status_code >= 400:
            return None
        try:
            return _parse_tokens(_safe_json(response), self._clock())
        except ValueError:
            return None


__all__ = [
    "OAuthFlowManager",
    "OAuthProviderConfig",
    "OAuthResult",
    "OAuthState",
    "OAUTH_PROVIDERS",
    "ANTHROPIC_CLIENT_ID",
    "OPENAI_CLIENT_ID",
]
