#!/usr/bin/env python3
"""NeoSwarm TUI - Raycast-style terminal UI for your AI agent swarm."""

import asyncio
import os
from typing import Optional

import httpx
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Static, Input, Button, ListView, ListItem
from textual.widgets import TextArea as TA
from textual.screen import ModalScreen
from textual import work
from textual.binding import Binding

BACKEND_URL = os.environ.get("NEOSWARM_URL", "http://localhost:8324")


class ModelPickerScreen(ModalScreen):
    """Raycast-style floating model picker with search."""

    CSS = """
    ModelPickerScreen {
        align: center middle;
        background: rgba(0,0,0,0.7);
    }
    #picker-box {
        width: 50;
        height: 22;
        border: solid $primary;
        background: $surface;
        layer: overlay;
    }
    #picker-title {
        background: $primary;
        color: $text;
        text-align: center;
        padding: 1 0;
    }
    #search-input {
        dock: top;
        margin: 0 1;
    }
    #model-list {
        height: 14;
        margin: 0 1;
    }
    #picker-footer {
        text-align: center;
        color: $text-disabled;
        padding: 0 1;
    }
    ListItem {
        padding: 0 1;
    }
    ListItem > .current {
        background: $accent;
        color: $text;
    }
    ListItem:hover {
        background: $boost;
    }
    """

    def __init__(self, available_models: dict, current_model: str, **kwargs):
        super().__init__(**kwargs)
        self.all_models = []
        for provider, models in available_models.items():
            for m in models:
                self.all_models.append({
                    "provider": provider,
                    "value": m.get("value", ""),
                    "label": m.get("label", m.get("value", "")),
                })
        self.current_model = current_model
        self.filtered: list = list(self.all_models)

    def compose(self) -> ComposeResult:
        yield Container(
            Static("[bold]Select Model[/bold]", id="picker-title"),
            Input(placeholder="Search models...", id="search-input"),
            ListView(id="model-list"),
            Static("↑↓ navigate · enter select · esc cancel", id="picker-footer"),
            id="picker-box",
        )

    async def on_mount(self) -> None:
        await self.refresh_list()
        self.query_one("#search-input", Input).focus()

    async def refresh_list(self, query: str = "") -> None:
        q = query.lower()
        self.filtered = [m for m in self.all_models if not q or q in m["value"].lower() or q in m["label"].lower()]

        list_view = self.query_one("#model-list", ListView)
        list_view.clear()
        last_provider = None
        for m in self.filtered:
            label = m["label"]
            if m["provider"] != last_provider:
                list_view.append(ListItem(Static(f"\n[bold cyan]{m['provider']}[/bold cyan]", classes="provider-header")))
                last_provider = m["provider"]
            marker = " ▶ " if m["value"] == self.current_model else "   "
            list_view.append(ListItem(Static(f"{marker}{label}")))

    def on_input_changed(self, event: Input.Changed) -> None:
        asyncio.create_task(self.refresh_list(event.value))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if not self.filtered:
            return
        idx = event.list_view.index
        # Subtract provider headers to get real model index
        real_idx = 0
        for i in range(len(self.filtered)):
            if i == idx:
                self.dismiss(self.filtered[real_idx])
                return
            real_idx += 1

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


class NeoSwarmTUI(App):
    """NeoSwarm Terminal UI - OpenCode/Raycast inspired."""

    CSS = """
    Screen { background: $surface; }
    #main { height: 100%; }
    #sidebar { width: 25; border: solid cyan; background: $panel; }
    #chat-panel { border: solid green; }
    #output-panel { border: solid yellow; }
    #chat-input { dock: bottom; height: 3; }
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
        self.current_provider = "Anthropic"
        self.messages: list[dict] = []
        self.available_models: dict = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main"):
            with Horizontal():
                with Vertical(id="sidebar"):
                    yield Static("Sessions", id="sessions-header")
                    yield Static("No active sessions", id="sessions-list")
                    yield Static("\nTools", id="tools-header")
                    yield Static("• bash\n• write\n• read\n• grep", id="tools-list")
                with Vertical(id="chat-panel"):
                    yield Static("[bold]Chat[/bold] sonnet", id="chat-header")
                    yield TA(id="chat-history", classes="panel")
                    yield Input(placeholder="Type message or /model <n>...", id="chat-input")
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
                resp = await client.get(f"{self.backend_url}/api/health/check", timeout=5.0)
                self.update_status("[green]Connected[/green]" if resp.status_code == 200 else "[red]Error[/red]")
        except Exception as e:
            self.update_status(f"[red]Offline: {e}[/red]")

    async def fetch_models(self):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.backend_url}/api/agents/models", timeout=10.0)
                if resp.status_code == 200:
                    self.available_models = resp.json().get("models", {})
                    total = sum(len(v) for v in self.available_models.values())
                    self.update_status(f"[green]Loaded {total} models[/green]")
        except Exception:
            self.update_status("[yellow]Using defaults[/yellow]")

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
        arg = message[7:].strip()
        if not arg:
            await self.action_switch_model()
            return

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
        chat_history.text = (chat_history.text or "") + f"You: {message}\n"
        if not self.session_id:
            await self.create_session()
        if self.session_id:
            await self.prompt_session(message)

    async def create_session(self):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(f"{self.backend_url}/api/agents/sessions", json={"model": self.current_model, "mode": "chat"})
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
                resp = await client.post(f"{self.backend_url}/api/agents/sessions/{self.session_id}/prompt", json={"prompt": prompt})
                if resp.status_code == 200:
                    response = resp.json().get("response", "")
                    self.messages.append({"role": "assistant", "content": response})
                    chat_history = self.query_one("#chat-history", TA)
                    chat_history.text = (chat_history.text or "") + f"Neo: {response}\n"
                    output_text.update(response[:500])
        except Exception as e:
            output_text.update(f"[red]Error: {e}[/red]")

    def update_sessions_list(self):
        try:
            sessions = self.query_one("#sessions-list", Static)
            sessions.update(f"• {self.session_id[:8]}..." if self.session_id else "No active sessions")
        except Exception:
            pass

    def action_new_session(self):
        self.session_id = None
        self.messages = []
        self.query_one("#chat-history", TA).clear()
        self.update_sessions_list()
        self.update_status("[cyan]New session[/cyan]")

    async def action_switch_model(self):
        if not self.available_models:
            self.update_status("[yellow]No models loaded. Press ^r to refresh.[/yellow]")
            return
        result = await self.push_screen_wait(ModelPickerScreen(self.available_models, self.current_model))
        if result:
            self.current_model = result.get("value", result)
            self.current_provider = result.get("provider", "")
            self.update_status(f"[green]Model: {self.current_model} ({self.current_provider})[/green]")

    def action_command_palette(self):
        self.show_help()

    def show_help(self):
        self.update_status(
            "[bold]NeoSwarm TUI Shortcuts:[/bold]\n"
            "^n  New chat  ^m  Model picker  ^s  Sidebar\n"
            "^r  Refresh   ^a  Toggle output  /model <n>  Select\n"
        )

    def action_toggle_sidebar(self):
        self.query_one("#sidebar").display = not self.query_one("#sidebar").display

    def action_toggle_output(self):
        self.query_one("#output-panel").display = not self.query_one("#output-panel").display

    def action_refresh(self):
        self.connect_backend()
        asyncio.create_task(self.fetch_models())


def run_tui():
    NeoSwarmTUI(backend_url=BACKEND_URL).run()


if __name__ == "__main__":
    run_tui()
