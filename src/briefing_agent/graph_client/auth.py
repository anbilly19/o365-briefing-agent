"""Microsoft Graph authentication via MSAL + optional system keychain.

Token storage priority:
  1. System keychain via `keyring` (most secure — recommended).
  2. Plaintext file at data/token.json (fallback, with explicit warning).

Security note:
  Storing OAuth tokens in plaintext is a meaningful security risk.
  Anyone with read access to data/token.json can access your mailbox.
  keyring is a small dependency (already in pyproject.toml) that stores
  tokens in the OS-native credential store (macOS Keychain, Windows
  Credential Manager, Secret Service on Linux).
  Set USE_KEYRING=false in .env to deliberately opt out.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import msal

logger = logging.getLogger(__name__)

_KEYRING_SERVICE = "o365-briefing-agent"
_KEYRING_USERNAME = "graph-token"
_FALLBACK_PATH = Path("data/token.json")


def _load_keyring() -> dict[str, Any] | None:
    try:
        import keyring
        raw = keyring.get_password(_KEYRING_SERVICE, _KEYRING_USERNAME)
        if raw:
            return json.loads(raw)  # type: ignore[no-any-return]
    except Exception:
        pass
    return None


def _save_keyring(data: dict[str, Any]) -> bool:
    try:
        import keyring
        keyring.set_password(_KEYRING_SERVICE, _KEYRING_USERNAME, json.dumps(data))
        return True
    except Exception:
        return False


def _load_file() -> dict[str, Any] | None:
    if _FALLBACK_PATH.exists():
        logger.warning(
            "Loading OAuth token from plaintext file %s. "
            "Consider setting USE_KEYRING=true for secure storage.",
            _FALLBACK_PATH,
        )
        return json.loads(_FALLBACK_PATH.read_text())  # type: ignore[no-any-return]
    return None


def _save_file(data: dict[str, Any]) -> None:
    logger.warning(
        "Saving OAuth token to plaintext file %s. "
        "This is a security risk. Set USE_KEYRING=true to use the system keychain.",
        _FALLBACK_PATH,
    )
    _FALLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    _FALLBACK_PATH.write_text(json.dumps(data, indent=2))


class GraphAuth:
    """MSAL-backed token cache with keyring/file persistence."""

    def __init__(
        self,
        client_id: str,
        tenant_id: str,
        client_secret: str,
        scopes: list[str],
        use_keyring: bool = True,
    ) -> None:
        self._scopes = scopes
        self._use_keyring = use_keyring

        cache = msal.SerializableTokenCache()
        cached = self._load()
        if cached:
            cache.deserialize(json.dumps(cached))

        self._app = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            token_cache=cache,
        )
        self._cache = cache

    def _load(self) -> dict[str, Any] | None:
        if self._use_keyring:
            data = _load_keyring()
            if data:
                return data
        return _load_file()

    def _persist(self) -> None:
        if not self._cache.has_state_changed:
            return
        data = json.loads(self._cache.serialize())
        if self._use_keyring and _save_keyring(data):
            return
        _save_file(data)

    def get_token(self) -> str:
        """Return a valid access token, refreshing if needed."""
        accounts = self._app.get_accounts()
        result = None
        if accounts:
            result = self._app.acquire_token_silent(self._scopes, account=accounts[0])
        if not result:
            result = self._app.acquire_token_for_client(scopes=self._scopes)
        if "access_token" not in result:
            raise RuntimeError(f"MSAL error: {result.get('error_description', result)}")
        self._persist()
        return result["access_token"]  # type: ignore[index]
