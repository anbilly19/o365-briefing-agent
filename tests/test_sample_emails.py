"""End-to-end tests using realistic email fixtures.

Three layers:
  1. Cascade tier-1: realistic emails that should NEVER reach the LLM.
  2. Cascade tier-0: realistic emails that SHOULD reach the LLM.
  3. Pipeline integration: pre-built TriagedMessage objects wired through
     memory, grouping, and TUI rendering — no real LLM required.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from briefing_agent.cascade import CascadeFilter
from briefing_agent.models import TriageCategory, TriagedMessage, TriageResult
from briefing_agent.memory import MemoryDB

from tests.fixtures.emails import (
    EMAIL_NEWSLETTER,
    EMAIIL_GITHUB_NOTIFY,
    EMAIL_CI_FAILURE,
    EMAIL_DOCUSIGN,
    EMAIL_MARKETING_ACTION_REQUIRED,
    EMAIL_MANAGER_DELIVERABLE,
    EMAIL_CLIENT_WAITING,
    EMAIL_INVOICE_OVERDUE,
    EMAIL_FYI_UPDATE,
    EMAIL_SALES_FOLLOWUP,
    EMAIL_THREAD_REPLY_QUESTION,
    EMAIL_TASK_ASSIGNMENT,
    ALL_EMAILS,
    LLM_QUEUE_EMAILS,
    ALL_TRIAGED,
    TRIAGED_MANAGER_DELIVERABLE,
    TRIAGED_CLIENT_WAITING,
    TRIAGED_INVOICE_OVERDUE,
    TRIAGED_FYI_UPDATE,
    TRIAGED_SALES_FOLLOWUP,
    TRIAGED_THREAD_REPLY_QUESTION,
    TRIAGED_TASK_ASSIGNMENT,
)

_RULES = Path("config/rules.yaml")


@pytest.fixture
def cascade() -> CascadeFilter:
    return CascadeFilter(rules_path=_RULES)


# ===========================================================================
# Layer 1 — Cascade tier-1: should be caught WITHOUT calling the LLM
# ===========================================================================

class TestCascadeTier1:
    """These emails must be classified by heuristics alone."""

    def test_newsletter_caught_by_unsubscribe(self, cascade: CascadeFilter) -> None:
        msg, expected_cat, expected_tier = EMAIL_NEWSLETTER
        result = cascade.classify(msg, cleaned_body=msg.body_preview)
        assert result.tier == 1, "Newsletter must be caught by cascade (tier 1)"
        assert result.category == TriageCategory.FYI

    def test_github_notification_caught_by_sender(self, cascade: CascadeFilter) -> None:
        msg, expected_cat, expected_tier = EMAIIL_GITHUB_NOTIFY
        result = cascade.classify(msg, cleaned_body=msg.body_preview)
        assert result.tier == 1
        assert result.category == TriageCategory.FYI

    def test_ci_failure_caught_by_noreply_sender(self, cascade: CascadeFilter) -> None:
        msg, expected_cat, expected_tier = EMAIL_CI_FAILURE
        result = cascade.classify(msg, cleaned_body=msg.body_preview)
        assert result.tier == 1
        assert result.category == TriageCategory.FYI

    def test_docusign_caught_as_needs_action(self, cascade: CascadeFilter) -> None:
        msg, expected_cat, expected_tier = EMAIL_DOCUSIGN
        result = cascade.classify(msg, cleaned_body=msg.body_preview)
        assert result.tier == 1
        assert result.category == TriageCategory.NEEDS_ACTION

    def test_marketing_unsubscribe_beats_action_required(self, cascade: CascadeFilter) -> None:
        """The unsubscribe matcher fires before 'action required' subject rule."""
        msg, expected_cat, expected_tier = EMAIL_MARKETING_ACTION_REQUIRED
        result = cascade.classify(msg, cleaned_body=msg.body_preview)
        assert result.tier == 1
        assert result.category == TriageCategory.FYI

    def test_partition_tier1_count(self, cascade: CascadeFilter) -> None:
        """Exactly 5 of 12 sample emails should be caught by cascade."""
        cleaned = {m.id: m.body_preview for m in ALL_EMAILS}
        pre_classified, llm_queue = cascade.partition(ALL_EMAILS, cleaned_bodies=cleaned)
        assert len(pre_classified) == 5
        assert len(llm_queue) == 7

    def test_partition_no_llm_emails_overlap(self, cascade: CascadeFilter) -> None:
        """No message should appear in both pre_classified and llm_queue."""
        cleaned = {m.id: m.body_preview for m in ALL_EMAILS}
        pre_classified, llm_queue = cascade.partition(ALL_EMAILS, cleaned_bodies=cleaned)
        pre_ids = {r.message.id for r in pre_classified}
        llm_ids = {m.id for m in llm_queue}
        assert pre_ids.isdisjoint(llm_ids)


# ===========================================================================
# Layer 2 — Cascade tier-0: must NOT be intercepted, must reach LLM
# ===========================================================================

class TestCascadeTier0:
    """These emails are ambiguous enough that heuristics must pass them through."""

    def test_manager_email_reaches_llm(self, cascade: CascadeFilter) -> None:
        msg, _, _ = EMAIL_MANAGER_DELIVERABLE
        result = cascade.classify(msg, cleaned_body=msg.body_preview)
        assert result.category is None, (
            f"Manager email should not be pre-classified; got {result.category}"
        )

    def test_client_waiting_reaches_llm(self, cascade: CascadeFilter) -> None:
        msg, _, _ = EMAIL_CLIENT_WAITING
        result = cascade.classify(msg, cleaned_body=msg.body_preview)
        assert result.category is None

    def test_invoice_overdue_reaches_llm(self, cascade: CascadeFilter) -> None:
        """Supplier invoice — not a DocuSign sender, not noreply; goes to LLM."""
        msg, _, _ = EMAIL_INVOICE_OVERDUE
        result = cascade.classify(msg, cleaned_body=msg.body_preview)
        assert result.category is None

    def test_fyi_office_closure_reaches_llm(self, cascade: CascadeFilter) -> None:
        msg, _, _ = EMAIL_FYI_UPDATE
        result = cascade.classify(msg, cleaned_body=msg.body_preview)
        assert result.category is None

    def test_sales_followup_reaches_llm(self, cascade: CascadeFilter) -> None:
        msg, _, _ = EMAIL_SALES_FOLLOWUP
        result = cascade.classify(msg, cleaned_body=msg.body_preview)
        assert result.category is None

    def test_thread_reply_question_reaches_llm(self, cascade: CascadeFilter) -> None:
        msg, _, _ = EMAIL_THREAD_REPLY_QUESTION
        result = cascade.classify(msg, cleaned_body=msg.body_preview)
        assert result.category is None

    def test_task_assignment_reaches_llm(self, cascade: CascadeFilter) -> None:
        """DevOps task assignment — real human sender, not 'action required' in subject."""
        msg, _, _ = EMAIL_TASK_ASSIGNMENT
        result = cascade.classify(msg, cleaned_body=msg.body_preview)
        assert result.category is None


# ===========================================================================
# Layer 3 — Pipeline integration (no real LLM)
# Uses pre-built TriagedMessage objects as stand-ins for LLM output
# ===========================================================================

class TestTriageResultGrouping:
    """TriageResult correctly groups messages by category."""

    def _build_result(self, messages: list[TriagedMessage]) -> TriageResult:
        result = TriageResult()
        for msg in messages:
            getattr(result, msg.category.value).append(msg)
        return result

    def test_all_categories_represented(self) -> None:
        result = self._build_result(ALL_TRIAGED)
        assert len(result.needs_reply) == 2   # manager + priya
        assert len(result.needs_action) == 2  # invoice + PR review
        assert len(result.waiting_on) == 1    # client proposal
        assert len(result.follow_up) == 1     # sales renewal
        assert len(result.fyi) == 1           # office closure

    def test_total_matches_fixture_count(self) -> None:
        result = self._build_result(ALL_TRIAGED)
        assert result.total() == len(ALL_TRIAGED) == 7

    def test_all_items_returns_flat_list(self) -> None:
        result = self._build_result(ALL_TRIAGED)
        all_ids = {m.id for m in result.all_items()}
        fixture_ids = {m.id for m in ALL_TRIAGED}
        assert all_ids == fixture_ids

    def test_high_priority_messages_have_due_hint(self) -> None:
        high_pri = [
            TRIAGED_MANAGER_DELIVERABLE,
            TRIAGED_INVOICE_OVERDUE,
            TRIAGED_TASK_ASSIGNMENT,
        ]
        for msg in high_pri:
            assert msg.due_hint is not None, (
                f"{msg.id} is high priority but has no due_hint"
            )

    def test_fyi_has_no_reply_intent(self) -> None:
        assert TRIAGED_FYI_UPDATE.reply_intent is None

    def test_waiting_on_has_no_reply_intent(self) -> None:
        assert TRIAGED_CLIENT_WAITING.reply_intent is None

    def test_needs_reply_have_reply_intent(self) -> None:
        assert TRIAGED_MANAGER_DELIVERABLE.reply_intent is not None
        assert TRIAGED_THREAD_REPLY_QUESTION.reply_intent is not None


class TestMemoryPersistenceWithRealEmails:
    """Persist pre-built TriagedMessages through MemoryDB and verify retrieval."""

    @pytest.fixture
    async def db(self, tmp_path: Path) -> MemoryDB:
        mem = MemoryDB(db_path=tmp_path / "test.db")
        await mem.open()
        yield mem
        await mem.close()

    async def test_all_messages_persisted(self, db: MemoryDB) -> None:
        run_id = await db.start_run()
        await db.finish_run(run_id, ALL_TRIAGED)
        for msg in ALL_TRIAGED:
            assert await db.was_triaged(msg.id)

    async def test_dedup_skips_already_triaged(self, db: MemoryDB) -> None:
        run_id = await db.start_run()
        await db.finish_run(run_id, ALL_TRIAGED)
        for msg in ALL_TRIAGED:
            assert await db.was_triaged(msg.id) is True

    async def test_classification_reason_stored(self, db: MemoryDB) -> None:
        run_id = await db.start_run()
        reasons = {m.id: "llm" for m in ALL_TRIAGED}
        reasons["email_008"] = "heuristic: docusign sender"  # override one
        await db.finish_run(run_id, ALL_TRIAGED, reasons=reasons)
        row = await db.get_previous_classification("email_008")
        assert row["reason"] == "heuristic: docusign sender"

    async def test_feedback_loop_marks_wrong(self, db: MemoryDB) -> None:
        run_id = await db.start_run()
        await db.finish_run(run_id, ALL_TRIAGED)
        # Simulate user marking the sales follow-up as needs_reply
        await db.record_feedback(
            message_id="email_010",
            run_id=run_id,
            old_category="follow_up",
            new_category="needs_reply",
            vote="wrong",
            note="This vendor is actually waiting on our decision",
        )
        wrong = await db.get_recent_wrong_votes()
        assert any(r["message_id"] == "email_010" for r in wrong)

    async def test_wrong_votes_appear_in_review(self, db: MemoryDB) -> None:
        run_id = await db.start_run()
        await db.finish_run(run_id, ALL_TRIAGED)
        await db.record_feedback(
            message_id="email_006",
            run_id=run_id,
            old_category="needs_reply",
            new_category="needs_action",
            vote="wrong",
        )
        wrong = await db.get_recent_wrong_votes(limit=5)
        ids = [r["message_id"] for r in wrong]
        assert "email_006" in ids

    async def test_manager_email_summary_preserved(self, db: MemoryDB) -> None:
        run_id = await db.start_run()
        await db.finish_run(run_id, [TRIAGED_MANAGER_DELIVERABLE])
        row = await db.get_previous_classification("email_006")
        assert "board meeting" in row["summary"]
        assert "Sarah Chen" in row["summary"]

    async def test_invoice_due_hint_preserved(self, db: MemoryDB) -> None:
        run_id = await db.start_run()
        await db.finish_run(run_id, [TRIAGED_INVOICE_OVERDUE])
        row = await db.get_previous_classification("email_008")
        assert row["due_hint"] == "within 5 business days"
