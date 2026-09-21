"""Phase B (upstream port): direct browser parity behaviors.

Covers in-flight command drain, bounded observations, the dashboard-less
one-line error, RequestUserText plumbing, and browser-last-resort routing.
"""

import asyncio

import pytest

from backend.apps.agents import ws_manager as ws_module
from backend.apps.agents.browser_agent import (
    _MAX_TOOL_TEXT_CHARS,
    _format_tool_result,
    run_browser_agent,
)


class FakeWS:
    def __init__(self):
        self.sent = []

    async def accept(self):
        pass

    async def send_text(self, payload):
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_browser_command_drain_fails_fast():
    manager = ws_module.ConnectionManager()
    ws = FakeWS()
    await manager.connect_global(ws)

    send_task = asyncio.create_task(
        manager.send_browser_command("req-1", "get_text", "b1", {})
    )
    await asyncio.sleep(0.02)
    assert not send_task.done()

    assert manager.cancel_browser_commands("Dashboard disconnected") == 1
    assert await send_task == {"error": "Dashboard disconnected"}
    manager.disconnect_global(ws)


@pytest.mark.asyncio
async def test_disconnect_global_drains_without_dashboard():
    manager = ws_module.ConnectionManager()
    ws = FakeWS()
    await manager.connect_global(ws)

    send_task = asyncio.create_task(
        manager.send_browser_command("req-2", "get_text", "b1", {})
    )
    await asyncio.sleep(0.02)
    manager.disconnect_global(ws)
    assert await send_task == {"error": "Dashboard disconnected"}


def test_format_tool_result_bounds_large_observations():
    long_text = "x" * (_MAX_TOOL_TEXT_CHARS + 500)
    blocks = _format_tool_result({"text": long_text}, "BrowserGetText")
    assert len(blocks) == 1
    assert len(blocks[0]["text"]) < len(long_text)
    assert "truncated" in blocks[0]["text"]

    short = _format_tool_result({"text": "hello"}, "BrowserGetText")
    assert short == [{"type": "text", "text": "hello"}]

    error = _format_tool_result({"error": "boom"}, "BrowserClick")
    assert error == [{"type": "text", "text": "Error: boom"}]


@pytest.mark.asyncio
async def test_dashboard_less_session_gets_one_line_error():
    result = await run_browser_agent(task="do a thing", browser_id="", model="sonnet")
    assert result["session_id"] == ""
    assert result["summary"].startswith("Error: ")
    assert "\n" not in result["summary"]
    assert result["action_log"] == []


def test_browser_context_routes_browser_last(monkeypatch):
    from types import SimpleNamespace

    import backend.apps.agents.agent_manager as manager_module

    manager = manager_module.AgentManager()

    # Patch the dashboards loader used inside _build_browser_context.
    import backend.apps.dashboards.dashboards as dashboards_module

    fake_dashboard = SimpleNamespace(
        model_dump=lambda mode: {"layout": {"browser_cards": {}}}
    )
    monkeypatch.setattr(dashboards_module, "_load", lambda dashboard_id: fake_dashboard)

    context = manager._build_browser_context("dash-1")
    assert context is not None
    assert "LAST resort" in context
    assert "WebSearch" in context


@pytest.mark.asyncio
async def test_user_controlled_browser_fails_fast():
    manager = ws_module.ConnectionManager()
    assert manager.take_browser_control("b1") is True
    assert manager.take_browser_control("b1") is False
    assert manager.is_browser_controlled("b1") is True

    ws = FakeWS()
    await manager.connect_global(ws)
    result = await manager.send_browser_command("req-9", "click", "b1", {})
    assert "under user control" in result["error"]
    assert manager.browser_futures == {}

    assert manager.release_browser_control("b1") is True
    assert manager.release_browser_control("b1") is False
    assert manager.is_browser_controlled("b1") is False
    manager.disconnect_global(ws)


def test_browser_hover_registered_everywhere():
    from backend.apps.agents.browser_agent import ACTION_MAP, BROWSER_TOOLS_SCHEMA

    assert ACTION_MAP["BrowserHover"] == "hover"
    by_name = {item["name"]: item for item in BROWSER_TOOLS_SCHEMA}
    assert "BrowserHover" in by_name
    assert by_name["BrowserHover"]["input_schema"]["required"] == ["selector"]
    assert "RequestUserText" in by_name
    batch = by_name["BrowserBatch"]
    assert "hover" in batch["input_schema"]["properties"]["actions"]["items"]["properties"]["type"]["enum"]
