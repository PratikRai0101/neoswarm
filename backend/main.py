import logging
import os
import threading
import time
from uuid import uuid4

logger = logging.getLogger(__name__)


def _start_parent_watchdog() -> None:
    """Exit a sidecar backend when the desktop process disappears.

    PyInstaller one-file executables use a bootloader parent, so checking only
    ``os.getppid()`` is insufficient. The Tauri launcher passes its PID and we
    monitor that process directly instead.
    """
    raw_parent_pid = os.environ.get("NEOSWARM_PARENT_PID")
    if not raw_parent_pid:
        return
    try:
        parent_pid = int(raw_parent_pid)
    except ValueError:
        return

    def monitor() -> None:
        while True:
            try:
                os.kill(parent_pid, 0)
            except OSError:
                os._exit(0)
            time.sleep(0.5)

    threading.Thread(target=monitor, name="neoswarm-parent-watchdog", daemon=True).start()


_start_parent_watchdog()

from fastapi.responses import JSONResponse
from fastapi import HTTPException, Request

from backend.config.Apps import MainApp
from backend.apps.health.health import health
from backend.apps.agents.agents import agents
from backend.apps.scheduler.schedules import schedules
from backend.apps.memory.memory import memory
from backend.apps.git.git import git
from backend.apps.agents.ws_manager import ws_manager
from backend.apps.skills.skills import skills
from backend.apps.tools_lib.tools_lib import tools_lib
from backend.apps.modes.modes import modes
from backend.apps.settings.settings import settings
from backend.apps.mcp_registry.mcp_registry import mcp_registry
from backend.apps.skill_registry.skill_registry import skill_registry
from backend.apps.outputs.outputs import outputs
from backend.apps.artifacts.artifacts import artifacts
from backend.apps.terminals.terminals import terminals, terminal_manager
from backend.apps.ssh.ssh import ssh
from backend.apps.images.images import images
from backend.apps.dashboards.dashboards import dashboards
from backend.apps.analytics.analytics import analytics
from fastapi.middleware.cors import CORSMiddleware
from fastapi import WebSocket, WebSocketDisconnect
import json

main_app = MainApp(
    [
        health,
        agents,
        schedules,
        memory,
        git,
        skills,
        tools_lib,
        modes,
        settings,
        mcp_registry,
        skill_registry,
        outputs,
        artifacts,
        terminals,
        ssh,
        images,
        dashboards,
        analytics,
    ]
)
app = main_app.app

_cors_origins = os.environ.get(
    "NEOSWARM_CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,tauri://localhost,http://tauri.localhost,https://tauri.localhost",
)
_allowed_origins = frozenset(
    origin.strip() for origin in _cors_origins.split(",") if origin.strip()
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(_allowed_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def reject_untrusted_browser_writes(request: Request, call_next):
    """Block cross-origin browser mutations against the loopback API.

    CORS prevents a hostile page from reading responses, but a ``no-cors``
    request can still send writes. Non-browser clients omit Origin and remain
    supported for the TUI and internal MCP subprocesses.
    """
    origin = request.headers.get("origin")
    if (
        request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and origin
        and origin not in _allowed_origins
    ):
        return JSONResponse({"detail": "Origin not allowed"}, status_code=403)
    return await call_next(request)


def _websocket_origin_allowed(websocket: WebSocket) -> bool:
    """Allow trusted browser origins and non-browser clients without Origin."""
    origin = websocket.headers.get("origin")
    return origin is None or origin in _allowed_origins


@app.websocket("/ws/terminals/{terminal_id}")
async def websocket_terminal(websocket: WebSocket, terminal_id: str):
    if not _websocket_origin_allowed(websocket):
        await websocket.close(code=1008, reason="Origin not allowed")
        return

    try:
        await terminal_manager.connect(terminal_id, websocket)
    except HTTPException:
        await websocket.close(code=1008, reason="Terminal not found")
        return

    try:
        while True:
            raw_message = await websocket.receive_text()
            try:
                message = json.loads(raw_message)
            except (json.JSONDecodeError, TypeError):
                await websocket.send_json({"event": "terminal:error", "data": {"error": "Invalid JSON message"}})
                continue
            if not isinstance(message, dict):
                await websocket.send_json({"event": "terminal:error", "data": {"error": "Message must be an object"}})
                continue
            try:
                response = await terminal_manager.handle_message(terminal_id, message)
            except (ValueError, TypeError) as exc:
                await websocket.send_json({"event": "terminal:error", "data": {"error": str(exc)}})
                continue
            if response:
                await websocket.send_json(response)
    except WebSocketDisconnect:
        pass
    finally:
        terminal_manager.disconnect(terminal_id, websocket)


@app.websocket("/ws/agents/{session_id}")
async def websocket_session(websocket: WebSocket, session_id: str):
    if not _websocket_origin_allowed(websocket):
        await websocket.close(code=1008, reason="Origin not allowed")
        return

    await ws_manager.connect_session(session_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                await websocket.send_json(
                    {"event": "error", "data": {"error": "Invalid JSON message"}}
                )
                continue
            if not isinstance(msg, dict):
                await websocket.send_json(
                    {"event": "error", "data": {"error": "Message must be an object"}}
                )
                continue
            event = msg.get("event")
            payload = msg.get("data", {})
            if not isinstance(payload, dict):
                await websocket.send_json(
                    {"event": "error", "data": {"error": "Message data must be an object"}}
                )
                continue

            if event == "agent:send_message":
                from backend.apps.agents.agent_manager import agent_manager

                await agent_manager.send_message(
                    session_id,
                    payload.get("prompt", ""),
                    mode=payload.get("mode"),
                    model=payload.get("model"),
                    provider=payload.get("provider"),
                    images=payload.get("images"),
                )
            elif event == "agent:approval_response":
                from backend.apps.agents.agent_manager import agent_manager

                agent_manager.handle_approval(
                    payload.get("request_id"),
                    {
                        "behavior": payload.get("behavior", "deny"),
                        "message": payload.get("message"),
                        "updated_input": payload.get("updated_input"),
                    },
                )
            elif event == "agent:edit_message":
                from backend.apps.agents.agent_manager import agent_manager

                await agent_manager.edit_message(
                    session_id,
                    payload.get("message_id", ""),
                    payload.get("content", ""),
                )
            elif event == "agent:stop":
                from backend.apps.agents.agent_manager import agent_manager

                await agent_manager.stop_agent(session_id)
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect_session(session_id, websocket)


@app.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    if not _websocket_origin_allowed(websocket):
        await websocket.close(code=1008, reason="Origin not allowed")
        return

    await ws_manager.connect_global(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                await websocket.send_json(
                    {"event": "error", "data": {"error": "Invalid JSON message"}}
                )
                continue
            if not isinstance(msg, dict):
                await websocket.send_json(
                    {"event": "error", "data": {"error": "Message must be an object"}}
                )
                continue
            event = msg.get("event")
            payload = msg.get("data", {})
            if not isinstance(payload, dict):
                await websocket.send_json(
                    {"event": "error", "data": {"error": "Message data must be an object"}}
                )
                continue

            if event == "agent:approval_response":
                from backend.apps.agents.agent_manager import agent_manager

                agent_manager.handle_approval(
                    payload.get("request_id"),
                    {
                        "behavior": payload.get("behavior", "deny"),
                        "message": payload.get("message"),
                        "updated_input": payload.get("updated_input"),
                    },
                )
            elif event == "browser:result":
                ws_manager.resolve_browser_command(
                    payload.get("request_id", ""),
                    payload,
                )
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.disconnect_global(websocket)


@app.post("/api/browser/command")
async def browser_command(request: Request):
    """HTTP endpoint called by the browser MCP server subprocess.
    Proxies commands to the frontend via WebSocket and waits for results."""
    body = await request.json()
    action = body.get("action", "")
    browser_id = body.get("browser_id", "")
    tab_id = body.get("tab_id", "")
    params = body.get("params", {})

    if not action or not browser_id:
        return JSONResponse(
            {"error": "action and browser_id are required"}, status_code=400
        )

    request_id = uuid4().hex
    result = await ws_manager.send_browser_command(
        request_id, action, browser_id, params, tab_id=tab_id
    )
    return JSONResponse(result)


@app.post("/api/browser-agent/run")
async def browser_agent_run(request: Request):
    """Run one or more browser sub-agents in parallel.
    Called by the browser_agent_mcp_server stdio subprocess."""
    from backend.apps.settings.settings import load_settings
    from backend.apps.agents.browser_agent import run_browser_agents

    body = await request.json()
    tasks = body.get("tasks", [])
    model = body.get("model", "sonnet")
    dashboard_id = body.get("dashboard_id", "")
    pre_selected_browser_ids = body.get("pre_selected_browser_ids", [])
    parent_session_id = body.get("parent_session_id", "")

    if not tasks:
        return JSONResponse({"error": "tasks array is required"}, status_code=400)

    results = await run_browser_agents(
        tasks=tasks,
        model=model,
        dashboard_id=dashboard_id or None,
        pre_selected_browser_ids=pre_selected_browser_ids,
        parent_session_id=parent_session_id or None,
    )
    return JSONResponse({"results": results})


@app.post("/api/invoke-agent/run")
async def invoke_agent_run(request: Request):
    """Fork an existing agent session and send it a new message.
    Called by the invoke_agent_mcp_server stdio subprocess."""
    body = await request.json()
    session_id = body.get("session_id", "")
    message = body.get("message", "")
    parent_session_id = body.get("parent_session_id", "")
    dashboard_id = body.get("dashboard_id", "")

    if not session_id:
        return JSONResponse({"error": "session_id is required"}, status_code=400)
    if not message:
        return JSONResponse({"error": "message is required"}, status_code=400)

    try:
        from backend.apps.agents.agent_manager import agent_manager

        result = await agent_manager.invoke_agent(
            source_session_id=session_id,
            message=message,
            parent_session_id=parent_session_id or None,
            dashboard_id=dashboard_id or None,
        )
        return JSONResponse(result)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        logger.exception("invoke_agent_run failed")
        return JSONResponse({"error": str(e)}, status_code=500)


if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="NeoSwarm backend server")
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("NEOSWARM_PORT", "8324"))
    )
    parser.add_argument("--host", default=os.environ.get("NEOSWARM_HOST", "127.0.0.1"))
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()

    os.environ["NEOSWARM_PORT"] = str(args.port)

    import uvicorn.config

    class _ReadyServer(uvicorn.Server):
        """Subclass that prints a machine-readable READY line on startup."""

        async def startup(self, sockets=None):
            await super().startup(sockets)
            print(f"READY:PORT={args.port}", flush=True)

    if args.reload:
        uvicorn.run("backend.main:app", host=args.host, port=args.port, reload=True)
    else:
        config = uvicorn.Config("backend.main:app", host=args.host, port=args.port)
        server = _ReadyServer(config)
        import asyncio

        asyncio.run(server.serve())
