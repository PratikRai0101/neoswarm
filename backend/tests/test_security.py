"""Security defaults for the loopback backend."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.main import app


def test_health_endpoint_uses_the_shared_json_contract():
    response = TestClient(app).get("/api/health/check")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_allows_local_frontends_but_not_arbitrary_websites():
    client = TestClient(app)

    allowed = client.options(
        "/api/health/check",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    denied = client.options(
        "/api/health/check",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in denied.headers


def test_untrusted_browser_origins_cannot_mutate_loopback_api():
    client = TestClient(app)

    denied = client.post(
        "/api/analytics/event",
        headers={"Origin": "https://untrusted.example"},
        json={"event_type": "security.test"},
    )
    allowed = client.post(
        "/api/analytics/event",
        headers={"Origin": "http://localhost:3000"},
        json={"event_type": "security.test"},
    )
    native_client = client.post(
        "/api/analytics/event",
        json={"event_type": "security.test"},
    )

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert native_client.status_code == 200


def test_untrusted_websocket_origin_is_rejected():
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(
            "/ws/dashboard", headers={"Origin": "https://untrusted.example"}
        ):
            pass

    assert exc_info.value.code == 1008


def test_websocket_rejects_malformed_messages_without_disconnecting():
    client = TestClient(app)

    with client.websocket_connect(
        "/ws/dashboard", headers={"Origin": "http://localhost:3000"}
    ) as websocket:
        websocket.send_text("not json")
        response = websocket.receive_json()
        websocket.send_json([])
        second_response = websocket.receive_json()

    assert response == {
        "event": "error",
        "data": {"error": "Invalid JSON message"},
    }
    assert second_response == {
        "event": "error",
        "data": {"error": "Message must be an object"},
    }
