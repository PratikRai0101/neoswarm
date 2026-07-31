"""Tests for event-to-state handling in the Textual UI."""

from cli.tui_client import BackendEvent
from cli.tui_state import TuiState


def session(session_id: str = "session-1") -> dict:
    return {
        "id": session_id,
        "name": "Review",
        "status": "running",
        "model": "llama3.3",
        "provider": "ollama",
        "messages": [],
    }


def test_streamed_message_is_replaced_by_the_final_backend_message():
    state = TuiState()
    state.upsert_session(session(), activate=True)

    assert state.apply(
        "session-1",
        BackendEvent(
            "agent:stream_start",
            {"message_id": "assistant-1", "role": "assistant"},
        ),
    )
    state.apply(
        "session-1",
        BackendEvent("agent:stream_delta", {"message_id": "assistant-1", "delta": "Hel"}),
    )
    state.apply(
        "session-1",
        BackendEvent("agent:stream_delta", {"message_id": "assistant-1", "delta": "lo"}),
    )

    assert state.messages_for() == [
        {"id": "assistant-1", "role": "assistant", "content": "Hello"}
    ]

    state.apply(
        "session-1",
        BackendEvent(
            "agent:message",
            {
                "message": {
                    "id": "assistant-1",
                    "role": "assistant",
                    "content": "Hello, final answer.",
                    "branch_id": "main",
                }
            },
        ),
    )

    assert state.messages_for() == [
        {
            "id": "assistant-1",
            "role": "assistant",
            "content": "Hello, final answer.",
            "branch_id": "main",
        }
    ]


def test_state_tracks_connection_approval_and_session_status():
    state = TuiState()
    state.upsert_session(session(), activate=True)

    state.apply("session-1", BackendEvent("connection:open", {"session_id": "session-1"}))
    state.apply(
        "session-1",
        BackendEvent(
            "agent:approval_request",
            {"approval": {"id": "approval-1", "tool_name": "Bash"}},
        ),
    )
    state.apply(
        "session-1",
        BackendEvent("agent:status", {"status": "waiting_approval"}),
    )

    assert state.connection_status == "connected"
    assert state.active_session()["status"] == "waiting_approval"
    assert state.pending_approvals == {
        "session-1": [{"id": "approval-1", "tool_name": "Bash"}]
    }
