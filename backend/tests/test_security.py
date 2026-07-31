"""Security defaults for the loopback backend."""

from fastapi.testclient import TestClient

from backend.main import app


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
