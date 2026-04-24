#!/usr/bin/env python3
"""NeoSwarm TUI - A rich terminal UI for your AI agent swarm.

Like Codex but for NeoSwarm - a full-screen terminal app with:
- Split panes: chat + agent output
- Interactive panels for agents, tools, sessions
- Live updates and streaming
"""

import asyncio
import os
import sys
from typing import Literal

import httpx
from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Static, Input, Button
from textual.widgets import TextArea as TA
from textual.screen import Screen
from textual import work

console = Console()


class NeoSwarmTUI(App):
    """NeoSwarm Terminal UI - like Codex but for your swarm."""

    CSS = """
    Screen {
        background: $surface;
    }
    #main {
        height: 100%;
    }
    .panel {
        border: solid green;
        padding: 1 2;
    }
    #chat-input {
        dock: bottom;
        height: 3;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+n", "new_session", "New Chat"),
        ("ctrl+s", "toggle_sidebar", "Toggle Sidebar"),
        ("ctrl+r", "refresh", "Refresh"),
    ]

    def __init__(self, backend_url: str = "http://localhost:8324"):
        super().__init__()
        self.backend_url = backend_url
        self.session_id: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main"):
            with Horizontal():
                yield Static("Sessions\nAgents\nTools", id="sidebar", classes="panel")
                with Vertical():
                    yield TA(id="chat", classes="panel")
                    yield Input(placeholder="Send message...", id="chat-input")
        yield Footer()

    async def on_mount(self) -> None:
        """Start up and connect to backend."""
        console.print("[green]NeoSwarm TUI[/green]")
        self.connect_backend()

    @work
    async def connect_backend(self):
        """Connect to the backend API."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.backend_url}/api/health/check", timeout=5.0
                )
                if resp.status_code == 200:
                    console.print("[green]Connected to backend[/green]")
                else:
                    console.print("[red]Backend returned error[/red]")
        except Exception as e:
            console.print(f"[red]Cannot connect: {e}[/red]")

    def action_new_session(self):
        """Start a new chat session."""
        console.print("[cyan]Starting new session...[/cyan]")

    def action_toggle_sidebar(self):
        """Toggle the sidebar."""
        sidebar = self.query_one("#sidebar")
        if sidebar.display:
            sidebar.display = False
        else:
            sidebar.display = True

    def action_refresh(self):
        """Refresh the view."""
        console.print("[cyan]Refreshing...[/cyan]")


def run_tui():
    """Run the TUI app."""
    backend = os.environ.get("NEOSWARM_URL", "http://localhost:8324")
    app = NeoSwarmTUI(backend_url=backend)
    app.run()


if __name__ == "__main__":
    run_tui()