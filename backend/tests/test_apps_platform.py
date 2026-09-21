"""Phase C (upstream port): apps platform — identity, grants, host SDK."""

import asyncio
import json

import pytest
from fastapi import HTTPException
from types import SimpleNamespace

from backend.apps.applications import grants, identity
from backend.apps.applications.apps import (
    ToolCallRequest,
    resolve_app_from_referer,
    tools_call,
)


@pytest.fixture
def isolated_stores(tmp_path, monkeypatch):
    monkeypatch.setattr(identity, "APPS_DIR", str(tmp_path))
    monkeypatch.setattr(identity, "APP_TOKENS_FILE", str(tmp_path / "app_tokens.json"))
    monkeypatch.setattr(grants, "APPS_DIR", str(tmp_path))
    monkeypatch.setattr(grants, "GRANTS_FILE", str(tmp_path / "app_tool_grants.json"))
    return tmp_path


def test_identity_mint_is_stable_and_revokable(isolated_stores):
    first = identity.mint_app_token("app-1")
    assert identity.mint_app_token("app-1") == first
    assert identity.resolve_app_token(first) == "app-1"
    assert identity.resolve_app_token("") is None
    assert identity.resolve_app_token("nope") is None

    other = identity.mint_app_token("app-2")
    assert other != first
    assert identity.revoke_app_token("app-1") is True
    assert identity.resolve_app_token(first) is None
    assert identity.resolve_app_token(other) == "app-2"
    assert identity.revoke_app_token("app-1") is False


def test_identity_damaged_store_resets_to_empty(isolated_stores):
    (isolated_stores / "app_tokens.json").write_text("{ broken")
    assert identity.mint_app_token("app-1")  # does not raise


def test_grants_remember_and_reset(isolated_stores):
    assert grants.grant_status("app-1", "t:X") is None
    grants.set_grant("app-1", "t:X", "granted")
    assert grants.grant_status("app-1", "t:X") == "granted"
    assert grants.list_grants("app-1") == {"t:X": "granted"}
    assert grants.clear_grants("app-1") is True
    assert grants.grant_status("app-1", "t:X") is None
    assert grants.clear_grants("app-1") is False


def test_resolve_unknown_grant_is_false():
    assert grants.resolve_grant("missing", True, False) is False


@pytest.mark.asyncio
async def test_grant_timeout_reads_as_deny(isolated_stores, monkeypatch):
    monkeypatch.setattr(grants, "GRANT_WAIT_SECONDS", 0.05)
    assert await grants.request_grant("app-1", "App", "t:X", "X", "{}") is False
    # Timeout never remembers.
    assert grants.grant_status("app-1", "t:X") is None


@pytest.mark.asyncio
async def test_grant_allow_with_remember(isolated_stores, monkeypatch):
    monkeypatch.setattr(grants, "GRANT_WAIT_SECONDS", 5.0)
    seen = {}

    from backend.apps.agents import ws_manager as ws_module

    async def fake_broadcast(event, data):
        seen.update(data)

    monkeypatch.setattr(ws_module.ws_manager, "broadcast_global", fake_broadcast)

    async def _resolve():
        for _ in range(100):
            await asyncio.sleep(0.01)
            if seen.get("request_id"):
                break
        assert grants.resolve_grant(seen["request_id"], True, True) is True

    allowed, _ = await asyncio.gather(
        grants.request_grant("app-1", "App", "t:X", "X", '{"a": 1}'),
        _resolve(),
    )
    assert allowed is True
    assert grants.grant_status("app-1", "t:X") == "granted"


def test_referer_identifies_served_apps():
    assert (
        resolve_app_from_referer("http://127.0.0.1:8324/api/outputs/abc123/serve/index.html")
        == "abc123"
    )
    assert (
        resolve_app_from_referer("http://127.0.0.1:8324/api/outputs/workspace/my-app/serve/index.html")
        == "my-app"
    )
    assert resolve_app_from_referer("http://127.0.0.1:8324/") is None
    assert resolve_app_from_referer("") is None


def _request(headers=None):
    return SimpleNamespace(headers=headers or {})


@pytest.mark.asyncio
async def test_tools_call_rejects_unidentified_apps():
    with pytest.raises(HTTPException) as excinfo:
        await tools_call(ToolCallRequest(tool="tool-id:X", args={}), _request())
    assert excinfo.value.status_code == 403


@pytest.mark.asyncio
async def test_tools_call_rejects_bad_tool_shape(isolated_stores):
    token = identity.mint_app_token("app-1")
    with pytest.raises(HTTPException) as excinfo:
        await tools_call(
            ToolCallRequest(app_token=token, tool="no-separator", args={}),
            _request(),
        )
    assert excinfo.value.status_code == 422


@pytest.mark.asyncio
async def test_tools_call_enforces_remembered_deny(isolated_stores):
    token = identity.mint_app_token("app-1")
    grants.set_grant("app-1", "tool-id:X", "denied")
    with pytest.raises(HTTPException) as excinfo:
        await tools_call(
            ToolCallRequest(app_token=token, tool="tool-id:X", args={}),
            _request(),
        )
    assert excinfo.value.status_code == 403


def test_view_client_injection_carries_token():
    from backend.apps.outputs.outputs import _build_data_injection, _inject_data_into_html

    script = _build_data_injection("{}", "null", "tok-123")
    assert "window.NeoSwarm" in script
    assert "tok-123" in script
    assert "/api/apps" in script

    page = _inject_data_into_html("<html><head></head><body></body></html>", "{}", "null", "tok-123")
    assert "window.NeoSwarm" in page
    # Token is JSON-encoded, never raw-interpolated.
    assert json.dumps("tok-123") in page
