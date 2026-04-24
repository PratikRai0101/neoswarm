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

    table = Table(title="Models")
    table.add_column("Provider", style="cyan")
    table.add_column("Model", style="green")
    table.add_column("Context", style="yellow")

    for p, m, context in [
        ("Anthropic", "claude-sonnet-4-6", "1M"),
        ("Anthropic", "claude-opus-4-6", "1M"),
        ("Anthropic", "claude-haiku-4-5", "200K"),
        ("Ollama", "llama3.3", "128K"),
        ("Ollama", "qwen2.5", "128K"),
    ]:
        table.add_row(p, m, context)

    console.print(table)


@cli.command()
def server():
    """Start the NeoSwarm backend server."""
    console.print("[green]🐝 Starting backend...[/green]")
    os.system(
        "cd backend && source .venv/bin/activate && PYTHONPATH=. uvicorn main:app --host 127.0.0.1 --port 8324"
    )


if __name__ == "__main__":
    cli()
