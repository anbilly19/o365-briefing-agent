"""MSAL token acquisition for Microsoft Graph.

Supports two flows:
  - Device code (interactive, for personal use)
  - Client credentials (daemon, for server deployments)

The token is cached in memory for the process lifetime.
"""

from __future__ import annotations

import logging
from typing import Any

import msal

from briefing_agent.config import settings

logger = logging.getLogger(__name__)

SCOPES = [
    "https://graph.microsoft.com/Mail.Read",
    "https://graph.microsoft.com/Calendars.Read",
]

_token_cache: dict[str, Any] = {}


def _build_app() -> msal.ConfidentialClientApplication | msal.PublicClientApplication:
    if settings.ms_client_secret:
        return msal.ConfidentialClientApplication(
            client_id=settings.ms_client_id,
            client_credential=settings.ms_client_secret,
            authority=f"https://login.microsoftonline.com/{settings.ms_tenant_id}",
        )
    return msal.PublicClientApplication(
        client_id=settings.ms_client_id,
        authority=f"https://login.microsoftonline.com/{settings.ms_tenant_id}",
    )


def get_token() -> str:
    """Return a valid Bearer token, acquiring a new one if needed."""
    global _token_cache

    if _token_cache.get("access_token"):
        return _token_cache["access_token"]

    app = _build_app()

    if isinstance(app, msal.ConfidentialClientApplication):
        # Daemon / server flow
        result = app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
    else:
        # Interactive device-code flow
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(f"Device flow failed: {flow}")
        print(f"\nOpen {flow['verification_uri']} and enter code: {flow['user_code']}")
        result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        raise RuntimeError(f"Token acquisition failed: {result.get('error_description')}")

    _token_cache = result
    logger.info("Token acquired for tenant %s", settings.ms_tenant_id)
    return result["access_token"]
