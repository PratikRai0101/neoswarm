"""Direct model-provider OAuth: flow states, storage, precedence, redaction.

Network calls are always served by ``httpx.MockTransport`` so these tests never
touch a live provider.
"""

import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from backend.apps.settings import oauth
from backend.apps.settings import settings as settings_api


@pytest.fixture
def isolated_settings(tmp_path, monkeypatch):
    """Point the settings API at a temp dir and a fake in-memory keychain."""
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_api, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings_api, "SETTINGS_FILE", str(settings_file))

    secure: dict[str, str] = {}

    def set_secret(name, value):
        secure[name] = value
        return True

    def get_secret(name):
        return secure.get(name)

    def delete_secret(name):
        secure.pop(name, None)
        return True

    monkeypatch.setattr(settings_api, "set_secret", set_secret)
    monkeypatch.setattr(settings_api, "get_secret", get_secret)
    monkeypatch.setattr(settings_api, "delete_secret", delete_secret)

    # Every test gets a fresh in-flight flow store.
    monkeypatch.setattr(settings_api, "_oauth_manager", oauth.OAuthFlowManager())
    return {"file": settings_file, "secure": secure}


def _openai_transport(*, poll_pending_times: int = 0):
    """Mock transport for the OpenAI device-code exchange."""
    calls = {"poll": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/deviceauth/usercode"):
            return httpx.Response(
                200,
                json={
                    "user_code": "ABCD-1234",
                    "device_auth_id": "device-1",
                    "interval": 1,
                    "expires_in": 600,
                },
            )
        if url.endswith("/deviceauth/token"):
            calls["poll"] += 1
            if calls["poll"] <= poll_pending_times:
                return httpx.Response(403, json={"error": "authorization_pending"})
            return httpx.Response(
                200,
                json={"authorization_code": "auth-code", "code_verifier": "verifier-1"},
            )
        if url.endswith("/oauth/token"):
            return httpx.Response(
                200,
                json={
                    "access_token": "openai-access-token",
                    "refresh_token": "openai-refresh-token",
                    "expires_in": 3600,
                    "email": "person@example.com",
                },
            )
        raise AssertionError(f"unexpected request: {url}")

    return httpx.MockTransport(handler), calls


def _anthropic_transport():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content.decode())
        seen["content_type"] = request.headers.get("content-type", "")
        return httpx.Response(
            200,
            json={
                "access_token": "anthropic-access-token",
                "refresh_token": "anthropic-refresh-token",
                "expires_in": 3600,
            },
        )

    return httpx.MockTransport(handler), seen


# ---------------------------------------------------------------------------
# Flow state transitions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_device_code_flow_transitions_pending_to_connected():
    transport, calls = _openai_transport(poll_pending_times=1)
    manager = oauth.OAuthFlowManager(transport=transport)

    started = await manager.start("openai")
    assert started.state == oauth.OAuthState.PENDING.value
    assert started.flow == "device_code"
    assert started.user_code == "ABCD-1234"
    assert started.verification_uri == "https://auth.openai.com/codex/device"
    assert started.tokens is None
    assert "access_token" not in json.dumps(started.public())

    still_pending = await manager.poll("openai")
    assert still_pending.state == oauth.OAuthState.PENDING.value
    assert calls["poll"] == 1

    connected = await manager.poll("openai")
    assert connected.state == oauth.OAuthState.CONNECTED.value
    assert connected.tokens["access_token"] == "openai-access-token"
    assert connected.tokens["refresh_token"] == "openai-refresh-token"
    assert connected.account == "person@example.com"
    assert manager.status("openai").state == oauth.OAuthState.CONNECTED.value


@pytest.mark.asyncio
async def test_device_code_flow_expires_after_provider_ttl():
    now = {"value": 1000.0}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "user_code": "EXPIRE-1",
                "device_auth_id": "device-2",
                "interval": 5,
                "expires_in": 10,
            },
        )

    manager = oauth.OAuthFlowManager(
        transport=httpx.MockTransport(handler), clock=lambda: now["value"]
    )
    started = await manager.start("openai")
    assert started.state == oauth.OAuthState.PENDING.value

    now["value"] = 1011.0
    expired = await manager.poll("openai")
    assert expired.state == oauth.OAuthState.EXPIRED.value
    assert manager.status("openai").state == oauth.OAuthState.EXPIRED.value


@pytest.mark.asyncio
async def test_device_code_flow_failure_is_reported_without_tokens():
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith("/deviceauth/usercode"):
            return httpx.Response(
                200, json={"user_code": "FAIL-1", "device_auth_id": "device-3"}
            )
        return httpx.Response(400, json={"error": "access_denied"})

    manager = oauth.OAuthFlowManager(transport=httpx.MockTransport(handler))
    await manager.start("openai")
    failed = await manager.poll("openai")
    assert failed.state == oauth.OAuthState.FAILED.value
    assert failed.error == "access_denied"
    assert "access_token" not in json.dumps(failed.public())


@pytest.mark.asyncio
async def test_browser_pkce_start_and_complete():
    transport, seen = _anthropic_transport()
    manager = oauth.OAuthFlowManager(transport=transport)

    started = await manager.start("anthropic")
    assert started.state == oauth.OAuthState.PENDING.value
    assert started.flow == "browser_pkce"
    assert started.auth_url is not None
    assert started.tokens is None

    params = parse_qs(urlparse(started.auth_url).query)
    assert params["code_challenge_method"] == ["S256"]
    assert params["client_id"] == [oauth.ANTHROPIC_CLIENT_ID]
    assert "code_challenge" in params
    state_value = params["state"][0]

    # Anthropic's callback page shows "<code>#<state>".
    connected = await manager.complete("anthropic", f"the-code#{state_value}")
    assert connected.state == oauth.OAuthState.CONNECTED.value
    assert connected.tokens["access_token"] == "anthropic-access-token"
    assert seen["body"]["grant_type"] == "authorization_code"
    assert seen["body"]["code"] == "the-code"
    assert seen["body"]["state"] == state_value
    assert "json" in seen["content_type"]


@pytest.mark.asyncio
async def test_complete_without_started_flow_fails():
    manager = oauth.OAuthFlowManager()
    result = await manager.complete("anthropic", "anything")
    assert result.state == oauth.OAuthState.FAILED.value
    assert result.tokens is None


def test_unsupported_provider_is_rejected():
    manager = oauth.OAuthFlowManager()
    assert manager.supports("anthropic")
    assert manager.supports("openai")
    assert not manager.supports("google")
    with pytest.raises(ValueError):
        manager.status("google")


# ---------------------------------------------------------------------------
# Storage through secret_store
# ---------------------------------------------------------------------------


def test_oauth_tokens_persist_through_secret_store(isolated_settings):
    settings_api._persist_oauth_tokens(
        "anthropic",
        {
            "access_token": "sk-ant-oat-1",
            "refresh_token": "refresh-1",
            "expires_at": 123.0,
            "account": "me@example.com",
        },
    )

    secure = isolated_settings["secure"]
    assert secure["anthropic_oauth_token"] == "sk-ant-oat-1"
    assert secure["anthropic_oauth_refresh_token"] == "refresh-1"

    persisted = json.loads(isolated_settings["file"].read_text())
    assert persisted["anthropic_oauth_token"] is None
    assert persisted["anthropic_oauth_refresh_token"] is None
    assert persisted["anthropic_oauth_account"] == "me@example.com"

    effective = settings_api.load_settings()
    assert effective.anthropic_oauth_token == "sk-ant-oat-1"
    assert effective.anthropic_oauth_refresh_token == "refresh-1"


@pytest.mark.asyncio
async def test_oauth_route_flow_persists_tokens_and_disconnects(isolated_settings):
    transport, _ = _openai_transport()
    settings_api._oauth_manager = oauth.OAuthFlowManager(transport=transport)

    started = await settings_api.oauth_start("openai")
    assert started["state"] == "pending"
    assert "access_token" not in json.dumps(started)

    connected = await settings_api.oauth_poll("openai")
    assert connected["state"] == "connected"
    assert "openai-access-token" not in json.dumps(connected)

    secure = isolated_settings["secure"]
    assert secure["openai_oauth_token"] == "openai-access-token"
    assert settings_api.load_settings().openai_oauth_token == "openai-access-token"

    removed = await settings_api.oauth_disconnect("openai")
    assert removed["state"] == "disconnected"
    assert "openai_oauth_token" not in secure
    assert settings_api.load_settings().openai_oauth_token is None


# ---------------------------------------------------------------------------
# Precedence ordering
# ---------------------------------------------------------------------------


def test_oauth_token_environment_wins_over_keychain(isolated_settings, monkeypatch):
    settings_api._persist_oauth_tokens("openai", {"access_token": "stored-oauth"})
    assert settings_api.load_settings().openai_oauth_token == "stored-oauth"

    monkeypatch.setenv("OPENAI_OAUTH_TOKEN", "environment-oauth")
    effective = settings_api.load_settings()
    assert effective.openai_oauth_token == "environment-oauth"

    # The environment value is runtime-only and must not replace storage.
    persisted = json.loads(isolated_settings["file"].read_text())
    assert persisted["openai_oauth_token"] is None
    assert isolated_settings["secure"]["openai_oauth_token"] == "stored-oauth"


def test_credentials_resolution_includes_oauth_tokens():
    from backend.apps.settings.credentials import (
        get_provider_credentials,
        resolve_credential,
        validate_credentials,
    )
    from backend.apps.settings.models import AppSettings

    validate_credentials(AppSettings(anthropic_oauth_token="oauth-1"), "anthropic")
    resolved = get_provider_credentials(
        AppSettings(anthropic_oauth_token="oauth-1"), "anthropic"
    )
    assert resolved["auth_token"] == "oauth-1"
    assert resolved["credential_type"] == "oauth"

    api_key_first = get_provider_credentials(
        AppSettings(anthropic_api_key="api-1", anthropic_oauth_token="oauth-1"),
        "anthropic",
    )
    assert api_key_first["api_key"] == "api-1"
    assert api_key_first["credential_type"] == "api_key"

    validate_credentials(AppSettings(openai_oauth_token="oauth-2"), "openai")
    assert resolve_credential(AppSettings(openai_oauth_token="oauth-2"), "openai") == (
        "oauth",
        "oauth-2",
    )

    with pytest.raises(ValueError):
        validate_credentials(AppSettings(), "anthropic")


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oauth_tokens_are_redacted_in_public_settings(isolated_settings):
    settings_api._persist_oauth_tokens(
        "anthropic", {"access_token": "sk-ant-oat-secret", "refresh_token": "refresh-secret"}
    )

    public = await settings_api.get_settings()

    assert public["anthropic_oauth_token"] == settings_api.SECRET_UNCHANGED
    assert public["anthropic_oauth_refresh_token"] == settings_api.SECRET_UNCHANGED
    assert "sk-ant-oat-secret" not in json.dumps(public)
    assert "refresh-secret" not in json.dumps(public)


@pytest.mark.asyncio
async def test_oauth_status_payload_never_contains_token_material(isolated_settings):
    settings_api._persist_oauth_tokens(
        "openai", {"access_token": "openai-secret-token", "refresh_token": "refresh-secret"}
    )

    overview = await settings_api.oauth_overview()
    serialized = json.dumps(overview)

    assert "openai-secret-token" not in serialized
    assert "refresh-secret" not in serialized
    openai_entry = next(
        entry for entry in overview["providers"] if entry["provider"] == "openai"
    )
    assert openai_entry["state"] == "connected"


@pytest.mark.asyncio
async def test_oauth_overview_reports_pending_then_expired(isolated_settings):
    transport, _ = _openai_transport()
    settings_api._oauth_manager = oauth.OAuthFlowManager(transport=transport)

    started = await settings_api.oauth_start("openai")
    assert started["state"] == "pending"

    pending_entry = await settings_api.oauth_status("openai")
    assert pending_entry["state"] == "pending"
    assert pending_entry["user_code"] == "ABCD-1234"

    # A stored token whose expiry has passed is reported as expired.
    settings_api._persist_oauth_tokens(
        "openai", {"access_token": "stale-token", "expires_at": 1.0}
    )
    settings_api._oauth_manager.cancel("openai")
    expired_entry = await settings_api.oauth_status("openai")
    assert expired_entry["state"] == "expired"
    assert "stale-token" not in json.dumps(expired_entry)
