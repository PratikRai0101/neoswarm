from backend.config.Apps import SubApp
from backend.apps.agents.agent_manager import agent_manager
from backend.apps.agents.ws_manager import ws_manager
from backend.apps.agents.models import AgentConfig, ApprovalResponse
from contextlib import asynccontextmanager
from fastapi import WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse
import json
import logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def agents_lifespan():
    logger.info("Agents sub-app starting")
    await agent_manager.reconcile_on_startup()
    await agent_manager.restore_all_sessions()
    yield
    logger.info("Agents sub-app shutting down")
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
    session = await agent_manager.launch_agent(config)
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
async def stop_agent(session_id: str):
    await agent_manager.stop_agent(session_id)
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
async def delete_session(session_id: str):
    await agent_manager.delete_session(session_id)
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
                            "value": name.split(":")[0].split("-")[0],
                            "label": f"{name.split(':')[0]} ({size_gb:.1f}GB)",
                            "context_window": m.get("details", {}).get("context_length", 128_000),
                            "reasoning": False,
                        })
                if ollama_models:
                    result["Ollama"] = ollama_models
    except Exception:
        pass  # Ollama not running

    # Known Copilot-specific models (not in public API)
    COPILOT_KNOWN_MODELS = [
        # Anthropic models
        {"value": "anthropic/claude-opus-4-7", "label": "Claude Opus 4.7 (Anthropic)", "context_window": 200_000, "reasoning": True},
        {"value": "anthropic/claude-opus-4-6", "label": "Claude Opus 4.6 (Anthropic)", "context_window": 200_000, "reasoning": True},
        {"value": "anthropic/claude-sonnet-4-6", "label": "Claude Sonnet 4.6 (Anthropic)", "context_window": 200_000, "reasoning": False},
        {"value": "anthropic/claude-sonnet-4-5", "label": "Claude Sonnet 4.5 (Anthropic)", "context_window": 200_000, "reasoning": False},
        {"value": "anthropic/claude-haiku-4-5", "label": "Claude Haiku 4.5 (Anthropic)", "context_window": 200_000, "reasoning": False},
        # Google models
        {"value": "google/gemini-2-5-pro", "label": "Gemini 2.5 Pro (Google)", "context_window": 1_000_000, "reasoning": False},
        {"value": "google/gemini-2-0-flash", "label": "Gemini 2.0 Flash (Google)", "context_window": 1_000_000, "reasoning": False},
        {"value": "google/gemini-3-pro", "label": "Gemini 3 Pro (Google)", "context_window": 1_000_000, "reasoning": False},
        # xAI Grok
        {"value": "xai/grok-3", "label": "Grok 3 (xAI)", "context_window": 131_072, "reasoning": True},
        {"value": "xai/grok-3-mini", "label": "Grok 3 Mini (xAI)", "context_window": 131_072, "reasoning": True},
        # Newer OpenAI (not in public API yet)
        {"value": "openai/gpt-5-4", "label": "GPT-5.4 (OpenAI)", "context_window": 200_000, "reasoning": True},
        {"value": "openai/gpt-5-4-mini", "label": "GPT-5.4 Mini (OpenAI)", "context_window": 200_000, "reasoning": True},
        {"value": "openai/gpt-5-2-codex", "label": "GPT-5.2 Codex (OpenAI)", "context_window": 200_000, "reasoning": True},
        {"value": "openai/gpt-5-3-codex", "label": "GPT-5.3 Codex (OpenAI)", "context_window": 200_000, "reasoning": True},
    ]

    # Fetch GitHub Copilot models if token available
    if settings.copilot_github_token:
        copilot_models = list(COPILOT_KNOWN_MODELS)  # Start with known models
        
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                # Also fetch public catalog models
                resp = await client.get(
                    "https://models.github.ai/catalog/models",
                    headers={
                        "Authorization": f"Bearer {settings.copilot_github_token}",
                        "X-GitHub-Api-Version": "2022-11-28",
                        "Accept": "application/vnd.github+json",
                    },
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    for model in data:
                        name = model.get("name", "")
                        pub = model.get("publisher", "")
                        caps = model.get("capabilities", [])
                        copilot_models.append({
                            "value": model.get("id", f"{pub}/{name}"),
                            "label": f"{name} ({pub})",
                            "context_window": model.get("limits", {}).get("max_input_tokens", 128_000),
                            "reasoning": "reasoning" in caps,
                        })
                elif resp.status_code == 401:
                    # Token invalid, try to just show user
                    user_resp = await client.get(
                        "https://api.github.com/user",
                        headers={
                            "Authorization": f"Bearer {settings.copilot_github_token}",
                            "X-GitHub-Api-Version": "2022-11-28",
                            "Accept": "application/vnd.github+json",
                        },
                    )
                    if user_resp.status_code == 200:
                        user_data = user_resp.json()
                        result["Copilot"] = [
                            {"value": "copilot", "label": f"GitHub Copilot ({user_data.get('login', '')})", "context_window": 128_000, "reasoning": False},
                        ]
                if copilot_models:
                    result["Copilot"] = copilot_models
        except Exception:
            pass

    return {"models": result}
