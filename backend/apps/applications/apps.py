"""Host-SDK REST API for vibe-coded apps."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from backend.config.Apps import SubApp
from backend.apps.applications import grants, identity
from backend.config.paths import OUTPUTS_WORKSPACE_DIR as WORKSPACE_DIR

logger = logging.getLogger(__name__)

# Our static serve paths embed the app id, and the browser owns the Referer
# header — a page cannot fake its own Referer, making this as trustworthy as
# the webview boundary. Matches /api/outputs/<id>/serve/… and
# /api/outputs/workspace/<workspace_id>/serve/…
SERVE_REFERER_RE = re.compile(r"/api/outputs/(?:workspace/)?([^/?#]+)/serve/")


@asynccontextmanager
async def apps_lifespan():
    os.makedirs(identity.APPS_DIR, exist_ok=True)
    yield


apps = SubApp("apps", apps_lifespan)


def resolve_app_from_referer(referer: str) -> Optional[str]:
    match = SERVE_REFERER_RE.search(referer or "")
    return match.group(1) if match else None


def _app_exists(app_id: str) -> tuple[bool, str]:
    """Check an app id names a real output or workspace. Returns (exists, name)."""
    from backend.apps.outputs.outputs import load_output

    try:
        output = load_output(app_id)
        if output is not None:
            return True, output.name or app_id
    except Exception:
        pass
    folder = os.path.join(WORKSPACE_DIR, app_id)
    if os.path.isdir(folder):
        meta_name = app_id
        try:
            with open(os.path.join(folder, "meta.json"), encoding="utf-8") as handle:
                meta_name = json.load(handle).get("name", app_id)
        except Exception:
            pass
        return True, meta_name
    return False, app_id


class TokenRequest(BaseModel):
    output_id: str = Field(description="Output id or workspace id to mint a token for.")


@apps.router.post("/token")
async def mint_token(body: TokenRequest):
    """Mint (or reuse) the calling app's token. The app stores it and sends
    it back as `app_token` or an `X-NeoSwarm-App-Token` header."""
    exists, _ = _app_exists(body.output_id)
    if not exists:
        raise HTTPException(status_code=404, detail="Unknown output or workspace")
    return {"token": identity.mint_app_token(body.output_id)}


@apps.router.delete("/token/{app_id}")
async def revoke_token(app_id: str):
    identity.revoke_app_token(app_id)
    grants.clear_grants(app_id)
    return {"ok": True}


class LlmRequest(BaseModel):
    prompt: str
    system: str = "You are a helpful assistant embedded in a user-built app. Answer concisely."
    max_tokens: int = 1024
    model: Optional[str] = None
    provider: Optional[str] = None
    app_token: Optional[str] = None


@apps.router.post("/llm")
async def app_llm(body: LlmRequest):
    """Host model call for apps (provider-agnostic, billed to host creds)."""
    if not body.prompt.strip():
        raise HTTPException(status_code=422, detail="prompt is empty")
    from backend.apps.agents.auxiliary import generate_auxiliary_text

    try:
        text = await generate_auxiliary_text(
            body.prompt,
            system=body.system,
            max_tokens=max(1, min(body.max_tokens, 4096)),
            preferred_tier="capable",
            model=body.model or None,
            provider=body.provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=402, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM call failed: {exc}") from exc
    return {"text": text}


@apps.router.post("/tools/list")
async def tools_list():
    """Tool servers an app may ask to use: the same enabled, configured set
    agents see. Calls go through the per-app grant gate."""
    from backend.apps.tools_lib.tools_lib import _load_all

    rows = [
        {"id": tool.id, "name": tool.name, "description": (tool.description or "")[:200]}
        for tool in _load_all()
        if tool.mcp_config and tool.enabled and tool.auth_status in ("configured", "connected")
    ]
    return {"servers": rows}


class ToolCallRequest(BaseModel):
    app_token: Optional[str] = None
    output_id: Optional[str] = None
    tool: str = Field(description="'<tool_id>:<ToolName>' from /tools/list")
    args: dict[str, Any] = Field(default_factory=dict)


def _resolve_caller(request: Request, body: ToolCallRequest) -> Optional[str]:
    header_token = request.headers.get("x-neoswarm-app-token", "")
    return (
        identity.resolve_app_token(body.app_token or "")
        or identity.resolve_app_token(header_token)
        or resolve_app_from_referer(request.headers.get("referer", ""))
    )


@apps.router.post("/tools/call")
async def tools_call(body: ToolCallRequest, request: Request):
    """Grant-gated tool call: denied refuses flat, ungranted asks the user on
    an approval card, granted dispatches through the agent MCP path."""
    app_id = _resolve_caller(request, body)
    if not app_id:
        raise HTTPException(
            status_code=403,
            detail="Could not identify the calling app; tool access is per-app.",
        )
    tool_id, sep, tool_name = body.tool.partition(":")
    if not sep or not tool_id or not tool_name:
        raise HTTPException(
            status_code=422, detail="tool must be '<tool_id>:<ToolName>' from /tools/list"
        )
    status = grants.grant_status(app_id, body.tool)
    if status == "denied":
        raise HTTPException(
            status_code=403, detail=f"The user has denied this app access to {tool_name}."
        )
    if status != "granted":
        _, app_name = _app_exists(app_id)
        allowed = await grants.request_grant(
            app_id, app_name, body.tool, tool_name, json.dumps(body.args)[:400]
        )
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail=f"The user did not approve this app using {tool_name}.",
            )

    from backend.apps.agents.mcp_client import MCPClientManager
    from backend.apps.tools_lib.tools_lib import _load, derive_mcp_config

    try:
        tool = _load(tool_id)
    except HTTPException as exc:
        raise HTTPException(status_code=404, detail="Unknown tool server") from exc
    config = derive_mcp_config(tool)
    if not config:
        raise HTTPException(status_code=400, detail="Tool server cannot be configured")
    server_name = f"app-{app_id[:8]}-{tool.id[:8]}"
    try:
        async with MCPClientManager() as manager:
            connected = await manager.connect(server_name, config)
            if not connected:
                raise HTTPException(status_code=502, detail="Could not reach the tool server")
            blocks = await manager.call_tool(server_name, tool_name, body.args)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Tool call failed: {exc}") from exc
    texts = [str(b.get("text", "")) for b in blocks if isinstance(b, dict)]
    return {"result": "\n".join(t for t in texts if t)}


class GrantResolveRequest(BaseModel):
    request_id: str
    allow: bool
    remember: bool = False


@apps.router.post("/tools/grant")
async def resolve_tool_grant(body: GrantResolveRequest):
    return {"ok": grants.resolve_grant(body.request_id, body.allow, body.remember)}


@apps.router.get("/tools/grants/{app_id}")
async def get_tool_grants(app_id: str):
    return {"grants": grants.list_grants(app_id)}


@apps.router.delete("/tools/grants/{app_id}")
async def reset_tool_grants(app_id: str):
    grants.clear_grants(app_id)
    return {"ok": True}


class SpawnAgentRequest(BaseModel):
    prompt: str
    name: str = "Agent"
    model: Optional[str] = None
    dashboard_id: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None


@apps.router.post("/agents/spawn")
async def spawn_agent(body: SpawnAgentRequest):
    """Spawn an agent from an app. Falls back to the most-recent dashboard so
    the spawn is visible instead of orphaned."""
    if not body.prompt.strip():
        raise HTTPException(status_code=422, detail="prompt is empty")
    from backend.apps.agents.agent_manager import agent_manager
    from backend.apps.agents.models import AgentConfig
    from backend.apps.agents.ws_manager import ws_manager

    dashboard_id = body.dashboard_id
    if dashboard_id is None:
        from backend.apps.dashboards.dashboards import _load_all

        try:
            boards = sorted(_load_all(), key=lambda d: d.updated_at or d.created_at, reverse=True)
            dashboard_id = boards[0].id if boards else None
        except Exception:
            dashboard_id = None
    config = AgentConfig(
        name=body.name,
        model=body.model or "sonnet",
        dashboard_id=dashboard_id,
    )
    session = await agent_manager.launch_agent(config)
    asyncio.create_task(agent_manager.send_message(session.id, body.prompt))
    if body.x is not None and body.y is not None:
        await ws_manager.broadcast_global("apps:place_agent_card", {
            "session_id": session.id,
            "dashboard_id": dashboard_id,
            "x": body.x,
            "y": body.y,
        })
    return {"session_id": session.id}
