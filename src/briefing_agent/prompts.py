"""Prompt templates for the triage pipeline.

Design principles:
  1. The model ONLY classifies. Python does all formatting and routing.
  2. Output schema is embedded as a comment in the prompt so the model
     understands the exact shape it must produce.
  3. Ambiguous cases have explicit tie-breaking rules.
  4. Weekly context is injected as a clearly-delimited block.
  5. Thread context is presented as a grouped block, not individual emails.

--- OUTPUT SCHEMA (what the model must return) ---

[
  {
    "id": "<message id — copy exactly from input>",
    "category": "<needs_reply | needs_action | waiting_on | follow_up | fyi>",
    "summary": "<one sentence, max 200 chars, present tense>",
    "due_hint": "<timing phrase extracted from email body, e.g. 'by Friday', or null>",
    "priority_hint": "<high | medium | low | null>",
    "reply_intent": "<what the reply should communicate, only if category=needs_reply, else null>"
  }
]

--- CATEGORY DEFINITIONS ---

  needs_reply   A real person is directly waiting for your response.
                The email contains a question or explicit request addressed to you.

  needs_action  You have a concrete task to complete. No response required but
                something must be done (sign a document, make a decision, complete a task).

  waiting_on    You are NOT the next person to act. You are waiting for someone
                else to deliver something you need.

  follow_up     Revisit later. No action right now but it should not be forgotten.

  fyi           Informational only. No action or reply expected.

--- AMBIGUOUS CASE RULES ---

  Newsletter vs action: If a newsletter or digest contains a concrete deadline
    addressed to you (e.g. "registration closes Friday"), classify as needs_action.
    Otherwise newsletters are always fyi.

  Automated notification vs waiting_on: Build/deploy notifications, CI alerts,
    and calendar reminders are always fyi, not waiting_on, even if they describe
    a pending state.

  Reply-all chain: If you are CC'd but not directly addressed, prefer fyi.
    If you are directly addressed or the last message in the thread ends with
    a question for you, prefer needs_reply.

  Ambiguous reply vs action: If an email asks you to do something AND expects
    a reply, choose needs_reply — the action is implied.
"""

from __future__ import annotations

TRIAGE_CATEGORIES = [
    "needs_reply",
    "needs_action",
    "waiting_on",
    "follow_up",
    "fyi",
]

SYSTEM_PROMPT = (
    "You are a strict JSON output machine. "
    "Return ONLY a valid JSON array. "
    "No markdown fences, no explanations, no thinking blocks, no extra keys."
)

TRIAGE_PROMPT_TEMPLATE = """\
Classify EACH message below into EXACTLY ONE category.

Categories:
  needs_reply   - a real person is waiting for your response
  needs_action  - you have a concrete task (no reply needed, but action required)
  waiting_on    - someone else must act next; you are blocked on them
  follow_up     - revisit later, no immediate action
  fyi           - informational only, no action or reply expected

Tie-breaking rules:
  - Newsletters/automated alerts/CI notifications → always fyi
  - Meeting reminders, calendar invites → fyi (not waiting_on)
  - CC'd with no direct question → fyi
  - Asked to do something AND reply → needs_reply (action is implied)
  - If a newsletter contains a real deadline addressed to you → needs_action

Return a JSON array. One object per message, same order as input.
Schema for each object:
  id            : copy the message id exactly
  category      : one of the five categories above
  summary       : one sentence ≤ 200 chars, present tense
  due_hint      : timing phrase from the email body, or null
  priority_hint : "high", "medium", "low", or null
  reply_intent  : what your reply should communicate (only if needs_reply, else null)
{weekly_context_block}
Messages:
{messages_block}
"""

WEEKLY_CONTEXT_TEMPLATE = """\
--- CONTEXT FROM LAST 7 DAYS ---
(Use this to inform priority and continuity. Do not re-classify old items.)
{context_string}
--- END CONTEXT ---
"""

THREAD_BLOCK_TEMPLATE = """\
[THREAD: {thread_id} — {message_count} message(s)]
{messages}
"""


def build_triage_prompt(
    messages_block: str,
    weekly_context: str | None = None,
) -> str:
    """Assemble the full triage prompt."""
    if weekly_context:
        ctx_block = WEEKLY_CONTEXT_TEMPLATE.format(context_string=weekly_context)
    else:
        ctx_block = ""
    return TRIAGE_PROMPT_TEMPLATE.format(
        messages_block=messages_block,
        weekly_context_block=ctx_block,
    )


def format_message_for_prompt(
    msg_id: str,
    sender: str,
    subject: str,
    body: str,
    attachments: list[str] | None = None,
    is_reply: bool = False,
) -> str:
    """Format a single message for inclusion in the prompt messages_block."""
    lines = [
        f"ID: {msg_id}",
        f"From: {sender}",
        f"Subject: {subject}",
    ]
    if is_reply:
        lines.append("[This is a reply in an existing thread]")
    if attachments:
        lines.append(f"[Attachments: {', '.join(attachments)}]")
    lines.append(f"Body: {body}")
    return "\n".join(lines)


def format_thread_block(
    thread_id: str,
    messages: list[str],  # already formatted via format_message_for_prompt
) -> str:
    """Wrap a group of thread messages in a thread context block."""
    return THREAD_BLOCK_TEMPLATE.format(
        thread_id=thread_id,
        message_count=len(messages),
        messages="\n---\n".join(messages),
    )
