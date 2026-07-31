import json
import os
import tempfile
import logging
from contextlib import asynccontextmanager
from fastapi import HTTPException, Query, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from backend.config.Apps import SubApp
from backend.apps.settings.models import AppSettings, DEFAULT_SYSTEM_PROMPT
from backend.apps.settings.secret_store import (
    custom_provider_secret_name,
    delete_secret,
    get_secret,
    set_secret,
)

logger = logging.getLogger(__name__)

from backend.config.paths import SETTINGS_DIR as DATA_DIR

SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

# This sentinel lets local clients preserve an existing credential without
# receiving it back over HTTP. Sending null still explicitly removes a key.
SECRET_UNCHANGED = "__neoswarm_secret_unchanged__"
SECRET_FIELDS = frozenset(
    {
        "anthropic_api_key",
        "openai_api_key",
        "google_api_key",
        "openrouter_api_key",
        "claude_subscription_token",
        "openai_subscription_token",
        "gemini_subscription_token",
        "copilot_github_token",
        "copilot_token",
    }
)
ENV_SECRET_FIELDS = {
    "ANTHROPIC_API_KEY": "anthropic_api_key",
    "OPENAI_API_KEY": "openai_api_key",
    "GOOGLE_API_KEY": "google_api_key",
    "OPENROUTER_API_KEY": "openrouter_api_key",
}


@asynccontextmanager
async def settings_lifespan():
    os.makedirs(DATA_DIR, exist_ok=True)
    yield


settings = SubApp("settings", settings_lifespan)


def _load_settings_file() -> AppSettings:
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE) as file:
            return AppSettings(**json.load(file))
    return AppSettings()


def _load_persisted_settings() -> AppSettings:
    """Load settings and overlay credentials from the platform keychain."""
    current = _load_settings_file()
    for field in SECRET_FIELDS:
        secure_value = get_secret(field)
        if secure_value is not None:
            setattr(current, field, secure_value)
    for provider in current.custom_providers:
        secure_value = get_secret(custom_provider_secret_name(provider.name))
        if secure_value is not None:
            provider.api_key = secure_value
    return current


def load_settings() -> AppSettings:
    """Load effective settings with environment credentials taking priority."""
    current = _load_persisted_settings()
    if current.default_system_prompt is None:
        current.default_system_prompt = DEFAULT_SYSTEM_PROMPT
    for environment_name, field in ENV_SECRET_FIELDS.items():
        value = os.environ.get(environment_name)
        if value:
            setattr(current, field, value)
    return current


def _save_settings(
    settings_obj: AppSettings,
    *,
    secret_fields_to_update: set[str] | None = None,
):
    """Atomically persist settings, preferring the platform keychain for secrets."""
    os.makedirs(DATA_DIR, exist_ok=True)
    data = settings_obj.model_dump()
    explicit_secret_updates = secret_fields_to_update or set()
    persisted_file = _load_settings_file()
    environment_fields = {
        field
        for environment_name, field in ENV_SECRET_FIELDS.items()
        if os.environ.get(environment_name)
    }

    for field in SECRET_FIELDS:
        if field in environment_fields:
            # Environment values are runtime-only and must never replace a
            # stored keychain or compatibility-fallback credential.
            data[field] = getattr(persisted_file, field)
            continue

        value = getattr(settings_obj, field)
        if value:
            if set_secret(field, value):
                data[field] = None
        elif field in explicit_secret_updates:
            delete_secret(field)
            data[field] = None
        else:
            # An unrelated settings save must not erase a fallback credential
            # if the keychain was temporarily unavailable during the read.
            data[field] = getattr(persisted_file, field)

    persisted_custom = {
        provider.name: provider for provider in persisted_file.custom_providers
    }
    current_custom_names = set()
    custom_providers_explicit = "custom_providers" in explicit_secret_updates
    for provider, provider_data in zip(settings_obj.custom_providers, data["custom_providers"]):
        current_custom_names.add(provider.name)
        secret_name = custom_provider_secret_name(provider.name)
        if provider.api_key:
            if set_secret(secret_name, provider.api_key):
                provider_data["api_key"] = ""
        elif custom_providers_explicit:
            delete_secret(secret_name)
            provider_data["api_key"] = ""
        else:
            previous = persisted_custom.get(provider.name)
            provider_data["api_key"] = previous.api_key if previous else ""

    if custom_providers_explicit:
        for removed_name in set(persisted_custom) - current_custom_names:
            delete_secret(custom_provider_secret_name(removed_name))

    descriptor, temporary = tempfile.mkstemp(prefix="settings-", suffix=".tmp", dir=DATA_DIR)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w") as file:
            json.dump(data, file, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, SETTINGS_FILE)
        try:
            os.chmod(SETTINGS_FILE, 0o600)
        except OSError:
            pass
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


def _public_settings(settings_obj: AppSettings) -> dict:
    """Serialize settings without ever returning stored credentials."""
    data = settings_obj.model_dump()
    for field in SECRET_FIELDS:
        if data.get(field):
            data[field] = SECRET_UNCHANGED

    # Custom providers use the same preservation contract as built-in keys.
    for provider in data.get("custom_providers", []):
        if provider.get("api_key"):
            provider["api_key"] = SECRET_UNCHANGED
    return data


def _merged_settings(current: AppSettings, patch: dict) -> AppSettings:
    """Apply a partial update while preserving redacted credentials."""
    unknown = set(patch) - set(AppSettings.model_fields)
    if unknown:
        raise HTTPException(
            status_code=422, detail=f"Unknown settings fields: {', '.join(sorted(unknown))}"
        )

    merged = current.model_dump()
    for key, value in patch.items():
        if key in SECRET_FIELDS and value == SECRET_UNCHANGED:
            continue
        if key == "custom_providers" and isinstance(value, list):
            current_providers = {provider.name: provider for provider in current.custom_providers}
            value = [dict(provider) if isinstance(provider, dict) else provider for provider in value]
            for provider in value:
                if not isinstance(provider, dict) or provider.get("api_key") != SECRET_UNCHANGED:
                    continue
                existing = current_providers.get(provider.get("name"))
                provider["api_key"] = existing.api_key if existing else ""
        merged[key] = value
    return AppSettings(**merged)


@settings.router.get("")
async def get_settings():
    return _public_settings(load_settings())


@settings.router.put("")
async def update_settings(body: dict):
    from backend.apps.analytics.collector import record as _analytics

    old = load_settings()
    current = _merged_settings(old, body)

    # Track provider key changes
    provider_keys = {
        "anthropic_api_key": "anthropic",
        "openai_api_key": "openai",
        "google_api_key": "gemini",
        "openrouter_api_key": "openrouter",
    }
    for key, provider_name in provider_keys.items():
        old_val = bool(getattr(old, key, None))
        new_val = bool(getattr(current, key, None))
        if old_val != new_val:
            _analytics("provider.configured", {
                "provider": provider_name,
                "action": "added" if new_val else "removed",
            })

    # Track settings changes (key names only, not values)
    old_dict = old.model_dump()
    new_dict = current.model_dump()
    secret_keys = {"anthropic_api_key", "openai_api_key", "google_api_key", "openrouter_api_key",
                   "claude_subscription_token", "openai_subscription_token", "gemini_subscription_token",
                   "copilot_github_token", "copilot_token", "installation_id"}
    safe_changed = [
        k for k in new_dict
        if k in old_dict and new_dict[k] != old_dict[k] and k not in secret_keys
    ]
    if safe_changed:
        _analytics("settings.changed", {"changed_keys": safe_changed})

    explicit_secret_updates = {
        field
        for field, value in body.items()
        if (field in SECRET_FIELDS and value != SECRET_UNCHANGED)
        or field == "custom_providers"
    }
    _save_settings(current, secret_fields_to_update=explicit_secret_updates)
    return {"ok": True, "settings": _public_settings(current)}


@settings.router.get("/default-system-prompt")
async def get_default_system_prompt():
    return {"default_system_prompt": DEFAULT_SYSTEM_PROMPT}


@settings.router.post("/reset-system-prompt")
async def reset_system_prompt():
    current = load_settings()
    current.default_system_prompt = DEFAULT_SYSTEM_PROMPT
    _save_settings(current)
    return {"ok": True, "settings": _public_settings(current)}


class BrowseResponse(BaseModel):
    current: str
    parent: Optional[str]
    directories: list[str]
    files: list[str]


UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "self-swarm-uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


@settings.router.post("/upload-files")
async def upload_files(files: list[UploadFile] = File(...)):
    """Accept dropped files, save them, and return their server-side paths."""
    results = []
    for f in files:
        safe_name = os.path.basename(f.filename or "untitled")
        dest = os.path.join(UPLOAD_DIR, safe_name)

        counter = 1
        base, ext = os.path.splitext(safe_name)
        while os.path.exists(dest):
            dest = os.path.join(UPLOAD_DIR, f"{base}_{counter}{ext}")
            counter += 1

        contents = await f.read()
        with open(dest, "wb") as fh:
            fh.write(contents)

        results.append({"path": dest, "name": safe_name, "size": len(contents)})

    return JSONResponse({"files": results})


@settings.router.get("/browse-directories")
async def browse_directories(path: str = Query(default="")) -> BrowseResponse:
    target = path.strip() if path.strip() else os.path.expanduser("~")
    target = os.path.expanduser(target)
    target = os.path.abspath(target)

    if not os.path.exists(target):
        raise HTTPException(status_code=404, detail=f"Path not found: {target}")
    if not os.path.isdir(target):
        raise HTTPException(status_code=400, detail=f"Not a directory: {target}")

    try:
        entries = sorted(os.listdir(target))
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"Permission denied: {target}")

    visible = [e for e in entries if not e.startswith(".")]
    directories = [e for e in visible if os.path.isdir(os.path.join(target, e))]
    files = [e for e in visible if os.path.isfile(os.path.join(target, e))]

    parent = os.path.dirname(target) if target != "/" else None

    return BrowseResponse(current=target, parent=parent, directories=directories, files=files)
