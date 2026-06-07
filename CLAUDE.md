# CLAUDE.md — o365-briefing-agent

Project context and guidelines for AI-assisted development.

---

## What this is

A privacy-first, local-only daily email briefing agent.
- Reads your O365/Exchange inbox via Microsoft Graph API (MSAL auth)
- Classifies and summarises emails using a **local LLM via Ollama** — no data leaves the machine
- Presents a daily briefing as a terminal/web dashboard
- Optionally replies to email threads via Graph's reply API

---

## Stack

| Layer | Technology |
|---|---|
| Package manager | **uv** (Astral) — not pip-tools, not pip |
| Python version | **3.12** (better library compat than 3.13 right now) |
| Graph auth | MSAL + keyring (see Security section) |
| Graph client | httpx async + delta queries |
| LLM | Ollama HTTP API (local, no network) |
| Agent orchestration | LangGraph |
| Data validation | Pydantic v2 |
| Persistence | aiosqlite (SQLite WAL mode) |
| Tests | pytest + pytest-asyncio + pytest-httpx + pytest-cov |

---

## Project structure

```
src/briefing_agent/
├── models.py             # shared Pydantic types (MessageEnvelope, TriagedMessage, …)
├── config.py             # pydantic-settings config
├── memory.py             # SQLite: runs, classified_messages, delta_tokens
├── prompts.py            # prompt templates + format helpers
├── token_budget.py       # char-based token estimation + batch splitter
├── graph_client/
│   ├── auth.py             # MSAL + keyring/file token storage
│   ├── mail.py             # delta queries, 429 retry, attachment metadata
│   └── calendar.py         # calendar event fetcher
├── llm/
│   └── agent.py            # Ollama async client, JSON schema enforcement
├── pipeline/
│   ├── email_cleaner.py    # HTML → plain text, attachment notes, quoted-reply stripping
├── │   ├── processor.py    # thread grouping, token budget, LLM batching, TriageResult
│   ├── briefing_writer.py  # formats TriageResult → markdown/rich output
│   └── action_exports.py   # export to CSV / todo formats
└── main.py               # entrypoint

scripts/
├── run_assistant.sh
└── com.briefing-agent.plist  # macOS launchd (preferred over cron)

tests/
├── test_token_budget.py
├── test_prompts.py
├── test_email_cleaner.py
├── test_memory.py
├── test_graph_mail.py
├── test_agent.py
└── test_processor.py
```

---

## Key design decisions

### JSON schema enforcement (not just `format: "json"`)
Ollama's `format` field accepts a full JSON schema (Pydantic `.model_json_schema()`).
We pass `TriagedMessageList.model_json_schema()` directly — grammar-constrained decoding
enforces the exact shape. `json_repair` is imported as a last resort only.

### Delta queries (not date filtering)
Graph API `$delta` endpoint tracks changes server-side. We store the `@odata.deltaLink`
in SQLite and resume from it on each run. If the token expires (410 Gone), we fall back
to a full fetch automatically. This prevents missing or re-processing emails on crash.

### Token budget management
`token_budget.py` uses a character-based approximation (~4 chars/token, zero extra deps)
to gate batches against `num_ctx` before sending. Bodies are truncated per-message to
fit. Fixed batch size (5) alone is not sufficient — a single HTML thread can be 3000+ tokens.

### Thread grouping
`processor.py` groups `MessageEnvelope` objects by `thread_id` before batching.
Thread siblings are passed together in a `[THREAD]` block so the LLM sees reply-chain
context. This significantly improves classification accuracy for reply-all chains.

### SQLite transactions + run status
Every run is tracked in the `runs` table with status `in_progress → complete/failed`.
All classifications for a run are committed in a single transaction. Crashes leave the
run in `in_progress`; `detect_stale_runs()` surfaces these on next startup.

### macOS scheduling: launchd over cron
`scripts/com.briefing-agent.plist` uses `launchd` with `StartCalendarInterval`.
Unlike cron, launchd fires on next wake if the machine was asleep at the scheduled time.
Cron silently misses the window. See the plist for installation instructions.

---

## Security

### OAuth token storage
`graph_client/auth.py` tries `keyring` first (macOS Keychain / Windows Credential Manager
/ Secret Service on Linux) before falling back to `data/token.json`.

**Risk if using the file fallback:** `data/token.json` contains a live OAuth access token
for your mailbox. Anyone with read access to that file can read your email.
- Do not commit `data/` to version control (it is in `.gitignore`).
- Set `USE_KEYRING=true` in `.env` (the default) to use the secure store.
- The fallback logs an explicit warning on every use.

### Local-only LLM
All email content is processed by Ollama running on `localhost`. Nothing is sent to
external APIs. This is a deliberate architectural constraint — do not add cloud LLM
integrations without explicit discussion.

---

## Running

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/briefing_agent --cov-report=term-missing

# Run the agent
uv run briefing-agent
```

---

## Phase tracker

| Phase | Status | Notes |
|---|---|---|
| 0 — Project scaffold | ✅ Done | uv, pyproject.toml, src layout |
| 1 — Graph client | ✅ Done | Delta queries, 429 retry, attachment metadata, keyring auth |
| 2 — Email cleaning | ✅ Done | html2text + BS4 fallback, attachment notes, quoted-reply stripping |
| 3 — LLM triage | ✅ Done | JSON schema enforcement, token budget, thread grouping, prompts |
| 4 — Memory + runs | ✅ Done | SQLite WAL, run transactions, delta_tokens table |
| 5 — Briefing output | 🔧 In progress | Terminal + FastAPI dashboard |
| 6 — Scheduling | ✅ Done | launchd plist (macOS), run_assistant.sh |
| 7 — Test coverage | ✅ Done | pytest-httpx for all HTTP, pytest-asyncio for async |
