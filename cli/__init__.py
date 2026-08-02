#!/usr/bin/env python3
"""NeoSwarm CLI - Command line interface for your AI agent swarm.

Usage:
    neoswarm chat                 Start interactive chat
    neoswarm launch "mission"     Launch a mission
    neoswarm status             Show session status
    neoswarm sessions          List all sessions
    neoswarm models            Show available models
"""

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Any, Optional

import click
import httpx
import websockets
from websockets.exceptions import WebSocketException
from rich.console import Console
from rich.table import Table

from cli.tui_client import BackendClient, BackendRequestError, decode_event, websocket_url

console = Console()


def get_backend_url() -> str:
    """Get backend URL from env or default."""
    return os.environ.get("NEOSWARM_URL", "http://localhost:8324")


async def check_backend() -> bool:
    """Check if backend is running."""
    return await BackendClient(get_backend_url()).health()


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return str(content.get("text") or content.get("tool") or content)
    return str(content)


async def _stream_turn(client: BackendClient, session_id: str, payload: dict[str, Any]) -> None:
    """Send one turn while printing normalized WebSocket events."""
    url = websocket_url(get_backend_url(), f"/ws/agents/{session_id}")
    streamed_text = False
    async with websockets.connect(url, ping_interval=20) as socket:
        await client.send(session_id, payload)
        async for raw in socket:
            event = decode_event(raw)
            if event.event == "agent:stream_delta":
                delta = event.data.get("delta", "")
                if isinstance(delta, str):
                    console.print(delta, end="")
                    streamed_text = True
            elif event.event == "agent:message":
                message = event.data.get("message", {})
                if not isinstance(message, dict):
                    continue
                role = message.get("role")
                content = message.get("content")
                if role == "tool_call" and isinstance(content, dict):
                    console.print(f"\n[dim]▸ {content.get('tool', 'tool')}[/dim]")
                elif role == "tool_result" and isinstance(content, dict):
                    tool_name = content.get("tool_name", "tool")
                    result = str(content.get("text", ""))[:500]
                    console.print(f"\n[dim]↳ {tool_name}: {result}[/dim]")
                elif role == "assistant" and not streamed_text:
                    console.print(_message_text(content))
            elif event.event == "agent:status":
                status = event.data.get("status")
                if status in {"completed", "stopped", "error"}:
                    if streamed_text:
                        console.print()
                    return


async def _wait_for_session(client: BackendClient, session_id: str) -> dict[str, Any]:
    """Wait for a session turn to reach a terminal state."""
    while True:
        session = await client.session(session_id)
        if session.get("status") not in {"running", "waiting_approval"}:
            return session
        await asyncio.sleep(0.25)


async def _wait_for_mission(client: BackendClient, mission_id: str) -> dict[str, Any]:
    """Poll a mission until it completes, fails, or is cancelled."""
    last_status = None
    while True:
        mission = await client.mission(mission_id)
        status = mission.get("status")
        if status != last_status:
            console.print(f"[cyan]→ Mission status: {status}[/cyan]")
            last_status = status
        if status in {"completed", "failed", "cancelled"}:
            return mission
        await asyncio.sleep(0.5)


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """NeoSwarm - Your local AI agent orchestrator."""
    pass


@cli.command()
@click.option("--model", "-m", default="sonnet", help="Model to use")
@click.option("--stream/--no-stream", default=True, help="Stream responses")
def chat(model: str, stream: bool):
    """Start an interactive chat against the backend session API."""
    console.print("[green]🐝 NeoSwarm Chat[/green]")
    console.print(f"[dim]Model: {model} | Backend: {get_backend_url()}[/dim]")
    console.print("[dim]Type 'exit' to quit[/dim]\n")

    async def run():
        client = BackendClient(get_backend_url())
        if not await client.health():
            console.print("[red]✗ Backend not running. Start with: neoswarm server[/red]")
            return

        session_id: str | None = None
        while True:
            prompt = console.input("[cyan]> [/cyan]").strip()
            if not prompt or prompt.lower() == "exit":
                break

            try:
                if session_id is None:
                    session = await client.launch({
                        "name": "CLI chat",
                        "model": model,
                        "mode": "agent",
                    })
                    session_id = str(session["id"])

                payload = {"prompt": prompt, "model": model}
                if stream:
                    await _stream_turn(client, session_id, payload)
                else:
                    await client.send(session_id, payload)
                    session = await _wait_for_session(client, session_id)
                    message = next(
                        (
                            item
                            for item in reversed(session.get("messages", []))
                            if item.get("role") in {"assistant", "system"}
                        ),
                        None,
                    )
                    if message:
                        console.print(_message_text(message.get("content")))
            except (BackendRequestError, OSError, WebSocketException) as exc:
                console.print(f"[red]✗ {exc}[/red]")
                return

    asyncio.run(run())


@cli.command()
@click.argument("mission")
@click.option("--model", "-m", default="sonnet", help="Model to use")
@click.option("--workers", "-w", default=3, type=click.IntRange(1, 8), help="Number of workers")
@click.option("--execution-mode", type=click.Choice(["parallel", "sequential"]), default="parallel", show_default=True)
@click.option("--provider", default=None, help="Provider override")
@click.option("--directory", default=None, help="Working directory for workers")
@click.option("--isolate-workers/--shared-workers", default=False, help="Use isolated git worktrees")
def launch(mission: str, model: str, workers: int, execution_mode: str, provider: str | None, directory: str | None, isolate_workers: bool):
    """Launch and monitor a mission with the orchestrator."""
    console.print(f"[green]🐝 Launching: {mission}[/green]")
    console.print(f"[dim]Model: {model} | Workers: {workers} | Mode: {execution_mode}[/dim]")

    async def run():
        client = BackendClient(get_backend_url())
        if not await client.health():
            console.print("[red]✗ Backend not running. Start with: neoswarm server[/red]")
            return
        try:
            mission_data = await client.create_mission({
                "mission": mission,
                "workers": workers,
                "model": model,
                "provider": provider,
                "execution_mode": execution_mode,
                "target_directory": directory,
                "isolate_workers": isolate_workers,
            })
            mission_id = str(mission_data["id"])
            await client.start_mission(mission_id)
            result = await _wait_for_mission(client, mission_id)
        except BackendRequestError as exc:
            console.print(f"[red]✗ {exc}[/red]")
            return

        if result.get("status") == "completed":
            console.print("[green]✓ Mission completed[/green]")
        else:
            console.print(f"[red]✗ Mission {result.get('status')}[/red]")
        if result.get("final_result"):
            console.print(result["final_result"])

    asyncio.run(run())


@cli.command()
def status():
    """Show currently active agent sessions."""
    console.print("[green]🐝 Session Status[/green]\n")

    async def run():
        client = BackendClient(get_backend_url())
        if not await client.health():
            console.print("[red]✗ Backend not running[/red]")
            return
        try:
            sessions = await client.sessions()
        except BackendRequestError as exc:
            console.print(f"[red]✗ {exc}[/red]")
            return

        active = [s for s in sessions if s.get("status") in {"running", "waiting_approval"}]
        if not active:
            console.print("[dim]No active sessions.[/dim]")
            return
        table = Table(title="Active Sessions")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="white")
        table.add_column("Status", style="green")
        table.add_column("Provider/Model", style="yellow")
        for session in active:
            table.add_row(
                str(session.get("id", ""))[:12],
                str(session.get("name", "Untitled"))[:32],
                str(session.get("status", "")),
                f"{session.get('provider', '')}/{session.get('model', '')}",
            )
        console.print(table)

    asyncio.run(run())


@cli.command()
def sessions():
    """List persisted and active chat sessions."""
    console.print("[green]🐝 Sessions[/green]\n")

    async def run():
        client = BackendClient(get_backend_url())
        if not await client.health():
            console.print("[red]✗ Backend not running[/red]")
            return
        try:
            all_sessions = await client.sessions()
        except BackendRequestError as exc:
            console.print(f"[red]✗ {exc}[/red]")
            return

        table = Table(title="All Sessions")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="white")
        table.add_column("Status", style="green")
        table.add_column("Provider/Model", style="yellow")
        for session in all_sessions:
            table.add_row(
                str(session.get("id", ""))[:12],
                str(session.get("name", "Untitled"))[:32],
                str(session.get("status", "")),
                f"{session.get('provider', '')}/{session.get('model', '')}",
            )
        console.print(table)

    asyncio.run(run())


@cli.command()
def models():
    """Show available models."""
    console.print("[green]🐝 Available Models[/green]\n")

    async def run():
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(f"{get_backend_url()}/api/agents/models", timeout=10.0)
            except Exception:
                console.print("[red]Failed to fetch models[/red]")
                return
            
            if resp.status_code != 200:
                console.print("[red]Failed to fetch models[/red]")
                return
            
            data = resp.json()
            all_models = data.get("models", {})
            
            table = Table(title="Models")
            table.add_column("Provider", style="cyan")
            table.add_column("Model", style="green")
            table.add_column("Context", style="yellow")

            for provider, model_list in all_models.items():
                for m in model_list:
                    ctx = m.get("context_window", 128_000)
                    ctx_str = f"{ctx//1000}K" if ctx < 1000000 else f"{ctx//1000000}M"
                    table.add_row(provider, m.get("label", ""), ctx_str)

            console.print(table)

    asyncio.run(run())


@cli.group()
def auth():
    """Manage authentication and providers."""
    pass


@auth.command()
@click.option("--provider", "-p", default=None, help="Provider to configure")
@click.option("--api-key", "-k", default=None, help="API key for the provider")
def login(provider: Optional[str], api_key: Optional[str]):
    """Configure API credentials for a provider."""
    console.print("[green]🐝 NeoSwarm Auth - Login[/green]\n")

    if not provider:
        console.print("[cyan]Select provider:[/cyan]")
        console.print("  1. anthropic    - Anthropic (Claude)")
        console.print("  2. openai     - OpenAI")
        console.print("  3. google     - Google (Gemini)")
        console.print("  4. ollama     - Ollama (local)")
        console.print("  5. openrouter - OpenRouter")
        console.print("  6. copilot    - GitHub Copilot")
        choice = click.prompt("Enter choice", type=int, default=1, show_default=False)
        providers = ["anthropic", "openai", "google", "ollama", "openrouter", "copilot"]
        provider = providers[choice - 1]

    if provider == "copilot":
        client_id = "Ov23liLDz3MEPhK1969Z"
        console.print("[cyan]Starting GitHub device flow authentication...[/cyan]\n")
        
        async def run():
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://github.com/login/device/code",
                    data={"client_id": client_id, "scope": "copilot"},
                    headers={"Accept": "application/json"},
                )
                if resp.status_code != 200:
                    console.print(f"[red]Failed: {resp.status_code}[/red]")
                    return
                
                data = resp.json()
                device_code = data["device_code"]
                user_code = data["user_code"]
                verification_uri = data["verification_uri"]
                interval = int(data.get("interval", 5))
                
                console.print(f"\n[yellow]Step 1:[/yellow] Visit: {verification_uri}")
                console.print(f"[yellow]Step 2:[/yellow] Enter code: [bold cyan]{user_code}[/bold cyan]\n")
                console.print("[dim]Waiting for authentication...[/dim]\n")
                
                import webbrowser
                webbrowser.open(verification_uri)
                
                for i in range(120):
                    await asyncio.sleep(interval)
                    try:
                        resp = await client.post(
                            "https://github.com/login/oauth/access_token",
                            data={
                                "client_id": client_id,
                                "device_code": device_code,
                                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                            },
                            headers={"Accept": "application/json"},
                        )
                    except Exception:
                        continue
                    
                    if resp.status_code == 200:
                        token_data = resp.json()
                        if "access_token" in token_data:
                            access_token = token_data["access_token"]
                            
                            await client.put(
                                f"{get_backend_url()}/api/settings",
                                json={"copilot_github_token": access_token},
                            )
                            console.print(f"[green]✓ GitHub Copilot authenticated![/green]")
                            return
                        
                        error = token_data.get("error", "")
                        if error in ["expired_token", "slow_down"]:
                            console.print("[red]Authentication expired. Try again.[/red]")
                            return
                
                console.print("[red]Authentication timed out. Try again.[/red]")
        
        asyncio.run(run())
        return

    if not api_key and provider != "ollama":
        api_key = click.prompt(f"Enter API key for {provider}", hide_input=True)
        if not api_key:
            console.print("[red]API key required[/red]")
            return

    if provider == "ollama":
        console.print("[green]✓ Ollama configured (local, no API key needed)[/green]")
        async def run():
            if await check_backend():
                async with httpx.AsyncClient() as client:
                    settings = {"default_model": provider}
                    await client.put(f"{get_backend_url()}/api/settings", json=settings)
                    console.print("[green]✓ Saved to settings[/green]")
            else:
                console.print("[dim]Note: Ollama runs locally on port 11434[/dim]")
                console.print("[green]✓ Ollama ready (run 'ollama serve' to start)[/green]")
        asyncio.run(run())
        return

    provider_key_map = {
        "anthropic": "anthropic_api_key",
        "openai": "openai_api_key",
        "google": "google_api_key",
        "openrouter": "openrouter_api_key",
    }
    key = provider_key_map.get(provider, "")
    async def run():
        if not await check_backend():
            console.print("[red]✗ Backend not running. Start with: neoswarm server[/red]")
            return

        async with httpx.AsyncClient() as client:
            settings = {key: api_key}
            resp = await client.put(f"{get_backend_url()}/api/settings", json=settings)
            if resp.status_code == 200:
                console.print(f"[green]✓ {provider.title()} API key saved[/green]")
            else:
                console.print(f"[red]✗ Failed to save credentials[/red]")
    asyncio.run(run())


@auth.command()
@click.option("--provider", "-p", type=click.Choice(["anthropic", "openai", "google", "ollama", "openrouter", "copilot"]), help="Provider to remove")
def logout(provider: Optional[str]):
    """Remove API credentials."""
    console.print("[green]🐝 NeoSwarm Auth - Logout[/green]\n")

    if not provider:
        console.print("[yellow]Which provider to disconnect?[/yellow]")
        console.print("  anthropic, openai, google, ollama, openrouter, copilot")
        console.print("[dim]Use: neoswarm auth logout -p PROVIDER[/dim]")
        return

    provider_key_map = {
        "anthropic": "anthropic_api_key",
        "openai": "openai_api_key",
        "google": "google_api_key",
        "openrouter": "openrouter_api_key",
    }

    if provider == "copilot":
        async def run():
            async with httpx.AsyncClient() as client:
                resp = await client.put(
                    f"{get_backend_url()}/api/settings",
                    json={"copilot_github_token": None}
                )
                if resp.status_code == 200:
                    console.print("[green]✓ Copilot disconnected[/green]")
                else:
                    console.print("[red]Failed[/red]")
        asyncio.run(run())
        return

    key = provider_key_map.get(provider, "")

    if not key:
        console.print(f"[red]Unknown provider: {provider}[/red]")
        return

    async def run():
        if not await check_backend():
            console.print("[red]✗ Backend not running[/red]")
            return

        async with httpx.AsyncClient() as client:
            settings = {key: None}
            resp = await client.put(f"{get_backend_url()}/api/settings", json=settings)
            if resp.status_code == 200:
                console.print(f"[green]✓ {provider.title()} credentials removed[/green]")
            else:
                console.print(f"[red]✗ Failed to remove credentials[/red]")
    asyncio.run(run())


@auth.command()
def status():
    """Show connected providers."""
    console.print("[green]🐝 Provider Status[/green]\n")

    async def run():
        if not await check_backend():
            console.print("[red]✗ Backend not running[/red]")
            return

        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{get_backend_url()}/api/settings")
            if resp.status_code == 200:
                settings = resp.json()
                table = Table(title="Providers")
                table.add_column("Provider", style="cyan")
                table.add_column("Status", style="green")
                table.add_column("Default", style="yellow")

                providers = [
                    ("Anthropic", bool(settings.get("anthropic_api_key"))),
                    ("OpenAI", bool(settings.get("openai_api_key"))),
                    ("Google", bool(settings.get("google_api_key"))),
                    ("OpenRouter", bool(settings.get("openrouter_api_key"))),
                    ("Ollama", True),
                    ("Copilot", bool(settings.get("copilot_github_token"))),
                ]
                default_model = settings.get("default_model", "sonnet")

                for name, has_key in providers:
                    status_str = "[green]✓ Connected" if has_key else "[dim]Not configured[/dim]"
                    default_str = "[bold]*[/bold]" if (name.lower() == "anthropic" and default_model == "sonnet") or name.lower() == default_model else ""
                    table.add_row(name, status_str, default_str)

                console.print(table)
            else:
                console.print("[red]Failed to load settings[/red]")
    asyncio.run(run())


@cli.command()
def server():
    """Start the NeoSwarm backend server from the project root."""
    console.print("[green]🐝 Starting backend...[/green]")
    project_root = Path(__file__).resolve().parents[1]
    configured_python = os.environ.get("NEOSWARM_PYTHON")
    if configured_python:
        command = [configured_python, "-m", "uvicorn", "backend.main:app"]
    else:
        command = [str(project_root / "run-backend.sh")]
    subprocess.run(command, cwd=project_root, check=False)


if __name__ == "__main__":
    cli()
