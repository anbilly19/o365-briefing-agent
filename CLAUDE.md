# CLAUDE.md — Agent Guidelines for o365-briefing-agent

This file provides context and conventions for AI coding assistants (Claude, Copilot, etc.) working in this repository.

---

## Project Purpose

This is a **LangGraph-based email briefing agent** that:
1. Reads a user's O365 inbox and calendar via Microsoft Graph API
2. Passes content to a **local LLM** (no cloud LLM calls for user data)
3. Returns a structured daily briefing: summary + to-dos + waiting-on-others
4. Optionally replies inline to email threads via Graph `reply` API

---

## Key Conventions

### Package Manager
- This project uses **uv** exclusively. Do not use pip, poetry, or conda.
- Add dependencies with `uv add <package>`, dev deps with `uv add --dev <package>`.
- Lock file is `uv.lock`. Do not manually edit it.

### Python
- Python **3.12** (see `.python-version`).
- Use **Pydantic v2** models for all structured data (agent state, LLM outputs, API responses).
- Prefer `TypedDict` for LangGraph state definitions.
- Use `httpx` (async) for all HTTP clients (Graph API, LLM endpoint).

### LangGraph
- All graph definitions live in `src/briefing_agent/graph/`.
- `state.py` — defines `BriefingState` (TypedDict).
- `nodes.py` — pure async functions: `(state) -> dict` that return partial state updates.
- `graph.py` — assembles the graph via `StateGraph`, compiles, and exports `graph`.
- Do **not** put business logic in `graph.py`; keep it in `nodes.py`.

### Microsoft Graph Client
- Auth via **MSAL** device code or client credentials flow.
- All Graph calls live in `src/briefing_agent/graph_client/`.
- Do not hard-code tenant id, client id, or secrets — always read from env/config.
- Use `httpx.AsyncClient` with a shared token refresh middleware.

### Local LLM
- The LLM client (`src/briefing_agent/llm/client.py`) wraps an **OpenAI-compatible endpoint** (e.g., Ollama on `http://localhost:11434/v1`).
- Model name and endpoint are config-driven (env vars `LLM_BASE_URL`, `LLM_MODEL`).
- Always request **structured JSON output** using the model's JSON mode or function calling where supported.
- Do not make direct LangChain LLM calls — go through the thin wrapper so the endpoint is swappable.

### Environment Variables
All required env vars must be documented in `.env.example`. Key vars:
```
MS_TENANT_ID=
MS_CLIENT_ID=
MS_CLIENT_SECRET=
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=gemma3:12b
USER_EMAIL=
```

---

## Architecture Phases

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | Core LangGraph agent + Graph client + local LLM | 🚧 In progress |
| 2 | Preemptive daily dashboard (FastAPI + minimal UI) | ⏳ Planned |
| 3 | Reactive thread summariser (Graph webhooks + inline reply) | ⏳ Planned |
| 4 | Multi-user, Redis memory, hardening | ⏳ Planned |

---

## Do / Don't

| Do | Don't |
|----|-------|
| Use `uv add` for deps | Use pip install |
| Keep nodes pure async functions | Put logic in graph builder |
| Read secrets from env | Hard-code credentials |
| Use Pydantic models for LLM output | Parse raw JSON strings manually |
| Filter emails before LLM call | Send raw inbox dumps to the LLM |
| Use `httpx.AsyncClient` | Mix sync/async HTTP calls |

---

## Testing

- Tests live in `tests/`, mirroring `src/` structure.
- Use **pytest** + **pytest-asyncio** for async tests.
- Mock Graph API calls in unit tests; use real Graph in integration tests (tag `@pytest.mark.integration`).
- Run: `uv run pytest`
