from backend.config.Apps import SubApp
from backend.apps.agents.agent_manager import agent_manager
from backend.apps.agents.ws_manager import ws_manager
from backend.apps.agents.models import AgentConfig, ApprovalResponse
from backend.apps.agents.orchestrator import orchestrator, mission_to_dict
from backend.apps.agents.worktrees import WorktreeDirtyError, WorktreeError
from contextlib import asynccontextmanager
from fastapi import WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
import json
import logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def agents_lifespan():
    logger.info("Agents sub-app starting")
    orchestrator.agent_manager = agent_manager
    await agent_manager.reconcile_on_startup()
    await agent_manager.restore_all_sessions()
    yield
    logger.info("Agents sub-app shutting down")
    for mission in orchestrator.list_sessions():
        if mission.status in {"decomposing", "running"}:
            await orchestrator.cancel(mission.id)
    for session_id in list(agent_manager.tasks.keys()):
        await agent_manager.stop_agent(session_id)
    await agent_manager.persist_all_sessions()


agents = SubApp("agents", agents_lifespan)

# REST Endpoints


@agents.router.get("/sessions")
async def list_sessions(dashboard_id: str = ""):
    sessions = agent_manager.get_all_sessions(dashboard_id=dashboard_id or None)
    return {"sessions": [s.model_dump(mode="json") for s in sessions]}


@agents.router.get("/sessions/{session_id}")
async def get_session(session_id: str):
    session = agent_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session.model_dump(mode="json")


@agents.router.post("/launch")
async def launch_agent(config: AgentConfig):
    try:
        session = await agent_manager.launch_agent(config)
    except WorktreeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"session_id": session.id, "session": session.model_dump(mode="json")}


@agents.router.post("/sessions/{session_id}/message")
async def send_message(session_id: str, body: dict):
    prompt = body.get("prompt", "")
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")
    await agent_manager.send_message(
        session_id,
        prompt,
        mode=body.get("mode"),
        model=body.get("model"),
        images=body.get("images"),
        context_paths=body.get("context_paths"),
        forced_tools=body.get("forced_tools"),
        attached_skills=body.get("attached_skills"),
        hidden=body.get("hidden", False),
        selected_browser_ids=body.get("selected_browser_ids"),
    )
    return {"ok": True}


@agents.router.post("/sessions/{session_id}/stop")
async def stop_agent(session_id: str, body: dict = {}):
    await agent_manager.stop_agent(
        session_id, remove_worktree=bool(body.get("remove_worktree", False))
    )
    return {"ok": True}


@agents.router.post("/approval")
async def handle_approval(response: ApprovalResponse):
    agent_manager.handle_approval(
        response.request_id,
        {
            "behavior": response.behavior,
            "message": response.message,
            "updated_input": response.updated_input,
        },
    )
    return {"ok": True}


@agents.router.post("/sessions/{session_id}/edit_message")
async def edit_message(session_id: str, body: dict):
    message_id = body.get("message_id")
    new_content = body.get("content", "")
    if not message_id or not new_content:
        raise HTTPException(
            status_code=400, detail="message_id and content are required"
        )
    await agent_manager.edit_message(session_id, message_id, new_content)
    return {"ok": True}


@agents.router.post("/sessions/{session_id}/switch_branch")
async def switch_branch(session_id: str, body: dict):
    branch_id = body.get("branch_id", "")
    if not branch_id:
        raise HTTPException(status_code=400, detail="branch_id is required")
    await agent_manager.switch_branch(session_id, branch_id)
    return {"ok": True}


@agents.router.post("/sessions/{session_id}/generate-title")
async def generate_title(session_id: str, body: dict):
    prompt = body.get("prompt", "")
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt is required")
    title = await agent_manager.generate_title(session_id, prompt)
    return {"title": title}


@agents.router.post("/sessions/{session_id}/generate-group-meta")
async def generate_group_meta(session_id: str, body: dict):
    group_id = body.get("group_id", "")
    tool_calls = body.get("tool_calls", [])
    if not group_id or not tool_calls:
        raise HTTPException(
            status_code=400, detail="group_id and tool_calls are required"
        )
    result = await agent_manager.generate_group_meta(
        session_id,
        group_id,
        tool_calls,
        results_summary=body.get("results_summary"),
        is_refinement=body.get("is_refinement", False),
    )
    return result


@agents.router.patch("/sessions/{session_id}")
async def update_session(session_id: str, body: dict):
    session = agent_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await agent_manager.update_session(session_id, **body)
    return {"ok": True}


@agents.router.get("/sessions/{session_id}/branches")
async def get_branches(session_id: str):
    session = agent_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "branches": {k: v.model_dump(mode="json") for k, v in session.branches.items()},
        "active_branch_id": session.active_branch_id,
    }


@agents.router.post("/sessions/{session_id}/duplicate")
async def duplicate_session(session_id: str, body: dict = {}):
    try:
        session = await agent_manager.duplicate_session(
            session_id,
            dashboard_id=body.get("dashboard_id"),
            up_to_message_id=body.get("up_to_message_id"),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"session": session.model_dump(mode="json")}


@agents.router.post("/sessions/{session_id}/close")
async def close_session(session_id: str):
    try:
        await agent_manager.close_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True}


@agents.router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, force_worktree: bool = False):
    try:
        await agent_manager.delete_session(
            session_id, force_worktree=force_worktree
        )
    except WorktreeDirtyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True}


@agents.router.get("/history")
async def get_history(
    q: str = "", limit: int = 20, offset: int = 0, dashboard_id: str = ""
):
    return agent_manager.get_history(
        q=q,
        limit=limit,
        offset=offset,
        dashboard_id=dashboard_id or None,
    )


@agents.router.get("/sessions/{session_id}/browser-agents")
async def get_browser_agent_children(session_id: str):
    children = agent_manager.get_browser_agent_children(session_id)
    return {"sessions": children}


@agents.router.post("/sessions/{session_id}/resume")
async def resume_session(session_id: str):
    try:
        session = await agent_manager.resume_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"session": session.model_dump(mode="json")}


# ---------------------------------------------------------------------------
# Missions / multi-agent orchestration
# ---------------------------------------------------------------------------


@agents.router.get("/missions")
async def list_missions():
    return {"missions": [mission_to_dict(mission) for mission in orchestrator.list_sessions()]}


@agents.router.post("/missions")
async def create_mission(body: dict):
    try:
        mission = await orchestrator.create_session(
            mission=str(body.get("mission", "")),
            num_workers=int(body.get("workers", body.get("num_workers", 3))),
            model=str(body.get("model", "sonnet")),
            provider=body.get("provider"),
            execution_mode=body.get("execution_mode", "parallel"),
            target_directory=body.get("target_directory"),
            isolate_workers=bool(body.get("isolate_workers", False)),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"mission": mission_to_dict(mission)}


@agents.router.get("/missions/{mission_id}")
async def get_mission(mission_id: str):
    mission = orchestrator.get_session(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return {"mission": mission_to_dict(mission)}


@agents.router.post("/missions/{mission_id}/start")
async def start_mission(mission_id: str):
    try:
        mission = await orchestrator.start(mission_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"mission": mission_to_dict(mission)}


@agents.router.post("/missions/{mission_id}/cancel")
async def cancel_mission(mission_id: str):
    try:
        mission = await orchestrator.cancel(mission_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"mission": mission_to_dict(mission)}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@agents.router.get("/health")
async def health_check():
    """Simple health check endpoint."""
    return {"status": "ok"}


@agents.router.get("/models")
async def list_models():
    """Return the chat-picker model list grouped by provider.

    NeoSwarm uses direct API keys or local Ollama. No subscription routing.
    Includes dynamic models from Ollama server.
    """
    from backend.apps.agents.providers.registry import BUILTIN_MODELS
    from backend.apps.settings.settings import load_settings

    settings = load_settings()

    result: dict[str, list[dict]] = {}
    for provider_name, models in BUILTIN_MODELS.items():
        visible = []
        for m in models:
            api = m.get("api", "")
            # Skip subscription-only models (we don't support them)
            if m.get("subscription_only"):
                continue
            if api == "anthropic":
                has_key = bool(getattr(settings, "anthropic_api_key", None))
                if not has_key:
                    continue
            elif api == "openai":
                has_key = bool(getattr(settings, "openai_api_key", None))
                if not has_key:
                    continue
            elif api == "gemini":
                has_key = bool(getattr(settings, "google_api_key", None))
                if not has_key:
                    continue
            visible.append(
                {
                    "provider": provider_name,
                    "value": m["value"],
                    "label": m["label"],
                    "context_window": m.get("context_window", 128_000),
                    "reasoning": bool(m.get("reasoning", False)),
                }
            )
        if visible:
            result[provider_name] = visible

    # Fetch dynamic Ollama models from local server
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://localhost:11434/api/tags", timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                ollama_models = []
                for m in data.get("models", []):
                    name = m.get("name", "")
                    if name:
                        size_gb = m.get("size", 0) / (1024**3)
                        ollama_models.append({
                            "provider": "Ollama",
                            "value": name,
                            "label": f"{name} ({size_gb:.1f}GB)",
                            "context_window": m.get("details", {}).get("context_length", 128_000),
                            "reasoning": False,
                        })
                if ollama_models:
                    result["Ollama"] = ollama_models
    except Exception:
        pass  # Ollama not running

    # GitHub Copilot authentication is retained for future use, but Copilot and
    # GitHub catalog models are intentionally omitted until an execution
    # adapter exists. The model picker must only advertise runnable providers.

    return {"models": result}
