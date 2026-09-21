"""Per-app tool grants (ported from upstream `apps_sdk/tool_grants`).

Default is ask-the-user; decisions can be remembered per app+tool. The deny
path is enforced HERE, server-side, so no app-side code can widen its own
surface. Timeout and dismissal both read as deny: silence is never consent.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import threading
import uuid

from backend.apps.applications.identity import APPS_DIR

logger = logging.getLogger(__name__)

GRANTS_FILE = os.path.join(APPS_DIR, "app_tool_grants.json")
GRANT_WAIT_SECONDS = 120.0

_p_lock = threading.Lock()
_p_pending: dict[str, "_PendingGrant"] = {}


class _PendingGrant:
    def __init__(self, request_id: str, app_id: str, app_name: str, tool_key: str):
        self.request_id = request_id
        self.app_id = app_id
        self.app_name = app_name
        self.tool_key = tool_key
        self.event = asyncio.Event()
        self.allow = False
        self.remember = False


def _read_grants() -> dict[str, dict[str, str]]:
    try:
        with open(GRANTS_FILE, encoding="utf-8") as handle:
            raw = json.load(handle)
        return {str(k): {str(t): str(d) for t, d in v.items()} for k, v in raw.items()}
    except FileNotFoundError:
        return {}
    except Exception as exc:
        logger.error("App grant store %s is damaged (%s); using empty", GRANTS_FILE, exc)
        return {}


def _write_grants(grants: dict[str, dict[str, str]]) -> None:
    os.makedirs(APPS_DIR, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="app-grants-", suffix=".tmp", dir=APPS_DIR)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(grants, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, GRANTS_FILE)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def grant_status(app_id: str, tool_key: str) -> str | None:
    with _p_lock:
        return _read_grants().get(app_id, {}).get(tool_key)


def list_grants(app_id: str) -> dict[str, str]:
    with _p_lock:
        return dict(_read_grants().get(app_id, {}))


def set_grant(app_id: str, tool_key: str, decision: str) -> None:
    assert decision in ("granted", "denied")
    with _p_lock:
        grants = _read_grants()
        grants.setdefault(app_id, {})[tool_key] = decision
        _write_grants(grants)


def clear_grants(app_id: str) -> bool:
    """Reset an app to ask-by-default. Returns True if anything was forgotten."""
    with _p_lock:
        grants = _read_grants()
        if grants.pop(app_id, None) is not None:
            _write_grants(grants)
            return True
        return False


async def request_grant(
    app_id: str, app_name: str, tool_key: str, tool_label: str, args_preview: str
) -> bool:
    """Ask the user over the websocket; block until they answer or time out."""
    from backend.apps.agents.ws_manager import ws_manager

    pending = _PendingGrant(
        request_id=uuid.uuid4().hex,
        app_id=app_id,
        app_name=app_name,
        tool_key=tool_key,
    )
    _p_pending[pending.request_id] = pending
    try:
        await ws_manager.broadcast_global("apps:tool_grant_request", {
            "request_id": pending.request_id,
            "app_id": app_id,
            "app_name": app_name,
            "tool_key": tool_key,
            "tool_label": tool_label,
            "args_preview": args_preview[:400],
        })
        try:
            await asyncio.wait_for(pending.event.wait(), timeout=GRANT_WAIT_SECONDS)
        except asyncio.TimeoutError:
            return False
        if pending.remember:
            set_grant(app_id, tool_key, "granted" if pending.allow else "denied")
        return pending.allow
    finally:
        _p_pending.pop(pending.request_id, None)


def resolve_grant(request_id: str, allow: bool, remember: bool) -> bool:
    pending = _p_pending.get(request_id)
    if pending is None:
        return False
    pending.allow = allow
    pending.remember = remember
    pending.event.set()
    return True


def pending_grant_count() -> int:
    return len(_p_pending)
