"""Process commands that work in source and frozen backend runtimes."""

from __future__ import annotations

import sys
from pathlib import Path


_INTERNAL_MODULES = {
    "browser-agent-mcp": "browser_agent_mcp_server.py",
    "invoke-agent-mcp": "invoke_agent_mcp_server.py",
}


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def internal_server_command(name: str) -> tuple[str, list[str]]:
    """Return a stdio MCP command for development or PyInstaller runtime."""
    if name not in _INTERNAL_MODULES:
        raise ValueError(f"Unknown internal server: {name}")
    if is_frozen():
        return sys.executable, ["--internal", name]

    agents_dir = Path(__file__).resolve().parents[1] / "apps" / "agents"
    return sys.executable, [str(agents_dir / _INTERNAL_MODULES[name])]


def isolated_python_command(
    code: str, input_data: dict
) -> tuple[list[str], bytes]:
    """Return command/stdin for executing output code in a child process."""
    import json

    if is_frozen():
        payload = json.dumps({"code": code, "input_data": input_data}).encode()
        return [sys.executable, "--internal", "python-exec"], payload
    return [sys.executable, "-c", code], json.dumps(input_data).encode()
