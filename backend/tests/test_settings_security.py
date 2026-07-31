"""Credential-redaction and partial-update settings contracts."""

import json
import stat
from unittest.mock import MagicMock

import pytest

from backend.apps.settings.models import AppSettings, CustomProvider
import backend.apps.settings.settings as settings_api


@pytest.fixture
def isolated_settings_file(tmp_path, monkeypatch):
    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(settings_api, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings_api, "SETTINGS_FILE", str(settings_file))
    # Default tests exercise the owner-only compatibility fallback without
    # touching the developer machine's real platform keychain.
    monkeypatch.setattr(settings_api, "get_secret", lambda _name: None)
    monkeypatch.setattr(settings_api, "set_secret", lambda _name, _value: False)
    monkeypatch.setattr(settings_api, "delete_secret", lambda _name: False)
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


def test_successful_keychain_write_removes_secrets_from_json(
    isolated_settings_file, monkeypatch
):
    secure_values = {}
    monkeypatch.setattr(settings_api, "get_secret", secure_values.get)
    monkeypatch.setattr(
        settings_api,
        "set_secret",
        lambda name, value: secure_values.__setitem__(name, value) is None,
    )

    settings_api._save_settings(
        AppSettings(anthropic_api_key="sk-keychain", openai_api_key="sk-openai")
    )

    persisted = json.loads(isolated_settings_file.read_text())
    assert persisted["anthropic_api_key"] is None
    assert persisted["openai_api_key"] is None
    assert secure_values["anthropic_api_key"] == "sk-keychain"
    assert settings_api.load_settings().anthropic_api_key == "sk-keychain"


def test_custom_provider_keys_use_the_keychain(isolated_settings_file, monkeypatch):
    secure_values = {}
    monkeypatch.setattr(settings_api, "get_secret", secure_values.get)
    monkeypatch.setattr(
        settings_api,
        "set_secret",
        lambda name, value: secure_values.__setitem__(name, value) is None,
    )

    settings_api._save_settings(
        AppSettings(
            custom_providers=[
                CustomProvider(
                    name="Private Gateway",
                    base_url="https://models.internal.example/v1",
                    api_key="private-key",
                    models=[{"value": "private-model"}],
                )
            ]
        )
    )

    persisted = json.loads(isolated_settings_file.read_text())
    assert persisted["custom_providers"][0]["api_key"] == ""
    assert secure_values["custom_provider:Private Gateway"] == "private-key"
    assert settings_api.load_settings().custom_providers[0].api_key == "private-key"


@pytest.mark.asyncio
async def test_explicit_clear_deletes_keychain_credential(
    isolated_settings_file, monkeypatch
):
    secure_values = {"anthropic_api_key": "sk-keychain"}
    deleted = []
    monkeypatch.setattr(settings_api, "get_secret", secure_values.get)
    monkeypatch.setattr(
        settings_api,
        "set_secret",
        lambda name, value: secure_values.__setitem__(name, value) is None,
    )

    def delete(name):
        deleted.append(name)
        secure_values.pop(name, None)
        return True

    monkeypatch.setattr(settings_api, "delete_secret", delete)
    settings_api._save_settings(AppSettings(anthropic_api_key="sk-keychain"))

    await settings_api.update_settings({"anthropic_api_key": None})

    assert "anthropic_api_key" in deleted
    assert settings_api.load_settings().anthropic_api_key is None


def test_new_installations_default_to_analytics_opt_out():
    assert AppSettings().analytics_opt_in is False


@pytest.mark.asyncio
async def test_profile_updates_are_never_sent_to_analytics(
    isolated_settings_file, monkeypatch
):
    import backend.apps.analytics.collector as collector

    identify = MagicMock()
    monkeypatch.setattr(collector, "identify", identify)

    await settings_api.update_settings(
        {
            "user_name": "Private Name",
            "user_email": "private@example.com",
            "user_use_case": "Private project",
            "user_referral_source": "Private referral",
        }
    )

    identify.assert_not_called()
