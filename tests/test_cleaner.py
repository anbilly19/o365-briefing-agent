"""Unit tests for EmailCleaner."""

import pytest
from datetime import datetime, timezone
from briefing_agent.models import MessageEnvelope
from briefing_agent.pipeline.email_cleaner import EmailCleaner


def make_msg(id: str, sender: str, subject: str, body: str = "body") -> MessageEnvelope:
    return MessageEnvelope(
        id=id,
        subject=subject,
        sender=sender,
        received_at=datetime.now(timezone.utc),
        body_preview=body,
    )


def test_newsletter_skipped() -> None:
    cleaner = EmailCleaner()
    msg = make_msg("1", "noreply@example.com", "Your weekly digest")
    kept, skipped = cleaner.clean_and_filter([msg])
    assert len(kept) == 0
    assert len(skipped) == 1


def test_real_message_kept() -> None:
    cleaner = EmailCleaner()
    msg = make_msg("2", "alice@example.com", "Can you review this?", "Please check the doc")
    kept, skipped = cleaner.clean_and_filter([msg])
    assert len(kept) == 1
    assert len(skipped) == 0


def test_url_stripped_from_body() -> None:
    cleaner = EmailCleaner()
    msg = make_msg("3", "alice@example.com", "Link inside", "See https://example.com/very/long/path for details")
    kept, _ = cleaner.clean_and_filter([msg])
    assert "https://" not in kept[0].body_preview


def test_body_truncated() -> None:
    cleaner = EmailCleaner()
    long_body = "x" * 2000
    msg = make_msg("4", "bob@example.com", "Long email", long_body)
    kept, _ = cleaner.clean_and_filter([msg])
    assert len(kept[0].body_preview) <= 800
