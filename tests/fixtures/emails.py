"""Realistic email fixtures for testing.

Each EMAIL_* constant is a (MessageEnvelope, expected_category, expected_cascade_tier) tuple.
  - tier 0 = should reach LLM
  - tier 1 = should be caught by cascade heuristics

ALSO provides TRIAGED_* constants: pre-built TriagedMessage objects
that represent plausible LLM output for the tier-0 messages.
Used to test downstream processing (memory persistence, TUI rendering,
category grouping) without running a real model.
"""

from __future__ import annotations

from datetime import datetime, timezone

from briefing_agent.models import MessageEnvelope, TriagedMessage, TriageCategory

_NOW = datetime(2026, 6, 8, 8, 0, 0, tzinfo=timezone.utc)


def _env(
    id: str,
    subject: str,
    sender: str,
    body: str,
    thread_id: str | None = None,
    is_reply: bool = False,
    attachments: list[str] | None = None,
) -> MessageEnvelope:
    return MessageEnvelope(
        id=id,
        subject=subject,
        sender=sender,
        received_at=_NOW,
        body_preview=body,
        thread_id=thread_id or id,
        is_reply=is_reply,
        attachments=attachments or [],
    )


# ---------------------------------------------------------------------------
# Tier-1 (cascade catches these — no LLM call)
# ---------------------------------------------------------------------------

# Newsletter with unsubscribe link
EMAIL_NEWSLETTER = (
    _env(
        id="email_001",
        subject="This week in AI: GPT-5 review, new Ollama release, and more",
        sender="digest@tldr.tech",
        body=(
            "Welcome to this week\u2019s TLDR AI digest.\n"
            "\n"
            "1. OpenAI announces GPT-5 with 1M context window\n"
            "2. Ollama 0.9 ships with multi-model routing\n"
            "3. Anthropic releases Claude 4 Sonnet\n"
            "\n"
            "You are receiving this because you subscribed.\n"
            "To unsubscribe from this list, click here: https://tldr.tech/unsubscribe"
        ),
    ),
    TriageCategory.FYI,
    1,  # cascade tier
)

# GitHub notification (automated sender)
EMAIIL_GITHUB_NOTIFY = (
    _env(
        id="email_002",
        subject="[anbilly19/o365-briefing-agent] PR review requested: feat/cascade (#12)",
        sender="notifications@github.com",
        body=(
            "@anbilly19 requested your review on PR #12.\n"
            "Repository: anbilly19/o365-briefing-agent\n"
            "Branch: feat/cascade\n"
            "View the pull request: https://github.com/anbilly19/o365-briefing-agent/pull/12"
        ),
    ),
    TriageCategory.FYI,
    1,
)

# CI build failure
EMAIL_CI_FAILURE = (
    _env(
        id="email_003",
        subject="[CI] Build failed on main \u2014 o365-briefing-agent",
        sender="noreply@circleci.com",
        body=(
            "Your CircleCI build failed.\n"
            "Job: test-suite\n"
            "Branch: main\n"
            "Duration: 1m 42s\n"
            "View: https://circleci.com/gh/anbilly19/o365-briefing-agent/42"
        ),
    ),
    TriageCategory.FYI,
    1,
)

# DocuSign signature request
EMAIL_DOCUSIGN = (
    _env(
        id="email_004",
        subject="DocuSign: Please sign \u2018Consulting Agreement \u2014 June 2026\u2019",
        sender="dse_NA4@docusign.net",
        body=(
            "Acme Corp has sent you a document to review and sign.\n"
            "Document: Consulting Agreement \u2014 June 2026\n"
            "Please sign by: 15 June 2026\n"
            "Review Document: https://app.docusign.com/sign/abc123"
        ),
    ),
    TriageCategory.NEEDS_ACTION,
    1,
)

# Marketing \u2018action required\u2019 spam
EMAIL_MARKETING_ACTION_REQUIRED = (
    _env(
        id="email_005",
        subject="Action Required: Confirm your email address",
        sender="no-reply@marketing-platform.io",
        body=(
            "Please confirm your email address to complete your registration.\n"
            "Click here to confirm: https://marketing-platform.io/confirm?token=xyz\n"
            "\n"
            "If you did not sign up, you can safely ignore this email.\n"
            "Unsubscribe: https://marketing-platform.io/unsubscribe"
        ),
    ),
    TriageCategory.FYI,  # unsubscribe rule fires before action_required
    1,
)


# ---------------------------------------------------------------------------
# Tier-0 (reaches LLM)
# ---------------------------------------------------------------------------

# Manager asking for deliverable
EMAIL_MANAGER_DELIVERABLE = (
    _env(
        id="email_006",
        subject="Q2 project status — need update before board meeting",
        sender="sarah.chen@company.com",
        body=(
            "Hi,\n\n"
            "The board meeting is on Thursday at 2pm. I need a one-page project status\n"
            "for the o365 briefing agent work by EOD tomorrow so I can include it in the deck.\n"
            "\n"
            "Specifically:\n"
            "  - What\u2019s shipped\n"
            "  - What\u2019s blocked\n"
            "  - RAG status (red/amber/green)\n"
            "\n"
            "Thanks\n"
            "Sarah"
        ),
    ),
    TriageCategory.NEEDS_REPLY,
    0,
)

# Client waiting on proposal
EMAIL_CLIENT_WAITING = (
    _env(
        id="email_007",
        subject="Re: Partnership proposal",
        sender="tom.okafor@bigclient.com",
        body=(
            "Thanks for sending over the proposal.\n\n"
            "I\u2019ve shared it with our procurement team and legal. They\u2019re reviewing now.\n"
            "Expect to hear back from me by end of next week.\n"
            "\n"
            "Best,\nTom"
        ),
        is_reply=True,
        thread_id="thread_proposal_001",
    ),
    TriageCategory.WAITING_ON,
    0,
)

# Invoice overdue
EMAIL_INVOICE_OVERDUE = (
    _env(
        id="email_008",
        subject="OVERDUE: Invoice #INV-2026-042 — \u20ac3,200 payment required",
        sender="accounts@supplier-ltd.com",
        body=(
            "Dear Customer,\n\n"
            "Invoice #INV-2026-042 for \u20ac3,200 was due on 1 June 2026 and remains unpaid.\n"
            "Please arrange payment within 5 business days to avoid a late fee.\n"
            "\n"
            "Bank details:\n"
            "  IBAN: GB29NWBK60161331926819\n"
            "  Reference: INV-2026-042\n"
            "\n"
            "If payment has already been made, please disregard this notice.\n"
            "Accounts team, Supplier Ltd"
        ),
    ),
    TriageCategory.NEEDS_ACTION,
    0,
)

# Colleague FYI update
EMAIL_FYI_UPDATE = (
    _env(
        id="email_009",
        subject="FYI: Office closed Friday 13 June",
        sender="facilities@company.com",
        body=(
            "Hi all,\n\n"
            "Just a reminder that the Amsterdam office will be closed on Friday 13 June\n"
            "for the public holiday. All meeting rooms are unavailable that day.\n"
            "\n"
            "No action needed \u2014 just wanted to give everyone advance notice.\n"
            "\n"
            "Facilities team"
        ),
    ),
    TriageCategory.FYI,
    0,
)

# Follow-up nudge from sales
EMAIL_SALES_FOLLOWUP = (
    _env(
        id="email_010",
        subject="Following up: annual licence renewal",
        sender="james.wright@vendor.com",
        body=(
            "Hi,\n\n"
            "I\u2019m just following up on our conversation last month about the annual licence\n"
            "renewal for your team. No rush at all \u2014 just wanted to stay on your radar.\n"
            "\n"
            "Happy to jump on a 15-minute call if useful.\n"
            "\n"
            "Best,\nJames\nVendor Ltd"
        ),
    ),
    TriageCategory.FOLLOW_UP,
    0,
)

# Thread reply asking a question back
EMAIL_THREAD_REPLY_QUESTION = (
    _env(
        id="email_011",
        subject="Re: Technical architecture review",
        sender="priya.sharma@partner.com",
        body=(
            "Thanks for the overview, that\u2019s really helpful.\n\n"
            "One question: you mentioned the LangGraph state store uses SQLite — have you\n"
            "considered Redis for multi-user deployments? Curious about your reasoning.\n"
            "\n"
            "Also, what\u2019s the target latency for a full triage run on ~50 messages?\n"
            "\n"
            "Priya"
        ),
        is_reply=True,
        thread_id="thread_arch_review",
    ),
    TriageCategory.NEEDS_REPLY,
    0,
)

# Internal task assignment
EMAIL_TASK_ASSIGNMENT = (
    _env(
        id="email_012",
        subject="Action needed: review and merge PR #14 before deploy",
        sender="devops@company.com",
        body=(
            "Hi,\n\n"
            "We\u2019re planning to deploy to staging on Wednesday at 10am.\n"
            "PR #14 (connector abstraction) needs to be reviewed and merged\n"
            "before then. Can you take a look today?\n"
            "\n"
            "Link: https://github.com/anbilly19/o365-briefing-agent/pull/14\n"
            "\n"
            "Thanks,\nDevOps"
        ),
    ),
    TriageCategory.NEEDS_ACTION,
    0,
)


# All tier-0 messages as a list (these go to the LLM)
LLM_QUEUE_EMAILS = [
    EMAIL_MANAGER_DELIVERABLE[0],
    EMAIL_CLIENT_WAITING[0],
    EMAIL_INVOICE_OVERDUE[0],
    EMAIL_FYI_UPDATE[0],
    EMAIL_SALES_FOLLOWUP[0],
    EMAIL_THREAD_REPLY_QUESTION[0],
    EMAIL_TASK_ASSIGNMENT[0],
]

# All emails (tier-0 + tier-1)
ALL_EMAILS = [
    EMAIL_NEWSLETTER[0],
    EMAIIL_GITHUB_NOTIFY[0],
    EMAIL_CI_FAILURE[0],
    EMAIL_DOCUSIGN[0],
    EMAIL_MARKETING_ACTION_REQUIRED[0],
    *LLM_QUEUE_EMAILS,
]


# ---------------------------------------------------------------------------
# Pre-built TriagedMessage objects (plausible LLM output for tier-0 messages)
# ---------------------------------------------------------------------------

TRIAGED_MANAGER_DELIVERABLE = TriagedMessage(
    id="email_006",
    category=TriageCategory.NEEDS_REPLY,
    summary="Sarah Chen needs a one-page project status (shipped, blocked, RAG) before Thursday\u2019s board meeting. Due EOD tomorrow.",
    due_hint="EOD tomorrow",
    priority_hint="high",
    reply_intent="Confirm receipt and send status update.",
)

TRIAGED_CLIENT_WAITING = TriagedMessage(
    id="email_007",
    category=TriageCategory.WAITING_ON,
    summary="Tom Okafor has shared the proposal with procurement and legal. Expects to respond by end of next week.",
    due_hint="end of next week",
    priority_hint="medium",
    reply_intent=None,
)

TRIAGED_INVOICE_OVERDUE = TriagedMessage(
    id="email_008",
    category=TriageCategory.NEEDS_ACTION,
    summary="Invoice #INV-2026-042 for \u20ac3,200 is overdue since 1 June. Payment required within 5 days to avoid late fee.",
    due_hint="within 5 business days",
    priority_hint="high",
    reply_intent=None,
)

TRIAGED_FYI_UPDATE = TriagedMessage(
    id="email_009",
    category=TriageCategory.FYI,
    summary="Amsterdam office closed Friday 13 June for public holiday. No meeting rooms available. No action needed.",
    due_hint=None,
    priority_hint="low",
    reply_intent=None,
)

TRIAGED_SALES_FOLLOWUP = TriagedMessage(
    id="email_010",
    category=TriageCategory.FOLLOW_UP,
    summary="James Wright (Vendor Ltd) following up on annual licence renewal. No deadline, happy to do a call.",
    due_hint=None,
    priority_hint="low",
    reply_intent="Respond when ready; no urgency.",
)

TRIAGED_THREAD_REPLY_QUESTION = TriagedMessage(
    id="email_011",
    category=TriageCategory.NEEDS_REPLY,
    summary="Priya Sharma asks about SQLite vs Redis for multi-user and target latency for 50-message triage run.",
    due_hint=None,
    priority_hint="medium",
    reply_intent="Answer SQLite rationale and share latency benchmarks.",
)

TRIAGED_TASK_ASSIGNMENT = TriagedMessage(
    id="email_012",
    category=TriageCategory.NEEDS_ACTION,
    summary="DevOps needs PR #14 reviewed and merged before Wednesday 10am staging deploy.",
    due_hint="Wednesday 10am",
    priority_hint="high",
    reply_intent=None,
)

ALL_TRIAGED = [
    TRIAGED_MANAGER_DELIVERABLE,
    TRIAGED_CLIENT_WAITING,
    TRIAGED_INVOICE_OVERDUE,
    TRIAGED_FYI_UPDATE,
    TRIAGED_SALES_FOLLOWUP,
    TRIAGED_THREAD_REPLY_QUESTION,
    TRIAGED_TASK_ASSIGNMENT,
]
