"""Best-effort platform credential storage.

The system keychain is the preferred adapter. Callers receive a boolean from
writes/deletes so they can retain the owner-only settings-file fallback on
headless systems without a usable keyring backend.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_SERVICE_NAME = "NeoSwarm"


def get_secret(name: str) -> str | None:
    """Read a secret from the platform keychain, returning None if unavailable."""
    try:
        import keyring

        return keyring.get_password(_SERVICE_NAME, name)
    except Exception as error:
        logger.debug("Platform keychain read unavailable for %s: %s", name, error)
        return None


def set_secret(name: str, value: str) -> bool:
    """Store a secret in the platform keychain and report whether it succeeded."""
    try:
        import keyring

        keyring.set_password(_SERVICE_NAME, name, value)
        return True
    except Exception as error:
        logger.debug("Platform keychain write unavailable for %s: %s", name, error)
        return False


def delete_secret(name: str) -> bool:
    """Delete a keychain secret; a missing credential is already a success."""
    try:
        import keyring
        from keyring.errors import PasswordDeleteError

        try:
            keyring.delete_password(_SERVICE_NAME, name)
        except PasswordDeleteError:
            pass
        return True
    except Exception as error:
        logger.debug("Platform keychain delete unavailable for %s: %s", name, error)
        return False


def custom_provider_secret_name(provider_name: str) -> str:
    return f"custom_provider:{provider_name}"
