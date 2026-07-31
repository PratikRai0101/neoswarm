#!/usr/bin/env python3
"""NeoSwarm's streaming Textual terminal interface."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Static
from textual.widgets import TextArea as TA

from cli.tui_client import BackendClient, BackendEvent, BackendRequestError
from cli.tui_state import TuiState


BACKEND_URL = os.environ.get("NEOSWARM_URL", "http://localhost:8324")


class CommandCenter(ModalScreen):
    """Search models and terminal actions in one compact overlay."""

    CSS = """
    CommandCenter { align: center middle; background: rgba(0,0,0,0.7); }
    #cc-box { width: 68; height: 25; border: solid $accent; background: $surface; }
    #cc-title { background: $primary; color: $text; text-align: center; padding: 1 0; text-style: bold; }
    #cc-input { dock: top; margin: 1; }
    #cc-results { height: 17; margin: 0 1; }
    #cc-footer { text-align: center; color: $text-disabled; padding: 0 1; }
    ListItem { padding: 0 1; }
    ListItem:hover { background: $boost; }
    """

    COMMANDS = [
        ("/new", "Start a new chat"),
        ("/refresh", "Refresh sessions and models"),
        ("/sidebar", "Toggle the session rail"),
        ("/output", "Toggle the activity panel"),
        ("/delete", "Delete the active session"),
    ]

    def __init__(self, available_models: dict[str, list[dict]], current_model: str):
        super().__init__()
        self.current_model = current_model
        self.entries: list[dict[str, Any]] = []
        self.rendered_entries: list[dict[str, Any] | None] = []
        for provider, models in available_models.items():
            for model in models:
                self.entries.append(
                    {
                        "type": "model",
                        "provider": provider,
                        "label": model.get("label", model.get("value", "")),
                        "value": model.get("value", ""),
                        "data": {"provider": provider, **model},
                    }
                )
        self.entries.extend(
            {
                "type": "command",
                "provider": "",
                "label": f"{command} — {description}",
                "value": command,
                "data": command,
            }
            for command, description in self.COMMANDS
        )

    def compose(self) -> ComposeResult:
        yield Container(
            Static("⌘  Command Center", id="cc-title"),
            Input(placeholder="Search models or actions...", id="cc-input"),
            ListView(id="cc-results"),
            Static("↑↓ navigate · enter select · esc cancel", id="cc-footer"),
            id="cc-box",
        )

    async def on_mount(self) -> None:
        await self._render_entries()
        self.query_one("#cc-input", Input).focus()

    async def _render_entries(self, query: str = "") -> None:
        needle = query.lower().strip()
        matches = [
            entry
            for entry in self.entries
            if not needle
            or needle in entry["label"].lower()
            or needle in entry["value"].lower()
        ]
        list_view = self.query_one("#cc-results", ListView)
        list_view.clear()
        self.rendered_entries = []
        last_provider: str | None = None

        for entry in matches:
            if entry["type"] == "model" and entry["provider"] != last_provider:
                last_provider = entry["provider"]
                list_view.append(ListItem(Static(f"[bold cyan]{last_provider}[/bold cyan]")))
                self.rendered_entries.append(None)
            if entry["type"] == "command" and last_provider is not None:
                last_provider = None
                list_view.append(ListItem(Static("")))
                self.rendered_entries.append(None)

            marker = "▶ " if entry["value"] == self.current_model else "  "
            icon = "◆" if entry["type"] == "model" else "/"
            list_view.append(ListItem(Static(f"{marker}{icon} {entry['label']}")))
            self.rendered_entries.append(entry)

    def on_input_changed(self, event: Input.Changed) -> None:
        asyncio.create_task(self._render_entries(event.value))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        index = event.list_view.index
        if index is None or index < 0 or index >= len(self.rendered_entries):
            return
        entry = self.rendered_entries[index]
        if entry is not None:
            self.dismiss(entry["data"])

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(None)


class NeoSwarmTUI(App[None]):
    """A local-first chat workspace backed by the NeoSwarm streaming API."""

    CSS = """
    Screen { background: $surface; }
    #main { height: 1fr; }
    #sidebar { width: 30; border: solid cyan; background: $panel; }
    #sidebar Label { padding: 0 1; text-style: bold; }
    #sessions-list { height: 1fr; margin: 0 1; }
    #sessions-list ListItem { padding: 0 1; }
    #sessions-list ListItem:hover { background: $boost; }
    #chat-panel { width: 1fr; border: solid green; }
    #chat-header { padding: 0 1; background: $panel; }
    #chat-history { height: 1fr; }
    #chat-input { dock: bottom; height: 3; }
    #activity-panel { width: 34; border: solid yellow; background: $panel; }
    #activity-header { padding: 0 1; background: $panel; text-style: bold; }
    #activity-text { padding: 1; }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+n", "new_session", "New"),
        Binding("ctrl+p", "command_center", "Command"),
        Binding("ctrl+m", "command_center", "Models"),
        Binding("ctrl+s", "toggle_sidebar", "Sessions"),
        Binding("ctrl+a", "toggle_activity", "Activity"),
        Binding("ctrl+r", "refresh", "Refresh"),
        Binding("ctrl+d", "delete_session", "Delete"),
    ]

    def __init__(self, backend_url: str = BACKEND_URL):
        super().__init__()
        self.client = BackendClient(backend_url)
        self.state = TuiState()
        self.available_models: dict[str, list[dict]] = {}
        self.current_model = "sonnet"
        self.current_provider = "anthropic"
        self._session_ids_in_view: list[str] = []
        self._event_task: asyncio.Task | None = None
        self._event_stop: asyncio.Event | None = None
        self._watched_session_id: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main"):
            with Horizontal():
                with Vertical(id="sidebar"):
                    yield Label("Sessions")
                    yield ListView(id="sessions-list")
                    yield Static("^N new · ^P commands", id="session-hint")
                with Vertical(id="chat-panel"):
                    yield Static(id="chat-header")
                    yield TA(id="chat-history")
                    yield Input(
                        placeholder="Message NeoSwarm, or type /help...",
                        id="chat-input",
                    )
                with Vertical(id="activity-panel"):
                    yield Static("Activity", id="activity-header")
                    yield Static(id="activity-text")
        yield Footer()

    async def on_mount(self) -> None:
        await self.refresh_backend()
        self.query_one("#chat-input", Input).focus()

    def on_unmount(self) -> None:
        self._stop_event_stream()

    async def refresh_backend(self) -> None:
        if not await self.client.health():
            self.state.connection_status = "offline"
            self.state.connection_detail = f"Cannot reach {self.client.backend_url}"
            self.render_all()
            return

        try:
            self.available_models = await self.client.models()
            self.state.replace_sessions(await self.client.sessions())
        except BackendRequestError as exc:
            self.state.connection_status = "offline"
            self.state.connection_detail = str(exc)
            self.render_all()
            return

        self.state.connection_status = "connected"
        active = self.state.active_session()
        if active:
            self.current_model = active.get("model", self.current_model)
            self.current_provider = active.get("provider", self.current_provider)
            self._watch_session(active["id"])
        self.render_all()

    def render_all(self) -> None:
        self._render_sessions()
        self._render_chat()
        self._render_activity()

    def _render_sessions(self) -> None:
        list_view = self.query_one("#sessions-list", ListView)
        list_view.clear()
        ordered = sorted(
            self.state.sessions.values(),
            key=lambda item: item.get("created_at", ""),
            reverse=True,
        )
        self._session_ids_in_view = []
        if not ordered:
            list_view.append(ListItem(Static("  No sessions yet")))
            return
        for session in ordered:
            session_id = session["id"]
            self._session_ids_in_view.append(session_id)
            active = session_id == self.state.active_session_id
            marker = "▶" if active else " "
            title = str(session.get("name") or "Untitled")[:20]
            status = str(session.get("status", "idle"))
            model = str(session.get("model", "?"))[:12]
            list_view.append(
                ListItem(Static(f"{marker} {title}\n  {model} · {status}"))
            )

    def _render_chat(self) -> None:
        session = self.state.active_session()
        header = self.query_one("#chat-header", Static)
        history = self.query_one("#chat-history", TA)
        if not session:
            header.update("[bold]Chat[/bold] — start a new session with ^N")
            history.text = ""
            return

        header.update(
            f"[bold]Chat[/bold]  {session.get('provider', self.current_provider)}/"
            f"{session.get('model', self.current_model)}  ·  {session.get('status', 'idle')}"
        )
        lines: list[str] = []
        for message in self.state.messages_for():
            if message.get("hidden"):
                continue
            role = message.get("role", "system")
            content = self._format_message_content(message.get("content"))
            if role == "user":
                lines.append(f"You: {content}")
            elif role == "assistant":
                lines.append(f"Neo: {content}")
            elif role == "thinking":
                lines.append(f"Thinking: {content}")
            elif role == "tool_call":
                lines.append(f"▸ Tool: {content}")
            elif role == "tool_result":
                lines.append(f"↳ Result: {content}")
            else:
                lines.append(f"[{role}] {content}")
        history.text = "\n\n".join(lines)

    def _render_activity(self) -> None:
        panel = self.query_one("#activity-text", Static)
        session = self.state.active_session()
        lines = [f"Connection: {self.state.connection_status}"]
        if self.state.connection_detail:
            lines.append(self.state.connection_detail[:180])
        lines.append("")
        if session:
            lines.extend(
                [
                    f"Model: {session.get('provider', self.current_provider)}/{session.get('model', self.current_model)}",
                    f"Status: {session.get('status', 'idle')}",
                    f"Cost: ${float(session.get('cost_usd', 0) or 0):.4f}",
                ]
            )
            approvals = self.state.pending_approvals.get(session["id"], [])
            if approvals:
                lines.extend(["", "Approvals:"])
                for approval in approvals:
                    lines.append(f"• {approval.get('tool_name', 'Tool')}")
                lines.append("/approve or /deny [reason]")
        else:
            lines.append("No active session")
        panel.update("\n".join(lines))

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            return
        event.input.clear()
        if text.startswith("/"):
            await self._handle_command(text)
        else:
            await self.send_message(text)

    async def _handle_command(self, command: str) -> None:
        name, _, argument = command.partition(" ")
        argument = argument.strip()
        if name == "/new":
            self.action_new_session()
        elif name == "/model":
            if argument:
                self._select_model(argument)
            else:
                await self.action_command_center()
        elif name == "/refresh":
            await self.refresh_backend()
        elif name == "/sidebar":
            self.action_toggle_sidebar()
        elif name in {"/output", "/activity"}:
            self.action_toggle_activity()
        elif name == "/delete":
            await self.action_delete_session()
        elif name == "/approve":
            await self._resolve_approval("allow")
        elif name == "/deny":
            await self._resolve_approval("deny", argument or None)
        elif name == "/help":
            self.state.connection_detail = "Commands: /new /model /refresh /delete /approve /deny"
            self.render_all()
        else:
            self.state.connection_detail = f"Unknown command: {name}. Try /help."
            self.render_all()

    async def send_message(self, prompt: str) -> None:
        session = self.state.active_session()
        if session is None:
            session = await self.create_session()
            if session is None:
                return
        try:
            await self.client.send(
                session["id"],
                {
                    "prompt": prompt,
                    "model": self.current_model,
                    "provider": self.current_provider,
                },
            )
            self.state.upsert_session(await self.client.session(session["id"]))
            self._watch_session(session["id"])
        except BackendRequestError as exc:
            self.state.connection_detail = str(exc)
        self.render_all()

    async def create_session(self) -> dict[str, Any] | None:
        try:
            session = await self.client.launch(
                {
                    "name": "TUI chat",
                    "model": self.current_model,
                    "mode": "chat",
                    "provider": self.current_provider,
                }
            )
        except BackendRequestError as exc:
            self.state.connection_detail = str(exc)
            self.render_all()
            return None
        self.state.upsert_session(session, activate=True)
        self._watch_session(session["id"])
        self.render_all()
        return session

    async def _resolve_approval(self, behavior: str, message: str | None = None) -> None:
        session = self.state.active_session()
        if session is None:
            return
        approvals = self.state.pending_approvals.get(session["id"], [])
        if not approvals:
            self.state.connection_detail = "No approval is waiting."
            self.render_all()
            return
        request_id = approvals[0].get("id")
        if not isinstance(request_id, str):
            return
        try:
            await self.client.respond_to_approval(request_id, behavior, message)
            self.state.resolve_approval(session["id"], request_id)
        except (BackendRequestError, ValueError) as exc:
            self.state.connection_detail = str(exc)
        self.render_all()

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "sessions-list":
            return
        index = event.list_view.index
        if index is None or index < 0 or index >= len(self._session_ids_in_view):
            return
        session_id = self._session_ids_in_view[index]
        self.state.activate(session_id)
        session = self.state.active_session()
        if session:
            self.current_model = session.get("model", self.current_model)
            self.current_provider = session.get("provider", self.current_provider)
            self._watch_session(session_id)
        self.render_all()

    def action_new_session(self) -> None:
        self.state.activate(None)
        self._stop_event_stream()
        self.render_all()
        self.query_one("#chat-input", Input).focus()

    async def action_command_center(self) -> None:
        if not self.available_models:
            self.state.connection_detail = "No models are available. Check provider settings."
            self.render_all()
            return
        result = await self.push_screen_wait(
            CommandCenter(self.available_models, self.current_model)
        )
        if isinstance(result, dict):
            self.current_model = str(result.get("value", self.current_model))
            self.current_provider = self._provider_id(str(result.get("provider", "")))
            self.state.connection_detail = (
                f"Selected {self.current_provider}/{self.current_model}"
            )
            self.render_all()
        elif isinstance(result, str):
            await self._handle_command(result)

    def _select_model(self, query: str) -> None:
        needle = query.lower()
        for provider, models in self.available_models.items():
            for model in models:
                value = str(model.get("value", ""))
                label = str(model.get("label", value))
                if needle in value.lower() or needle in label.lower():
                    self.current_model = value
                    self.current_provider = self._provider_id(provider)
                    self.state.connection_detail = (
                        f"Selected {self.current_provider}/{self.current_model}"
                    )
                    self.render_all()
                    return
        self.state.connection_detail = f"Model '{query}' was not found."
        self.render_all()

    async def action_delete_session(self) -> None:
        session = self.state.active_session()
        if session is None:
            return
        try:
            await self.client.delete(session["id"])
        except BackendRequestError as exc:
            self.state.connection_detail = str(exc)
            self.render_all()
            return
        self._stop_event_stream()
        self.state.remove_session(session["id"])
        active = self.state.active_session()
        if active:
            self._watch_session(active["id"])
        self.render_all()

    def action_toggle_sidebar(self) -> None:
        sidebar = self.query_one("#sidebar")
        sidebar.display = not sidebar.display

    def action_toggle_activity(self) -> None:
        panel = self.query_one("#activity-panel")
        panel.display = not panel.display

    async def action_refresh(self) -> None:
        await self.refresh_backend()

    def _watch_session(self, session_id: str) -> None:
        if (
            self._event_task
            and not self._event_task.done()
            and self._event_stop
            and not self._event_stop.is_set()
            and self._watched_session_id == session_id
        ):
            return
        self._stop_event_stream()
        stop = asyncio.Event()
        self._event_stop = stop
        self._watched_session_id = session_id
        self._event_task = asyncio.create_task(self._consume_session_events(session_id, stop))

    def _stop_event_stream(self) -> None:
        if self._event_stop:
            self._event_stop.set()
        if self._event_task and not self._event_task.done():
            self._event_task.cancel()
        self._event_stop = None
        self._event_task = None
        self._watched_session_id = None

    async def _consume_session_events(self, session_id: str, stop: asyncio.Event) -> None:
        try:
            async for event in self.client.session_events(session_id, stop):
                if event.event == "connection:open":
                    try:
                        self.state.upsert_session(await self.client.session(session_id))
                    except BackendRequestError:
                        pass
                self.state.apply(session_id, event)
                self.render_all()
        except asyncio.CancelledError:
            return

    @staticmethod
    def _provider_id(provider: str) -> str:
        return {
            "google": "google",
            "github models": "copilot",
        }.get(provider.lower(), provider.lower() or "anthropic")

    @staticmethod
    def _format_message_content(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            if "text" in content:
                return str(content["text"])
            if "tool" in content:
                tool_input = content.get("input", {})
                rendered = json.dumps(tool_input, ensure_ascii=False)
                return f"{content['tool']} {rendered[:500]}"
            return json.dumps(content, ensure_ascii=False)[:800]
        if isinstance(content, list):
            return json.dumps(content, ensure_ascii=False)[:800]
        return str(content)


def run_tui() -> None:
    NeoSwarmTUI(backend_url=BACKEND_URL).run()


if __name__ == "__main__":
    run_tui()
