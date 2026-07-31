"""Backend transport for the NeoSwarm Textual interface.

The TUI talks to the agent backend through this module rather than handling
HTTP responses and WebSocket frames in widgets.  Its interface deliberately
stays small: load state, create/send/delete a session, and stream a session's
events.  Connection retries and wire-format validation live here.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, AsyncIterator
from urllib.parse import quote, urlsplit, urlunsplit

import httpx
import websockets


class BackendRequestError(RuntimeError):
    """A backend REST request failed with useful caller-facing context."""


@dataclass(frozen=True)
class BackendEvent:
    """One validated event from an agent WebSocket or client connection state."""

    event: str
    data: dict[str, Any]


def websocket_url(backend_url: str, path: str) -> str:
    """Turn an HTTP backend URL and absolute path into a WebSocket URL."""
    parsed = urlsplit(backend_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("backend_url must be an absolute http(s) URL")
    scheme = "wss" if parsed.scheme == "https" else "ws"
    base_path = parsed.path.rstrip("/")
    return urlunsplit((scheme, parsed.netloc, f"{base_path}{path}", "", ""))


def decode_event(raw: str) -> BackendEvent:
    """Validate a backend WebSocket frame before it reaches the UI state."""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("backend sent invalid JSON") from exc

    event = payload.get("event")
    data = payload.get("data", {})
    if not isinstance(event, str) or not event:
        raise ValueError("backend event is missing its name")
    if not isinstance(data, dict):
        raise ValueError("backend event data must be an object")
    return BackendEvent(event=event, data=data)


class BackendClient:
    """Own the TUI's REST and per-session WebSocket interaction.

    Callers only supply the backend URL and use the high-level methods below.
    REST failures raise :class:`BackendRequestError`; transient WebSocket
    failures become ``connection:offline`` events and reconnect with backoff.
    """

    def __init__(
        self,
        backend_url: str,
        *,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.backend_url = backend_url.rstrip("/")
        self.timeout = timeout
        self._transport = transport

    async def health(self) -> bool:
        try:
            response = await self._request("GET", "/api/health/check")
        except BackendRequestError:
            return False
        return response.get("status") == "ok"

    async def models(self) -> dict[str, list[dict[str, Any]]]:
        response = await self._request("GET", "/api/agents/models")
        models = response.get("models", {})
        if not isinstance(models, dict):
            raise BackendRequestError("backend returned an invalid model catalog")
        return models

    async def sessions(self) -> list[dict[str, Any]]:
        response = await self._request("GET", "/api/agents/sessions")
        sessions = response.get("sessions", [])
        if not isinstance(sessions, list):
            raise BackendRequestError("backend returned invalid sessions")
        return sessions

    async def launch(self, config: dict[str, Any]) -> dict[str, Any]:
        response = await self._request("POST", "/api/agents/launch", payload=config)
        session = response.get("session")
        if not isinstance(session, dict) or not session.get("id"):
            raise BackendRequestError("backend did not return a new session")
        return session

    async def send(self, session_id: str, payload: dict[str, Any]) -> None:
        await self._request(
            "POST",
            f"/api/agents/sessions/{quote(session_id, safe='')}/message",
            payload=payload,
        )

    async def delete(self, session_id: str) -> None:
        await self._request(
            "DELETE", f"/api/agents/sessions/{quote(session_id, safe='')}"
        )

    async def _request(
        self, method: str, path: str, *, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(
                base_url=self.backend_url,
                timeout=self.timeout,
                transport=self._transport,
            ) as client:
                response = await client.request(method, path, json=payload)
        except httpx.HTTPError as exc:
            raise BackendRequestError(f"backend request failed: {exc}") from exc

        if response.is_error:
            detail = response.text.strip().replace("\n", " ")[:300]
            raise BackendRequestError(
                f"backend request failed ({response.status_code}): {detail}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise BackendRequestError("backend returned invalid JSON") from exc
        if not isinstance(data, dict):
            raise BackendRequestError("backend response must be an object")
        return data

    async def session_events(
        self, session_id: str, stop: asyncio.Event
    ) -> AsyncIterator[BackendEvent]:
        """Yield events for a session until cancelled or ``stop`` is set."""
        url = websocket_url(
            self.backend_url,
            f"/ws/agents/{quote(session_id, safe='')}",
        )
        retry_delay = 0.5

        while not stop.is_set():
            try:
                async with websockets.connect(url, ping_interval=20) as socket:
                    retry_delay = 0.5
                    yield BackendEvent("connection:open", {"session_id": session_id})
                    async for raw in socket:
                        if stop.is_set():
                            return
                        yield decode_event(raw)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                yield BackendEvent(
                    "connection:offline",
                    {"session_id": session_id, "error": str(exc)},
                )
                try:
                    await asyncio.wait_for(stop.wait(), timeout=retry_delay)
                except asyncio.TimeoutError:
                    retry_delay = min(retry_delay * 2, 8.0)
