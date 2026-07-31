"""Credential-redaction and partial-update settings contracts."""

import json
import stat

import pytest

from backend.apps.settings.models import AppSettings
import backend.apps.settings.settings as settings_api


@pytest.fixture
def isolated_settings_file(tmp_path, monkeypatch):
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_api, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings_api, "SETTINGS_FILE", str(settings_file))
    return settings_file


@pytest.mark.asyncio
async def test_settings_never_returns_raw_credentials(isolated_settings_file):
    settings_api._save_settings(
        AppSettings(
            anthropic_api_key="sk-secret",
            openai_api_key="sk-openai",
            copilot_github_token="github-secret",
        )
    )

    public = await settings_api.get_settings()

    assert public["anthropic_api_key"] == settings_api.SECRET_UNCHANGED
    assert public["openai_api_key"] == settings_api.SECRET_UNCHANGED
    assert public["copilot_github_token"] == settings_api.SECRET_UNCHANGED
    assert "sk-secret" not in str(public)


@pytest.mark.asyncio
async def test_partial_update_preserves_or_explicitly_clears_credentials(
    isolated_settings_file,
):
    settings_api._save_settings(AppSettings(anthropic_api_key="sk-secret", theme="dark"))

    saved = await settings_api.update_settings(
        {
            "theme": "light",
            "anthropic_api_key": settings_api.SECRET_UNCHANGED,
        }
    )

    assert saved["settings"]["anthropic_api_key"] == settings_api.SECRET_UNCHANGED
    assert settings_api.load_settings().anthropic_api_key == "sk-secret"
    assert settings_api.load_settings().theme == "light"

    await settings_api.update_settings({"anthropic_api_key": None})

    assert settings_api.load_settings().anthropic_api_key is None


def test_environment_credentials_win_without_being_persisted(
    isolated_settings_file, monkeypatch
):
    settings_api._save_settings(AppSettings(anthropic_api_key="stored-key"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "environment-key")

    effective = settings_api.load_settings()
    effective.theme = "light"
    settings_api._save_settings(effective)

    persisted = json.loads(isolated_settings_file.read_text())
    assert effective.anthropic_api_key == "environment-key"
    assert persisted["anthropic_api_key"] == "stored-key"
    assert persisted["theme"] == "light"


def test_settings_file_is_owner_only(isolated_settings_file):
    settings_api._save_settings(AppSettings(openai_api_key="secret"))

    mode = stat.S_IMODE(isolated_settings_file.stat().st_mode)

    assert mode == 0o600
