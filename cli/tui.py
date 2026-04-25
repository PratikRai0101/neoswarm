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
from typing import Literal, Optional

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
from textual.binding import Binding

console = Console()

BACKEND_URL = os.environ.get("NEOSWARM_URL", "http://localhost:8324")

MODELS = [
    ("sonnet", "Anthropic Sonnet 4.6", "1M"),
    ("opus", "Anthropic Opus 4.6", "1M"),
    ("haiku", "Anthropic Haiku 4.5", "200K"),
    ("llama3.3", "Ollama Llama 3.3", "128K"),
    ("qwen2.5", "Ollama Qwen 2.5", "128K"),
]

PROVIDERS = {
    "sonnet": "anthropic",
    "opus": "anthropic",
    "haiku": "anthropic",
    "llama3.3": "ollama",
    "qwen2.5": "ollama",
}


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
        padding: 0 1;
    }
    .sidebar {
        width: 25;
        border: solid cyan;
        background: $panel;
    }
    #chat-panel {
        border: solid green;
    }
    #output-panel {
        border: solid yellow;
    }
    #chat-input {
        dock: bottom;
        height: 3;
    }
    .model-tag {
        padding: 0 1;
        background: $primary;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+n", "new_session", "New Chat"),
        ("ctrl+m", "switch_model", "Model"),
        ("ctrl+s", "toggle_sidebar", "Sidebar"),
        ("ctrl+r", "refresh", "Refresh"),
        ("ctrl+a", "toggle_output", "Output"),
    ]

    def __init__(self, backend_url: str = BACKEND_URL):
        super().__init__()
        self.backend_url = backend_url
        self.session_id: Optional[str] = None
        self.current_model = "sonnet"
        self.messages: list[dict] = []
        self.output_text = ""

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main"):
            with Horizontal():
                with Vertical(classes="sidebar", id="sidebar"):
                    yield Static("Sessions", id="sessions-header")
                    yield Static("No active sessions", id="sessions-list")
                    yield Static("\nTools", id="tools-header")
                    yield Static("• bash\n• write\n• read\n• grep", id="tools-list")
                with Vertical(id="chat-panel"):
                    yield Static("[bold]Chat[/bold]", id="chat-header")
                    yield TA(id="chat-history", classes="panel")
                    yield Input(placeholder="Type message...", id="chat-input")
                with Vertical(id="output-panel"):
                    yield Static("[bold]Output[/bold]", id="output-header")
                    yield Static("", id="output-text")
        yield Footer()

    async def on_mount(self) -> None:
        self.connect_backend()

    @work
    async def connect_backend(self):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.backend_url}/api/health/check", timeout=5.0
                )
                if resp.status_code == 200:
                    self.update_status("[green]Connected[/green]")
                else:
                    self.update_status("[red]Error[/red]")
        except Exception as e:
            self.update_status(f"[red]Offline: {e}[/red]")

    def update_status(self, status: str):
        try:
            header = self.query_one("#chat-header", Static)
            header.update(f"[bold]Chat[/bold] {self.current_model} | {status}")
        except Exception:
            pass

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        message = event.value.strip()
        if not message:
            return
        event.input.clear()
        await self.send_message(message)

    async def send_message(self, message: str):
        chat_history = self.query_one("#chat-history", TA)
        
        self.messages.append({"role": "user", "content": message})
        chat_history.write(f"[cyan]You:[/cyan] {message}\n")

        if not self.session_id:
            await self.create_session()

        if self.session_id:
            await self.prompt_session(message)

    async def create_session(self):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.backend_url}/api/agents/sessions",
                    json={"model": self.current_model, "mode": "chat"},
                )
                if resp.status_code == 200:
                    self.session_id = resp.json().get("id")
                    self.update_sessions_list()
        except Exception as e:
            self.update_status(f"[red]Error: {e}[/red]")

    async def prompt_session(self, prompt: str):
        output_text = self.query_one("#output-text", Static)
        output_text.update("[yellow]Thinking...[/yellow]")

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.backend_url}/api/agents/sessions/{self.session_id}/prompt",
                    json={"prompt": prompt},
                )
                if resp.status_code == 200:
                    result = resp.json()
                    response = result.get("response", "")
                    self.messages.append({"role": "assistant", "content": response})
                    
                    chat_history = self.query_one("#chat-history", TA)
                    chat_history.write(f"[green]Neo:[/green] {response}\n")
                    output_text.update(response[:500])
        except Exception as e:
            output_text.update(f"[red]Error: {e}[/red]")

    def update_sessions_list(self):
        try:
            sessions = self.query_one("#sessions-list", Static)
            if self.session_id:
                sessions.update(f"• {self.session_id[:8]}...")
            else:
                sessions.update("No active sessions")
        except Exception:
            pass

    def action_new_session(self):
        self.session_id = None
        self.messages = []
        chat_history = self.query_one("#chat-history", TA)
        chat_history.clear()
        self.update_sessions_list()
        self.update_status("[cyan]New session[/cyan]")

    def action_switch_model(self):
        models_short = "\n".join([f"{i+1}. {m[0]}" for i, m in enumerate(MODELS)])
        self.update_status(f"[cyan]Models: {models_short}[/cyan]")

    def action_toggle_sidebar(self):
        sidebar = self.query_one("#sidebar")
        sidebar.display = not sidebar.display

    def action_toggle_output(self):
        output = self.query_one("#output-panel")
        output.display = not output.display

    def action_refresh(self):
        self.connect_backend()


def run_tui():
    app = NeoSwarmTUI(backend_url=BACKEND_URL)
    app.run()


if __name__ == "__main__":
    run_tui()