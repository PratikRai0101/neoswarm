"""Headless smoke tests for the Textual TUI composition."""

import pytest
from textual.widgets import Input, ListView, Static

from cli.tui import NeoSwarmTUI


@pytest.mark.asyncio
async def test_tui_mounts_the_session_chat_and_activity_panels(monkeypatch):
    app = NeoSwarmTUI()

    async def offline_refresh():
        app.state.connection_status = "offline"
        app.state.connection_detail = "test backend"
        app.render_all()

    monkeypatch.setattr(app, "refresh_backend", offline_refresh)

    async with app.run_test():
        assert app.query_one("#sessions-list", ListView)
        assert app.query_one("#chat-input", Input)
        assert app.query_one("#activity-text", Static)
