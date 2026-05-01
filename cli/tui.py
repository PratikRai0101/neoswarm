#!/usr/bin/env python3
"""NeoSwarm TUI — OpenCode-style terminal UI with live session management."""

import asyncio
import os
from typing import Optional

import httpx
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Static, Input, ListView, ListItem, Label
from textual.widgets import TextArea as TA
from textual.screen import ModalScreen
from textual import work
from textual.binding import Binding

BACKEND_URL = os.environ.get("NEOSWARM_URL", "http://localhost:8324")


class CommandCenter(ModalScreen):
    """Unified Raycast-style command center — type to search models & commands."""

    CSS = """
    CommandCenter { align: center middle; background: rgba(0,0,0,0.7); }
    #cc-box { width: 60; height: 24; border: solid $accent; background: $surface; }
    #cc-title { background: $primary; color: $text; text-align: center; padding: 1 0; text-style: bold; }
    #cc-input { dock: top; margin: 1; }
    #cc-results { height: 16; margin: 0 1; }
    #cc-footer { text-align: center; color: $text-disabled; padding: 0 1; }
    ListItem { padding: 0 1; }
    ListItem:hover { background: $boost; }
    """

    COMMANDS = [
        ("/new", "Start new chat", "blue"),
        ("/clear", "Clear chat history", "blue"),
        ("/refresh", "Refresh backend", "blue"),
        ("/sidebar", "Toggle sidebar", "blue"),
        ("/output", "Toggle output panel", "blue"),
    ]

    def __init__(self, available_models: dict, current_model: str, **kwargs):
        super().__init__(**kwargs)
        self.current_model = current_model
        self.all_entries: list[dict] = []
        for provider, models in available_models.items():
            color = {"Ollama": "green", "GitHub Models": "yellow", "Copilot": "cyan"}.get(provider, "white")
            for m in models:
                self.all_entries.append({
                    "type": "model",
                    "label": m.get("label", m.get("value", "")),
                    "value": m.get("value", ""),
                    "provider": provider,
                    "color": color,
                    "data": {"provider": provider, **m},
                })
        for cmd, desc, color in self.COMMANDS:
            self.all_entries.append({
                "type": "cmd",
                "label": f"{cmd}  —  {desc}",
                "value": cmd,
                "provider": "",
                "color": color,
                "data": cmd,
            })
        self.filtered: list = list(self.all_entries)

    def compose(self) -> ComposeResult:
        yield Container(
            Static("🔍  Command Center  (type to search)", id="cc-title"),
            Input(placeholder="Search models or commands...", id="cc-input"),
            ListView(id="cc-results"),
            Static("↑↓ navigate · enter select · esc cancel", id="cc-footer"),
            id="cc-box",
        )

    async def on_mount(self) -> None:
        await self._refresh()
        self.query_one("#cc-input", Input).focus()

    async def _refresh(self, query: str = "") -> None:
        q = query.lower().strip()
        self.filtered = [e for e in self.all_entries if not q or q in e["label"].lower() or q in e["value"].lower()]
        list_view = self.query_one("#cc-results", ListView)
        list_view.clear()
        last_provider = None
        for e in self.filtered:
            if e["type"] == "model":
                if e["provider"] != last_provider:
                    list_view.append(ListItem(Static(f"\n[bold {e['color']}]{e['provider']}[/bold {e['color']}]")))
                    last_provider = e["provider"]
                marker = "▶ " if e["value"] == self.current_model else "  "
                list_view.append(ListItem(Static(f"  {marker}[{e['color']}]◆[/{e['color']}] {e['label']}")))
            else:
                if last_provider is not None:
                    last_provider = None
                    list_view.append(ListItem(Static("")))
                list_view.append(ListItem(Static(f"  [{e['color']}]/[/{e['color']}] {e['label']}")))

    def on_input_changed(self, event: Input.Changed) -> None:
        asyncio.create_task(self._refresh(event.value))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if not self.filtered:
            return
        self.dismiss(self.filtered[event.list_view.index]["data"])

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


class NeoSwarmTUI(App):
    """NeoSwarm Terminal UI — OpenCode-style with live session management."""

    CSS = """
    Screen { background: $surface; }
    #main { height: 100%; }
    #sidebar { width: 28; border: solid cyan; background: $panel; }
    #sidebar Label { padding: 0 1; text-style: bold; }
    #chat-panel { border: solid green; }
    #output-panel { border: solid yellow; }
    #chat-input { dock: bottom; height: 3; }
    #sessions-list { height: 8; margin: 0 1; }
    #sessions-list ListItem { padding: 0 1; }
    #sessions-list ListItem:hover { background: $boost; }
    .active-session { background: $accent; color: $text; }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+n", "new_session", "New Chat"),
        ("ctrl+m", "command_center", "Command Center"),
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
        self.sessions: list[dict] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main"):
            with Horizontal():
                with Vertical(id="sidebar"):
                    yield Label("Sessions")
                    yield ListView(id="sessions-list")
                    yield Label("Tools")
                    yield Static("  • bash\n  • write\n  • read\n  • grep", id="tools-list")
                with Vertical(id="chat-panel"):
                    yield Static("[bold]Chat[/bold] sonnet", id="chat-header")
                    yield TA(id="chat-history")
                    yield Input(placeholder="Type message or /model <n>...", id="chat-input")
                with Vertical(id="output-panel"):
                    yield Static("[bold]Output[/bold]", id="output-header")
                    yield Static("", id="output-text")
        yield Footer()

    async def on_mount(self) -> None:
        self.connect_backend()
        await self.fetch_models()
        await self.fetch_sessions()

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

    async def fetch_sessions(self):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"{self.backend_url}/api/agents/sessions", timeout=5.0)
                if resp.status_code == 200:
                    self.sessions = resp.json().get("sessions", [])
                    self.render_sessions()
        except Exception:
            pass

    def render_sessions(self):
        list_view = self.query_one("#sessions-list", ListView)
        list_view.clear()
        if not self.sessions:
            list_view.append(ListItem(Static("  No sessions", id="no-sessions")))
            return
        for s in self.sessions:
            sid = s.get("id", "")[:8]
            model = s.get("model", "?")
            is_active = sid == (self.session_id[:8] if self.session_id else None)
            prefix = "▶ " if is_active else "  "
            list_view.append(ListItem(Static(f"{prefix}[cyan]{sid}[/cyan] ({model})", classes="active-session" if is_active else "")))

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
        if message in ("/model", "/new", "/clear", "/refresh", "/sidebar", "/output"):
            self._handle_command(message)
            return
        await self.send_message(message)

    def _handle_command(self, cmd: str):
        {
            "/model": lambda: asyncio.create_task(self.action_command_center()),
            "/new": lambda: self.action_new_session(),
            "/clear": lambda: self.action_new_session(),
            "/refresh": lambda: self.action_refresh(),
            "/sidebar": lambda: self.action_toggle_sidebar(),
            "/output": lambda: self.action_toggle_output(),
        }.get(cmd, lambda: None)()

    async def _handle_inline_model(self, message: str):
        arg = message[7:].strip()
        if not arg:
            await self.action_command_center()
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
                resp = await client.post(
                    f"{self.backend_url}/api/agents/launch",
                    json={"model": self.current_model, "mode": "chat"},
                )
                if resp.status_code == 200:
                    body = resp.json()
                    self.session_id = body.get("session_id")
                    await self.fetch_sessions()
                    self.update_status(f"[green]Session {self.session_id[:8] if self.session_id else ''} created[/green]")
                else:
                    self.update_status(f"[red]Create session failed: {resp.status_code}[/red]")
        except Exception as e:
            self.update_status(f"[red]Error: {e}[/red]")

    async def prompt_session(self, prompt: str):
        output_text = self.query_one("#output-text", Static)
        output_text.update("[yellow]Thinking...[/yellow]")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.backend_url}/api/agents/sessions/{self.session_id}/message",
                    json={"prompt": prompt},
                )
                if resp.status_code == 200:
                    result = resp.json()
                    response = result.get("response", result.get("content", "(no response)"))
                    self.messages.append({"role": "assistant", "content": response})
                    chat_history = self.query_one("#chat-history", TA)
                    chat_history.text = (chat_history.text or "") + f"Neo: {response}\n"
                    output_text.update(response[:500])
        except Exception as e:
            output_text.update(f"[red]Error: {e}[/red]")

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Switch to a session from the sidebar."""
        if event.list_view.id != "sessions-list":
            return
        if not self.sessions:
            return
        idx = event.list_view.index
        if idx < len(self.sessions):
            s = self.sessions[idx]
            self.session_id = s.get("id")
            self.current_model = s.get("model", self.current_model)
            self.current_provider = s.get("provider", self.current_provider)
            self.messages = s.get("messages", [])
            chat_history = self.query_one("#chat-history", TA)
            chat_history.text = "\n".join(
                f"{'You' if m.get('role') == 'user' else 'Neo'}: {m.get('content', '')}"
                for m in self.messages
            ) or ""
            self.update_status(f"[green]Switched to session {self.session_id[:8]}[/green]")
            self.render_sessions()

    async def action_delete_session(self, session_id: str):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.delete(f"{self.backend_url}/api/agents/sessions/{session_id}")
                if resp.status_code == 200:
                    if self.session_id == session_id:
                        self.session_id = None
                        self.messages = []
                        self.query_one("#chat-history", TA).clear()
                    await self.fetch_sessions()
                    self.update_status("[green]Session deleted[/green]")
        except Exception as e:
            self.update_status(f"[red]Delete failed: {e}[/red]")

    def action_new_session(self):
        self.session_id = None
        self.messages = []
        self.query_one("#chat-history", TA).clear()
        self.render_sessions()
        self.update_status("[cyan]New session[/cyan]")

    async def action_command_center(self):
        if not self.available_models:
            self.update_status("[yellow]No models loaded. Press ^r to refresh.[/yellow]")
            return
        result = await self.push_screen_wait(CommandCenter(self.available_models, self.current_model))
        if result is None:
            return
        if isinstance(result, dict):
            self.current_model = result.get("value", result)
            self.current_provider = result.get("provider", "")
            self.update_status(f"[green]Model: {self.current_model} ({self.current_provider})[/green]")
        elif isinstance(result, str):
            self._handle_command(result)

    def action_toggle_sidebar(self):
        sidebar = self.query_one("#sidebar")
        sidebar.display = not sidebar.display
        if sidebar.display:
            asyncio.create_task(self.fetch_sessions())

    def action_toggle_output(self):
        self.query_one("#output-panel").display = not self.query_one("#output-panel").display

    def action_refresh(self):
        self.connect_backend()
        asyncio.create_task(self.fetch_models())
        asyncio.create_task(self.fetch_sessions())


def run_tui():
    NeoSwarmTUI(backend_url=BACKEND_URL).run()


if __name__ == "__main__":
    run_tui()
