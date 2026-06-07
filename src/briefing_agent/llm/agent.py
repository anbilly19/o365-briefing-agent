"""Thin LLM agent wrapper — OpenAI-compatible endpoint (Ollama, vLLM, LM Studio).

This is the ONLY place in the codebase that talks to the model.
The endpoint is swappable via env vars (LLM_BASE_URL, LLM_MODEL).

Key lesson from the video:
  - num_predict = output room  (too low → truncated JSON)
  - num_ctx     = input room   (too low → model loses the assignment entirely)
"""

from __future__ import annotations

import httpx
import logging

from briefing_agent.config import settings

logger = logging.getLogger(__name__)


class LLMAgent:
    """Wraps an OpenAI-compatible /chat/completions endpoint."""

    SYSTEM_PROMPT = (
        "You are a strict JSON output machine. "
        "Return ONLY valid JSON. No markdown, no explanations, no thinking blocks."
    )

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 300.0,
    ) -> None:
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.model = model or settings.llm_model
        self.timeout = timeout

    async def complete(
        self,
        prompt: str,
        num_predict: int | None = None,
        num_ctx: int | None = None,
    ) -> str:
        payload: dict = {  # type: ignore[type-arg]
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "response_format": {"type": "json_object"},
        }

        # Ollama-specific tuning params (ignored by non-Ollama endpoints)
        options: dict = {}  # type: ignore[type-arg]
        if num_predict is not None:
            options["num_predict"] = num_predict
        if num_ctx is not None:
            options["num_ctx"] = num_ctx
        if options:
            payload["options"] = options

        logger.debug("Sending %d prompt chars to %s", len(prompt), self.model)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
            )
            resp.raise_for_status()

        content = resp.json()["choices"][0]["message"]["content"]
        logger.debug("Received %d chars from model", len(content))
        return content
