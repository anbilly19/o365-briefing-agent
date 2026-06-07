"""Tests for graph_client/mail.py using pytest-httpx to mock Graph API calls."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
import httpx
from pytest_httpx import HTTPXMock

from briefing_agent.graph_client.mail import GraphMailClient, _GRAPH_BASE
from briefing_agent.models import MessageEnvelope


def _make_auth_mock() -> MagicMock:
    auth = MagicMock()
    auth.get_token.return_value = "fake-token"
    return auth


def _raw_message(
    msg_id: str = "msg_1",
    subject: str = "Test",
    has_attachments: bool = False,
) -> dict:
    return {
        "id": msg_id,
        "subject": subject,
        "sender": {"emailAddress": {"address": "sender@example.com"}},
        "receivedDateTime": "2026-06-01T09:00:00Z",
        "bodyPreview": "Hello there",
        "conversationId": "thread_001",
        "hasAttachments": has_attachments,
    }


# --- _parse_message ---

def test_parse_message_fields() -> None:
    raw = _raw_message()
    client = GraphMailClient(auth=_make_auth_mock())
    msg = client._parse_message(raw)
    assert msg.id == "msg_1"
    assert msg.sender == "sender@example.com"
    assert msg.subject == "Test"
    assert msg.thread_id == "thread_001"
    assert isinstance(msg.received_at, datetime)


def test_parse_message_no_sender() -> None:
    raw = _raw_message()
    raw["sender"] = {}
    client = GraphMailClient(auth=_make_auth_mock())
    msg = client._parse_message(raw)
    assert msg.sender == ""


def test_parse_message_no_subject() -> None:
    raw = _raw_message()
    del raw["subject"]
    client = GraphMailClient(auth=_make_auth_mock())
    msg = client._parse_message(raw)
    assert msg.subject == "(no subject)"


# --- fetch_messages_delta ---

async def test_fetch_messages_delta_no_token(httpx_mock: HTTPXMock) -> None:
    delta_response = {
        "value": [_raw_message("m1"), _raw_message("m2")],
        "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta_link_here",
    }
    httpx_mock.add_response(json=delta_response)

    client = GraphMailClient(auth=_make_auth_mock())
    messages, delta_link = await client.fetch_messages_delta(delta_token=None)

    assert len(messages) == 2
    assert "delta_link_here" in delta_link


async def test_fetch_messages_delta_paginates(httpx_mock: HTTPXMock) -> None:
    page1 = {
        "value": [_raw_message("m1")],
        "@odata.nextLink": f"{_GRAPH_BASE}/me/mailFolders/inbox/messages/delta?$skiptoken=abc",
    }
    page2 = {
        "value": [_raw_message("m2")],
        "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta_final",
    }
    httpx_mock.add_response(json=page1)
    httpx_mock.add_response(json=page2)

    client = GraphMailClient(auth=_make_auth_mock())
    messages, _ = await client.fetch_messages_delta(delta_token=None)
    assert len(messages) == 2
    assert {m.id for m in messages} == {"m1", "m2"}


async def test_fetch_handles_429_retry(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(status_code=429, headers={"Retry-After": "0"})
    delta_response = {
        "value": [_raw_message("m1")],
        "@odata.deltaLink": "https://graph.microsoft.com/v1.0/delta_link",
    }
    httpx_mock.add_response(json=delta_response)

    client = GraphMailClient(auth=_make_auth_mock())
    messages, _ = await client.fetch_messages_delta(delta_token=None)
    assert len(messages) == 1


async def test_fetch_raises_after_max_retries(httpx_mock: HTTPXMock) -> None:
    for _ in range(5):
        httpx_mock.add_response(status_code=429, headers={"Retry-After": "0"})
    client = GraphMailClient(auth=_make_auth_mock())
    with pytest.raises(RuntimeError, match="rate limit exceeded"):
        await client.fetch_messages_delta(delta_token=None)


async def test_fetch_attachment_names(httpx_mock: HTTPXMock) -> None:
    attachments_resp = {
        "value": [{"name": "invoice.pdf"}, {"name": "notes.docx"}]
    }
    httpx_mock.add_response(json=attachments_resp)

    client = GraphMailClient(auth=_make_auth_mock())
    names = await client._fetch_attachment_names("msg_id")
    assert names == ["invoice.pdf", "notes.docx"]


async def test_fetch_attachment_names_empty(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"value": []})
    client = GraphMailClient(auth=_make_auth_mock())
    names = await client._fetch_attachment_names("msg_id")
    assert names == []


async def test_fetch_messages_includes_attachment_names(httpx_mock: HTTPXMock) -> None:
    delta_response = {
        "value": [_raw_message("m1", has_attachments=True)],
        "@odata.deltaLink": "https://graph.microsoft.com/v1.0/dl",
    }
    attachments_resp = {"value": [{"name": "contract.pdf"}]}
    httpx_mock.add_response(json=delta_response)
    httpx_mock.add_response(json=attachments_resp)

    client = GraphMailClient(auth=_make_auth_mock())
    messages, _ = await client.fetch_messages_delta(delta_token=None)
    assert messages[0].attachments == ["contract.pdf"]
