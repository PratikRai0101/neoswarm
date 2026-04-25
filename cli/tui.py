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
from textual.screen import Screen, ModalScreen
from textual import work
from textual.binding import Binding
from textual.reactive import reactive

console = Console()

BACKEND_URL = os.environ.get("NEOSWARM_URL", "http://localhost:8324")


class CommandPaletteScreen(ModalScreen):
    """Command palette - quick access to actions."""

    def compose(self) -> ComposeResult:
        yield Static("[bold]Command Palette[/bold]\n", id="palette-title")
        commands = [
            ("new", "Start new chat"),
            ("model", "Switch model"),
            ("refresh", "Refresh backend"),
            ("sidebar", "Toggle sidebar"),
            ("clear", "Clear chat history"),
            ("help", "Show shortcuts"),
        ]
        for cmd_id, desc in commands:
            yield Button(f"[cyan]/{cmd_id}[/cyan]  —  {desc}", id=f"cmd-{cmd_id}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "cmd-help":
            self.app.dismiss("/help")
            return
        if btn_id and btn_id.startswith("cmd-"):
            self.app.dismiss("/" + btn_id[4:])
        else:
            self.app.dismiss(None)


class ModelPickerScreen(ModalScreen):
    """Modal screen for selecting a model."""

    def __init__(self, available_models: dict, current_model: str, app_ref, **kwargs):
        super().__init__(**kwargs)
        self.available_models = available_models
        self.current_model = current_model
        self.app_ref = app_ref

    def compose(self) -> ComposeResult:
        yield Static("[bold]Select Model[/bold]\n", id="picker-title")
        idx = 1
        for provider, models in self.available_models.items():
            yield Static(f"[bold cyan]{provider}:[/bold cyan]", id=f"header-{provider}")
            for m in models:
                label = m.get("label", m.get("value", ""))
                value = m.get("value", "")
                is_current = "← current" if value == self.current_model else ""
                yield Button(f"  {idx}. {label} {is_current}", id=f"model-{idx}", variant="primary" if value == self.current_model else "default")
                idx += 1
        yield Static("")
        yield Button("Cancel", id="cancel-btn", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "cancel-btn":
            self.app.dismiss()
            return
        if btn_id and btn_id.startswith("model-"):
            idx = int(btn_id.split("-")[1])
            # Find the model at this index
            all_models = []
            for provider, models in self.available_models.items():
                for m in models:
                    all_models.append({"provider": provider, **m})
            if 1 <= idx <= len(all_models):
                selected = all_models[idx - 1]
                self.app.dismiss(selected)


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
        ("ctrl+p", "command_palette", "palette"),
    ]

    def __init__(self, backend_url: str = BACKEND_URL):
        super().__init__()
        self.backend_url = backend_url
        self.session_id: Optional[str] = None
        self.current_model = "sonnet"
        self.current_provider = "Anthropic"
        self.messages: list[dict] = []
        self.output_text = ""
        self.available_models: dict = {}

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
                    yield Static("[bold]Chat[/bold] sonnet", id="chat-header")
                    yield TA(id="chat-history", classes="panel")
                    yield Input(placeholder="Type message...", id="chat-input")
                with Vertical(id="output-panel"):
                    yield Static("[bold]Output[/bold]", id="output-header")
                    yield Static("", id="output-text")
        yield Footer()

    async def on_mount(self) -> None:
        self.connect_backend()
        await self.fetch_models()

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

    async def fetch_models(self):
        """Fetch available models from backend."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.backend_url}/api/agents/models", timeout=10.0
                )
                if resp.status_code == 200:
                    data = resp.json()
                    self.available_models = data.get("models", {})
                    self.update_status(f"[green]Loaded {sum(len(v) for v in self.available_models.values())} models[/green]")
        except Exception as e:
            self.update_status(f"[yellow]Using defaults[/yellow]")

    def update_status(self, status: str):
        try:
            header = self.query_one("#chat-header", Static)
            header.update(f"[bold]Chat[/bold] {self.current_provider}/{self.current_model} | {status}")
        except Exception:
            pass

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        message = event.value.strip()
        if not message:
            return
        event.input.clear()

        # Handle /model command inline
        if message.startswith("/model "):
            await self._handle_inline_model(message)
            return

        if message == "/model":
            asyncio.create_task(self.action_switch_model())
            return

        if message in ("/new", "/clear"):
            self.action_new_session()
            return

        await self.send_message(message)

    async def _handle_inline_model(self, message: str):
        """Handle /model <number> or /model <name> from chat input."""
        arg = message[7:].strip()
        if not arg:
            await self.action_switch_model()
            return

        # Try as number
        try:
            idx = int(arg)
            all_models = []
            for provider, models in self.available_models.items():
                for m in models:
                    all_models.append({"provider": provider, **m})
            if 1 <= idx <= len(all_models):
                selected = all_models[idx - 1]
                self.current_model = selected.get("value", arg)
                self.current_provider = selected.get("provider", "")
                self.update_status(f"[green]Model: {self.current_model} ({self.current_provider})[/green]")
                return
        except ValueError:
            pass

        # Try as partial name match
        for provider, models in self.available_models.items():
            for m in models:
                value = m.get("value", "")
                label = m.get("label", value)
                if arg.lower() in value.lower() or arg.lower() in label.lower():
                    self.current_model = value
                    self.current_provider = provider
                    self.update_status(f"[green]Model: {self.current_model} ({self.current_provider})[/green]")
                    return

        self.update_status(f"[red]Model '{arg}' not found. Press ^m for picker.[/red]")

    async def send_message(self, message: str):
        chat_history = self.query_one("#chat-history", TA)
        
        self.messages.append({"role": "user", "content": message})
        
        # Append to TextArea using correct API
        current_text = chat_history.text or ""
        chat_history.text = current_text + f"You: {message}\n"

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
                    current_text = chat_history.text or ""
                    chat_history.text = current_text + f"Neo: {response}\n"
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

    def action_command_palette(self):
        """Show help - same as pressing ^m or ^n."""
        self.show_help()

    def show_help(self):
        help_text = (
            "[bold]NeoSwarm TUI Shortcuts:[/bold]\n"
            "^n   New chat\n"
            "^m   Switch model\n"
            "^s   Toggle sidebar\n"
            "^r   Refresh backend\n"
            "^a   Toggle output panel\n"
            "^p   Help (this menu)\n"
            "/model <n>   Select model by number\n"
            "/new   New session | /clear   Clear chat"
        )
        self.update_status(help_text)

    async def action_switch_model(self):
        """Show available models in status area."""
        if not self.available_models:
            self.update_status("[yellow]No models loaded. Press ^r to refresh.[/yellow]")
            return

        lines = ["[bold]Available Models:[/bold]"]
        idx = 1
        for provider, models in self.available_models.items():
            lines.append(f"[cyan]{provider}:[/cyan]")
            for m in models[:5]:
                lines.append(f"  {idx}. {m.get('label', m.get('value', ''))}")
                idx += 1
            if len(models) > 5:
                lines.append(f"  ... and {len(models) - 5} more")
            idx += 1
            lines.append("")

        lines.append("Type /model <number> to select (e.g., /model 1)")
        self.update_status("\n".join(lines[:15]))

    def action_toggle_sidebar(self):
        sidebar = self.query_one("#sidebar")
        sidebar.display = not sidebar.display

    def action_toggle_output(self):
        output = self.query_one("#output-panel")
        output.display = not output.display

    async def action_switch_model(self):
        """Show available models in status area."""
        if not self.available_models:
            self.update_status("[yellow]No models loaded. Press ^r to refresh.[/yellow]")
            return

        lines = ["[bold]Available Models:[/bold]"]
        idx = 1
        for provider, models in self.available_models.items():
            lines.append(f"[cyan]{provider}:[/cyan]")
            for m in models[:5]:
                lines.append(f"  {idx}. {m.get('label', m.get('value', ''))}")
                idx += 1
            if len(models) > 5:
                lines.append(f"  ... and {len(models) - 5} more")
            idx += 1
            lines.append("")

        lines.append("Type /model <number> to select (e.g., /model 1)")
        self.update_status("\n".join(lines[:15]))

    def action_command_palette(self):
        """Show help - same as pressing ^p."""
        self.show_help()

    def show_help(self):
        help_text = (
            "[bold]NeoSwarm TUI Shortcuts:[/bold]\n"
            "^n   New chat\n"
            "^m   Switch model\n"
            "^s   Toggle sidebar\n"
            "^r   Refresh backend\n"
            "^a   Toggle output panel\n"
            "^p   Command palette\n"
            "/model <n>   Select model by number\n"
            "/new   New session\n"
            "/clear   Clear chat"
        )
        self.update_status(help_text)

    def action_refresh(self):
        self.connect_backend()
        import asyncio
        asyncio.create_task(self.fetch_models())


def run_tui():
    app = NeoSwarmTUI(backend_url=BACKEND_URL)
    app.run()


if __name__ == "__main__":
    run_tui()
