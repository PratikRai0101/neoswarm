"""Analytics SubApp: PostHog for product analytics + local usage summary from session data."""

import asyncio
import json
import logging
import os
import platform
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime

from backend.config.Apps import SubApp
from backend.config.paths import SESSIONS_DIR
from backend.apps.analytics.collector import (
    init as init_collector,
    shutdown as shutdown_collector,
    record,
    identify,
)

logger = logging.getLogger(__name__)

APP_VERSION = "1.0.22"

_heartbeat_task: asyncio.Task | None = None

# Delta tracking — tracks last-seen 9Router totals to compute increments
_last_9r_cost: float | None = None
_last_9r_prompt_tokens: int | None = None
_last_9r_completion_tokens: int | None = None
_last_9r_requests: int | None = None
_RESTART_THRESHOLD = 1.0


def _compute_delta(
    current: float, last: float | None, threshold: float = _RESTART_THRESHOLD
) -> tuple[float, float]:
    """Compute incremental delta from cumulative values.

    Returns (delta, new_last).
    Handles 9Router restarts (large drops) and float jitter (tiny drops).
    """
    if last is None:
        return 0.0, current
    if current < last - threshold:
        return current, current
    if current < last:
        return 0.0, last
    return current - last, current


async def _heartbeat_loop():
    """Send a heartbeat event every 60 seconds with cost/token deltas."""
    global \
        _last_9r_cost, \
        _last_9r_prompt_tokens, \
        _last_9r_completion_tokens, \
        _last_9r_requests

    while True:
        await asyncio.sleep(60)
        try:
            from backend.apps.agents.agent_manager import agent_manager

            props = {
                "active_session_count": len(agent_manager.sessions),
            }

            record("app.heartbeat", props)
        except Exception:
            pass


@asynccontextmanager
async def analytics_lifespan():
    global _heartbeat_task

    init_collector()
    logger.info("PostHog analytics initialised")

    try:
        from backend.apps.settings.settings import load_settings, _save_settings

        settings = load_settings()

        # Track first open
        is_first_open = settings.first_opened_at is None
        if is_first_open:
            settings.first_opened_at = datetime.now().isoformat()
            _save_settings(settings)

        days_since_install = 0
        if settings.first_opened_at:
            try:
                first = datetime.fromisoformat(settings.first_opened_at[:19])
                days_since_install = (datetime.now() - first).days
            except Exception:
                pass

        providers = []
        if getattr(settings, "anthropic_api_key", None):
            providers.append("anthropic")
        if getattr(settings, "openai_api_key", None):
            providers.append("openai")
        if getattr(settings, "google_api_key", None):
            providers.append("gemini")
        if getattr(settings, "openrouter_api_key", None):
            providers.append("openrouter")
        for cp in getattr(settings, "custom_providers", []):
            providers.append(cp.name)

        record(
            "app.opened",
            {
                "os": platform.system(),
                "platform": platform.platform(),
                "provider_count": len(providers),
                "providers": providers,
                "is_first_open": is_first_open,
                "days_since_install": days_since_install,
                "app_version": APP_VERSION,
            },
        )

        id_props = {
            "providers_configured": providers,
            "provider_count": len(providers),
            "app_version": APP_VERSION,
        }
        if getattr(settings, "user_email", None):
            id_props["email"] = settings.user_email
        if getattr(settings, "user_name", None):
            id_props["name"] = settings.user_name
        if getattr(settings, "user_use_case", None):
            id_props["use_case"] = settings.user_use_case
        if getattr(settings, "user_referral_source", None):
            id_props["referral_source"] = settings.user_referral_source
        identify(id_props)
    except Exception as e:
        logger.debug(f"Analytics startup event failed (non-critical): {e}")

    # Start heartbeat
    _heartbeat_task = asyncio.create_task(_heartbeat_loop())

    yield

    # Stop heartbeat
    if _heartbeat_task:
        _heartbeat_task.cancel()
        try:
            await _heartbeat_task
        except asyncio.CancelledError:
            pass
        _heartbeat_task = None

    shutdown_collector()
    logger.info("PostHog analytics shut down")


analytics = SubApp("analytics", analytics_lifespan)


def _load_all_sessions() -> list[dict]:
    """Load all persisted session JSON files."""
    results = []
    if not os.path.exists(SESSIONS_DIR):
        return results
    for fname in os.listdir(SESSIONS_DIR):
        if fname.endswith(".json"):
            try:
                with open(os.path.join(SESSIONS_DIR, fname)) as f:
                    results.append(json.load(f))
            except Exception:
                pass
    return results


@analytics.router.get("/usage-summary")
async def usage_summary():
    """Compute usage stats from persisted sessions for the Settings page."""
    from backend.apps.agents.agent_manager import agent_manager

    # Combine persisted + active sessions
    sessions = _load_all_sessions()
    for s in agent_manager.get_all_sessions():
        sessions.append(s.model_dump(mode="json"))

    total_sessions = len(sessions)
    total_cost = sum(s.get("cost_usd", 0) for s in sessions)
    total_messages = 0
    total_tool_calls = 0
    total_duration = 0.0
    model_counts: Counter = Counter()
    provider_counts: Counter = Counter()
    tool_counts: Counter = Counter()
    status_counts: Counter = Counter()

    for s in sessions:
        messages = s.get("messages", [])
        user_msgs = [m for m in messages if m.get("role") in ("user", "assistant")]
        tool_msgs = [m for m in messages if m.get("role") == "tool_call"]
        total_messages += len(user_msgs)
        total_tool_calls += len(tool_msgs)

        model_counts[s.get("model", "unknown")] += 1
        provider_counts[s.get("provider", "anthropic")] += 1
        status_counts[s.get("status", "unknown")] += 1

        # Duration
        created = s.get("created_at")
        closed = s.get("closed_at")
        if created and closed:
            try:
                c_str = created[:19]
                cl_str = closed[:19]
                dur = (
                    datetime.fromisoformat(cl_str) - datetime.fromisoformat(c_str)
                ).total_seconds()
                if dur > 0:
                    total_duration += dur
            except Exception:
                pass

        # Count individual tools
        for m in tool_msgs:
            content = m.get("content", {})
            if isinstance(content, dict):
                tool_name = content.get("tool", "")
                if tool_name:
                    tool_counts[tool_name] += 1

    avg_duration = total_duration / total_sessions if total_sessions > 0 else 0
    completed = status_counts.get("completed", 0)
    completion_rate = completed / total_sessions if total_sessions > 0 else 0

    avg_cost = total_cost / total_sessions if total_sessions > 0 else 0

    return {
        "total_sessions": total_sessions,
        "total_cost_usd": round(total_cost, 4),
        "total_messages": total_messages,
        "total_tool_calls": total_tool_calls,
        "avg_duration_seconds": round(avg_duration, 1),
        "avg_cost_per_session": round(avg_cost, 4),
        "completion_rate": round(completion_rate, 3),
        "models_used": dict(model_counts.most_common(10)),
        "providers_used": dict(provider_counts.most_common(10)),
        "top_tools": dict(tool_counts.most_common(15)),
        "status_breakdown": dict(status_counts),
        "cost_source": cost_source,
    }


@analytics.router.get("/cost-breakdown")
async def cost_breakdown(period: str = "7d"):
    """Get usage stats summary - 9Router no longer supported."""
    return {"available": False, "by_model": {}, "by_provider": {}}


@analytics.router.get("/status")
async def analytics_status():
    return {"status": "posthog", "enabled": True}


@analytics.router.post("/event")
async def record_event(body: dict):
    """Accept analytics events from the frontend (e.g. feature.time_spent)."""
    event_type = body.get("event_type", "")
    properties = body.get("properties", {})
    if event_type:
        record(
            event_type,
            properties,
            session_id=body.get("session_id"),
            dashboard_id=body.get("dashboard_id"),
        )
    return {"ok": True}
