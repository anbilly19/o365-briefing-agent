# O365 Briefing Agent

A preemptive, local-first daily briefing agent that connects to Microsoft 365 (Outlook, Calendar, Tasks) via the Microsoft Graph API, summarises your inbox and surfaces actionable to-dos — without sending you yet another email.

Powered by [LangGraph](https://github.com/langchain-ai/langgraph) and a locally hosted LLM (Ollama / vLLM / LM Studio).

---

## Features

- **Daily preemptive briefing** — runs at startup/cron, shows summary in a small web dashboard (no extra email)
- **Reactive thread assistant** — reply to any thread; the agent responds in the same email chain via Graph `reply` API
- **Fully local LLM** — no data leaves your machine except to Graph API
- **Structured output** — todos grouped by project, with urgency, deadline, and owner

---

## Architecture (phased)

```
Phase 1 – Core agent (Graph + LLM + LangGraph)
Phase 2 – Preemptive daily dashboard
Phase 3 – Reactive thread summariser (Graph webhooks)
Phase 4 – Multi-user, long-term memory, hardening
```

See [CLAUDE.md](./CLAUDE.md) for agent guidelines and [docs/architecture.md](./docs/architecture.md) for detailed design.

---

## Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (package manager)
- A Microsoft 365 account with app registration (see [docs/setup-graph.md](./docs/setup-graph.md))
- A local LLM server (Ollama recommended)

---

## Quickstart

```bash
# 1. Clone the repo
git clone https://github.com/anbilly19/o365-briefing-agent
cd o365-briefing-agent

# 2. Install dependencies via uv
uv sync

# 3. Copy and fill in environment variables
cp .env.example .env

# 4. Run the agent (Phase 1 CLI)
uv run python -m briefing_agent.main
```

---

## Project Structure

```
o365-briefing-agent/
├── src/
│   └── briefing_agent/
│       ├── __init__.py
│       ├── main.py          # CLI entrypoint
│       ├── graph/           # LangGraph definitions
│       │   ├── __init__.py
│       │   ├── nodes.py     # Graph nodes (fetch, summarise, format)
│       │   ├── state.py     # AgentState TypedDict
│       │   └── graph.py     # Graph builder
│       ├── graph_client/    # Microsoft Graph API client
│       │   ├── __init__.py
│       │   ├── auth.py      # MSAL token acquisition
│       │   ├── mail.py      # Fetch messages / reply
│       │   └── calendar.py  # Fetch events
│       ├── llm/             # Local LLM client
│       │   ├── __init__.py
│       │   └── client.py    # HTTP wrapper (Ollama / OpenAI-compatible)
│       └── models.py        # Pydantic output schemas
├── tests/
├── docs/
├── .env.example
├── .python-version
├── pyproject.toml
├── CLAUDE.md
└── README.md
```

---

## License

MIT
