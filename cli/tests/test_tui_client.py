"""Contract tests for the TUI's backend transport module."""

import json

import httpx
import pytest

from cli.tui_client import BackendClient, BackendRequestError, decode_event, websocket_url


def test_websocket_url_preserves_backend_path():
    assert (
        websocket_url("https://example.test/neoswarm", "/ws/agents/session-1")
        == "wss://example.test/neoswarm/ws/agents/session-1"
    )


def test_decode_event_rejects_bad_frames():
    with pytest.raises(ValueError, match="invalid JSON"):
        decode_event("not json")
    with pytest.raises(ValueError, match="missing its name"):
        decode_event('{"data": {}}')
    with pytest.raises(ValueError, match="must be an object"):
        decode_event('{"event": "agent:message", "data": []}')


@pytest.mark.asyncio
async def test_client_uses_the_backend_session_contract():
    requests: list[tuple[str, str, dict | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json_or_none(request)
        requests.append((request.method, request.url.path, payload))
        if request.url.path == "/api/health/check":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/api/agents/models":
            return httpx.Response(200, json={"models": {"Ollama": []}})
        if request.url.path == "/api/agents/sessions" and request.method == "GET":
            return httpx.Response(200, json={"sessions": []})
        if request.url.path == "/api/agents/launch":
            return httpx.Response(200, json={"session": {"id": "session-1"}})
        if request.url.path.endswith("/message"):
            return httpx.Response(200, json={"ok": True})
        if request.method == "DELETE":
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(404, json={"detail": "missing"})

    client = BackendClient(
        "http://localhost:8324",
        transport=httpx.MockTransport(handler),
    )

    assert await client.health() is True
    assert await client.models() == {"Ollama": []}
    assert await client.sessions() == []
    assert await client.launch({"model": "llama3.3"}) == {"id": "session-1"}
    await client.send("session-1", {"prompt": "hello"})
    await client.delete("session-1")

    assert requests[-2:] == [
        ("POST", "/api/agents/sessions/session-1/message", {"prompt": "hello"}),
        ("DELETE", "/api/agents/sessions/session-1", None),
    ]


@pytest.mark.asyncio
async def test_client_raises_useful_error_for_failed_requests():
    client = BackendClient(
        "http://localhost:8324",
        transport=httpx.MockTransport(lambda _: httpx.Response(503, text="offline")),
    )

    with pytest.raises(BackendRequestError, match="503"):
        await client.models()


def json_or_none(request: httpx.Request) -> dict | None:
    return json.loads(request.content) if request.content else None
