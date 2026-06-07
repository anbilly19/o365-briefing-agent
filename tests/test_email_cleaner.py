"""Tests for email_cleaner module."""

import pytest

from briefing_agent.pipeline.email_cleaner import (
    clean_body,
    is_html,
    strip_html,
)


# --- is_html ---

def test_is_html_detects_html_tag() -> None:
    assert is_html("<html><body>hello</body></html>")


def test_is_html_detects_div() -> None:
    assert is_html("<div>something</div>")


def test_is_html_rejects_plain_text() -> None:
    assert not is_html("Just a plain text email.")


def test_is_html_rejects_empty() -> None:
    assert not is_html("")


# --- strip_html ---

def test_strip_html_removes_tags() -> None:
    result = strip_html("<p>Hello <b>world</b></p>")
    assert "Hello" in result
    assert "world" in result
    assert "<" not in result


def test_strip_html_handles_empty() -> None:
    result = strip_html("")
    assert isinstance(result, str)


def test_strip_html_handles_malformed() -> None:
    result = strip_html("<p>unclosed")
    assert isinstance(result, str)


# --- clean_body ---

def test_clean_body_plain_text_passthrough() -> None:
    result = clean_body("Simple email body")
    assert "Simple email body" in result


def test_clean_body_strips_html() -> None:
    result = clean_body("<html><body><p>Hi there</p></body></html>")
    assert "Hi there" in result
    assert "<" not in result


def test_clean_body_appends_attachment_note() -> None:
    result = clean_body("Please sign this.", attachments=["contract.pdf", "notes.docx"])
    assert "contract.pdf" in result
    assert "notes.docx" in result
    assert "[Attachments:" in result


def test_clean_body_no_attachments_no_note() -> None:
    result = clean_body("body text")
    assert "[Attachments:" not in result


def test_clean_body_truncates_to_max_chars() -> None:
    long_body = "word " * 5000
    result = clean_body(long_body, max_chars=500)
    # attachment note comes after truncation so don't count it
    body_part = result.split("[Attachments:")[0]
    assert len(body_part) <= 500


def test_clean_body_attachment_appended_after_truncation() -> None:
    """Attachment note must always be present even when body is truncated."""
    long_body = "x" * 5000
    result = clean_body(long_body, attachments=["file.pdf"], max_chars=100)
    assert "file.pdf" in result


def test_clean_body_removes_quoted_reply() -> None:
    body = "Here is my answer.\n--- Original Message ---\nOriginal stuff here."
    result = clean_body(body)
    assert "Original stuff here" not in result
    assert "Here is my answer" in result


def test_clean_body_collapses_blank_lines() -> None:
    body = "First line\n\n\n\n\nSecond line"
    result = clean_body(body)
    assert "\n\n\n" not in result
