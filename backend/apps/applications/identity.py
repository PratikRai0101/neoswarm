"""Per-app identity tokens (ported from upstream `apps_sdk/app_identity`).

The host mints a random token per app (output or workspace id) and the grant
gate resolves identity FROM the token, so an app cannot claim another app's
id by self-reporting it. Tokens persist so a backend restart doesn't strand
live app processes. Writes are atomic; damaged files reset to empty.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import tempfile
import threading

from backend.config.paths import DATA_ROOT

logger = logging.getLogger(__name__)

APPS_DIR = os.path.join(DATA_ROOT, "apps")
APP_TOKENS_FILE = os.path.join(APPS_DIR, "app_tokens.json")

_p_lock = threading.Lock()


def _read_tokens() -> dict[str, str]:
    try:
        with open(APP_TOKENS_FILE, encoding="utf-8") as handle:
            raw = json.load(handle)
        return {str(k): str(v) for k, v in raw.items()}
    except FileNotFoundError:
        return {}
    except Exception as exc:
        logger.error("App token store %s is damaged (%s); using empty", APP_TOKENS_FILE, exc)
        return {}


def _write_tokens(tokens: dict[str, str]) -> None:
    os.makedirs(APPS_DIR, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="app-tokens-", suffix=".tmp", dir=APPS_DIR)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(tokens, handle, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, APP_TOKENS_FILE)
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


def mint_app_token(app_id: str) -> str:
    """One stable token per app id: reused while the app lives so a still-
    running instance's copy is never orphaned."""
    with _p_lock:
        tokens = _read_tokens()
        for token, stored_id in tokens.items():
            if stored_id == app_id:
                return token
        token = secrets.token_urlsafe(24)
        tokens[token] = app_id
        _write_tokens(tokens)
        return token


def resolve_app_token(token: str) -> str | None:
    if not token:
        return None
    with _p_lock:
        return _read_tokens().get(token)


def revoke_app_token(app_id: str) -> bool:
    with _p_lock:
        tokens = _read_tokens()
        kept = {token: stored_id for token, stored_id in tokens.items() if stored_id != app_id}
        if len(kept) != len(tokens):
            _write_tokens(kept)
            return True
        return False
