"""Tests for cascade.py pre-filter."""

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from briefing_agent.cascade import CascadeFilter, CascadeResult
from briefing_agent.models import MessageEnvelope, TriageCategory


def _make_msg(
    id: str = "m1",
    sender: str = "person@example.com",
    subject: str = "Hello",
) -> MessageEnvelope:
    return MessageEnvelope(
        id=id,
        subject=subject,
        sender=sender,
        received_at=datetime.now(timezone.utc),
        body_preview="Body text here.",
    )


@pytest.fixture
def rules_file(tmp_path: Path) -> Path:
    rules = {
        "rules": [
            {
                "name": "noreply",
                "matcher": "sender_contains",
                "value": "noreply",
                "action": {"category": "fyi", "reason": "Automated sender"},
            },
            {
                "name": "action_required",
                "matcher": "subject_contains",
                "value": "action required",
                "action": {"category": "needs_action", "reason": "Action required subject"},
            },
            {
                "name": "unsubscribe",
                "matcher": "has_unsubscribe",
                "action": {"category": "fyi", "reason": "Newsletter"},
            },
        ]
    }
    p = tmp_path / "rules.yaml"
    p.write_text(yaml.dump(rules))
    return p


@pytest.fixture
def cascade(rules_file: Path) -> CascadeFilter:
    return CascadeFilter(rules_path=rules_file)


# --- classify ---

def test_classify_sender_match(cascade: CascadeFilter) -> None:
    msg = _make_msg(sender="noreply@github.com")
    result = cascade.classify(msg)
    assert result.category == TriageCategory.FYI
    assert result.tier == 1
    assert "Automated" in result.reason


def test_classify_subject_match(cascade: CascadeFilter) -> None:
    msg = _make_msg(subject="Action Required: approve PR")
    result = cascade.classify(msg)
    assert result.category == TriageCategory.NEEDS_ACTION


def test_classify_unsubscribe_body(cascade: CascadeFilter) -> None:
    msg = _make_msg()
    result = cascade.classify(msg, cleaned_body="Click here to unsubscribe from this list.")
    assert result.category == TriageCategory.FYI
    assert result.tier == 1


def test_classify_no_match_returns_none(cascade: CascadeFilter) -> None:
    msg = _make_msg(sender="boss@company.com", subject="Quick question")
    result = cascade.classify(msg)
    assert result.category is None
    assert result.tier == 0


def test_classify_first_rule_wins(cascade: CascadeFilter) -> None:
    """noreply rule comes before action_required in fixture — should match noreply."""
    msg = _make_msg(sender="noreply@co.com", subject="Action Required: do something")
    result = cascade.classify(msg)
    assert result.reason == "Automated sender"


# --- partition ---

def test_partition_splits_correctly(cascade: CascadeFilter) -> None:
    msgs = [
        _make_msg("m1", sender="noreply@x.com"),
        _make_msg("m2", sender="alice@company.com", subject="Meeting tomorrow"),
        _make_msg("m3", subject="Action Required: review doc"),
    ]
    pre_classified, llm_queue = cascade.partition(msgs)
    pre_ids = {r.message.id for r in pre_classified}
    llm_ids = {m.id for m in llm_queue}
    assert pre_ids == {"m1", "m3"}
    assert llm_ids == {"m2"}


def test_partition_empty_input(cascade: CascadeFilter) -> None:
    pre, llm = cascade.partition([])
    assert pre == []
    assert llm == []


def test_partition_all_matched(cascade: CascadeFilter) -> None:
    msgs = [
        _make_msg("m1", sender="noreply@x.com"),
        _make_msg("m2", sender="donotreply@y.com" if False else "noreply@y.com"),
    ]
    pre, llm = cascade.partition(msgs)
    assert len(llm) == 0


def test_partition_none_matched(cascade: CascadeFilter) -> None:
    msgs = [
        _make_msg("m1", sender="alice@co.com", subject="Hi"),
        _make_msg("m2", sender="bob@co.com", subject="Quick question"),
    ]
    pre, llm = cascade.partition(msgs)
    assert len(pre) == 0
    assert len(llm) == 2


# --- missing rules file ---

def test_missing_rules_file_doesnt_crash(tmp_path: Path) -> None:
    f = CascadeFilter(rules_path=tmp_path / "nonexistent.yaml")
    msg = _make_msg(sender="noreply@x.com")
    result = f.classify(msg)
    assert result.category is None  # no rules = no match


def test_unknown_category_defaults_to_fyi(tmp_path: Path) -> None:
    rules = {
        "rules": [{
            "name": "bad_cat",
            "matcher": "sender_contains",
            "value": "test@",
            "action": {"category": "INVALID_CATEGORY", "reason": "test"},
        }]
    }
    p = tmp_path / "rules.yaml"
    p.write_text(yaml.dump(rules))
    f = CascadeFilter(rules_path=p)
    msg = _make_msg(sender="test@example.com")
    result = f.classify(msg)
    assert result.category == TriageCategory.FYI
