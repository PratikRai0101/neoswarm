"""Presentation state for the NeoSwarm Textual interface.

This module receives validated backend events and maintains a coherent local
session view.  Widgets render its data but never need to understand streaming
message replacement, approval queues, or status updates.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from cli.tui_client import BackendEvent


@dataclass
class TuiState:
    """Own the TUI's loaded sessions and live event-derived state."""

    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    active_session_id: str | None = None
    connection_status: str = "offline"
    connection_detail: str = ""
    pending_approvals: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def replace_sessions(self, sessions: list[dict[str, Any]]) -> None:
        """Merge a server session listing without discarding live stream content."""
        listed_ids = set()
        for session in sessions:
            session_id = session.get("id")
            if not isinstance(session_id, str) or not session_id:
                continue
            listed_ids.add(session_id)
            existing = self.sessions.get(session_id, {})
            merged = {**existing, **deepcopy(session)}
            if existing.get("messages") and not session.get("messages"):
                merged["messages"] = existing["messages"]
            self.sessions[session_id] = merged

        for session_id in set(self.sessions) - listed_ids:
            if session_id != self.active_session_id:
                del self.sessions[session_id]

        if self.active_session_id not in self.sessions:
            self.active_session_id = next(iter(self.sessions), None)

    def upsert_session(self, session: dict[str, Any], *, activate: bool = False) -> None:
        session_id = session.get("id")
        if not isinstance(session_id, str) or not session_id:
            return
        existing = self.sessions.get(session_id, {})
        self.sessions[session_id] = {**existing, **deepcopy(session)}
        self.sessions[session_id].setdefault("messages", [])
        if activate or self.active_session_id is None:
            self.active_session_id = session_id

    def activate(self, session_id: str | None) -> None:
        if session_id is None or session_id in self.sessions:
            self.active_session_id = session_id

    def remove_session(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)
        self.pending_approvals.pop(session_id, None)
        if self.active_session_id == session_id:
            self.active_session_id = next(iter(self.sessions), None)

    def active_session(self) -> dict[str, Any] | None:
        if self.active_session_id is None:
            return None
        return self.sessions.get(self.active_session_id)

    def messages_for(self, session_id: str | None = None) -> list[dict[str, Any]]:
        target = session_id or self.active_session_id
        if target is None:
            return []
        session = self.sessions.get(target, {})
        messages = session.get("messages", [])
        return messages if isinstance(messages, list) else []

    def apply(self, session_id: str, event: BackendEvent) -> bool:
        """Apply one event and return whether callers should re-render."""
        if event.event == "connection:open":
            self.connection_status = "connected"
            self.connection_detail = ""
            return True
        if event.event == "connection:offline":
            self.connection_status = "reconnecting"
            self.connection_detail = str(event.data.get("error", "offline"))
            return True

        session = self.sessions.get(session_id)
        if session is None:
            return False
        session.setdefault("messages", [])

        if event.event == "agent:status":
            incoming = event.data.get("session")
            if isinstance(incoming, dict):
                self.upsert_session(incoming)
                session = self.sessions[session_id]
            status = event.data.get("status")
            if isinstance(status, str):
                session["status"] = status
            return True

        if event.event == "agent:stream_start":
            message_id = event.data.get("message_id")
            role = event.data.get("role")
            if not isinstance(message_id, str) or not isinstance(role, str):
                return False
            if not self._message(session, message_id):
                content: Any = "" if role != "tool_call" else {
                    "tool": event.data.get("tool_name", "Tool"),
                    "input": "",
                }
                session["messages"].append(
                    {"id": message_id, "role": role, "content": content}
                )
            return True

        if event.event == "agent:stream_delta":
            message_id = event.data.get("message_id")
            delta = event.data.get("delta")
            message = self._message(session, message_id)
            if message is None or not isinstance(delta, str):
                return False
            if message.get("role") == "tool_call":
                content = message.setdefault("content", {})
                if not isinstance(content, dict):
                    content = message["content"] = {}
                content["input"] = f"{content.get('input', '')}{delta}"
            else:
                message["content"] = f"{message.get('content', '')}{delta}"
            return True

        if event.event == "agent:message":
            incoming = event.data.get("message")
            if not isinstance(incoming, dict):
                return False
            message_id = incoming.get("id")
            existing = self._message(session, message_id)
            if existing is None:
                session["messages"].append(deepcopy(incoming))
            else:
                existing.clear()
                existing.update(deepcopy(incoming))
            return True

        if event.event == "agent:cost_update":
            session["cost_usd"] = event.data.get("cost_usd", session.get("cost_usd", 0))
            return True

        if event.event == "agent:approval_request":
            request = event.data.get("approval") or event.data.get("request")
            if isinstance(request, dict):
                requests = self.pending_approvals.setdefault(session_id, [])
                if not any(item.get("id") == request.get("id") for item in requests):
                    requests.append(deepcopy(request))
                return True

        return False

    @staticmethod
    def _message(session: dict[str, Any], message_id: Any) -> dict[str, Any] | None:
        if not isinstance(message_id, str):
            return None
        for message in session.get("messages", []):
            if isinstance(message, dict) and message.get("id") == message_id:
                return message
        return None
