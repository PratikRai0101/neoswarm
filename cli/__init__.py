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
import sys
from typing import Optional
from rich.console import Console

import click
import httpx
from rich.console import Console
from rich.table import Table

console = Console()


def get_backend_url() -> str:
    """Get backend URL from env or default."""
    return os.environ.get("NEOSWARM_URL", "http://localhost:8324")


async def check_backend() -> bool:
    """Check if backend is running."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{get_backend_url()}/api/health/check", timeout=5.0
            )
            return resp.status_code == 200
    except Exception:
        return False


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """NeoSwarm - Your local AI agent orchestrator."""
    pass


@cli.command()
@click.option("--model", "-m", default="sonnet", help="Model to use")
@click.option("--stream/--no-stream", default=True, help="Stream responses")
def chat(model: str, stream: bool):
    """Start an interactive chat."""
    console.print("[green]🐝 NeoSwarm Chat[/green]")
    console.print(f"[dim]Model: {model} | Backend: {get_backend_url()}[/dim]")
    console.print("[dim]Type 'exit' to quit[/dim]\n")

    async def run():
        if not await check_backend():
            console.print(
                "[red]✗ Backend not running. Start with: neoswarm server[/red]"
            )
            return

        async with httpx.AsyncClient() as client:
            session_id = None
            while True:
                prompt = await console.input("[cyan]> [/cyan]")
                if not prompt or prompt.lower() == "exit":
                    break

                if not session_id:
                    resp = await client.post(
                        f"{get_backend_url()}/api/agents/sessions",
                        json={"model": model, "mode": "chat"},
                    )
                    if resp.status_code == 200:
                        session_id = resp.json().get("id")

                if session_id:
                    resp = await client.post(
                        f"{get_backend_url()}/api/agents/sessions/{session_id}/prompt",
                        json={"prompt": prompt},
                    )
                    if resp.status_code == 200:
                        console.print("[green]✓[/green]")

    asyncio.run(run())


@cli.command()
@click.argument("mission")
@click.option("--model", "-m", default="sonnet", help="Model to use")
@click.option("--workers", "-w", default=3, help="Number of workers")
def launch(mission: str, model: str, workers: int):
    """Launch a mission with the orchestrator."""
    console.print(f"[green]🐝 Launching: {mission}[/green]")
    console.print(f"[dim]Model: {model} | Workers: {workers}[/dim]")

    async def run():
        if not await check_backend():
            console.print("[red]✗ Backend not running[/red]")
            return

        console.print("[cyan]→ Decomposing mission...[/cyan]")
        console.print("[yellow]TODO: Connect to orchestrator API[/yellow]")
        console.print(f"[green]✓ Mission launched[/green]")

    asyncio.run(run())


@cli.command()
def status():
    """Show current session status."""
    console.print("[green]🐝 Session Status[/green]\n")

    async def run():
        if not await check_backend():
            console.print("[red]✗ Backend not running[/red]")
            return

        table = Table(title="Active Sessions")
        table.add_column("ID", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Model", style="yellow")

        table.add_row("sample-123", "running", "sonnet")

        console.print(table)

    asyncio.run(run())


@cli.command()
def sessions():
    """List all sessions."""
    console.print("[green]🐝 Sessions[/green]\n")

    async def run():
        if not await check_backend():
            console.print("[red]✗ Backend not running[/red]")
            return

        table = Table(title="All Sessions")
        table.add_column("ID", style="cyan")
        table.add_column("Mission", style="white")
        table.add_column("Status", style="green")
        table.add_column("Workers", style="yellow")

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
@click.option("--provider", "-p", type=click.Choice(["anthropic", "openai", "google", "ollama", "openrouter"]), help="Provider to remove")
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
    """Start the NeoSwarm backend server."""
    console.print("[green]🐝 Starting backend...[/green]")
    os.system(
        "cd backend && source .venv/bin/activate && PYTHONPATH=. uvicorn main:app --host 127.0.0.1 --port 8324"
    )


if __name__ == "__main__":
    cli()
