"""Ollama LLM agent with JSON schema enforcement and robust retry logic.

JSON Schema Enforcement
-----------------------
We pass the Pydantic model's JSON schema directly to Ollama via the
`format` field. This instructs Ollama's grammar-constrained decoding
to enforce the exact shape. `json_repair` is a true last resort, not
a regular code path.

Retry Strategy
--------------
Ollama can fail with:
  - Connection errors (model loading, VRAM pressure)
  - Malformed JSON despite schema enforcement (rare but possible)
  - Timeout on very large batches

We retry with exponential back-off on all errors. After MAX_RETRIES
we raise so the processor can skip the batch and continue.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx
from json_repair import repair_json

from briefing_agent.models import TriagedMessage, TriagedMessageList
from briefing_agent.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BASE_BACKOFF_S = 2.0


class OllamaAgent:
    """Thin async wrapper around the Ollama /api/chat endpoint."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "mistral",
        num_ctx: int = 8192,
        temperature: float = 0.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.num_ctx = num_ctx
        self.temperature = temperature

    async def triage_batch(
        self,
        user_prompt: str,
    ) -> list[TriagedMessage]:
        """Send a triage prompt to Ollama and return parsed TriagedMessage list.

        Uses TriagedMessageList.model_json_schema() as the `format` field
        so Ollama enforces the exact output structure via grammar-constrained
        decoding. Falls back to json_repair on parse failure.
        """
        schema = TriagedMessageList.model_json_schema()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "format": schema,   # <-- schema enforcement, not just format:"json"
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_ctx": self.num_ctx,
            },
        }

        raw_content = await self._post_with_retry(payload)
        return self._parse_response(raw_content)

    async def _post_with_retry(self, payload: dict[str, Any]) -> str:
        url = f"{self.base_url}/api/chat"
        async with httpx.AsyncClient(timeout=120.0) as client:
            for attempt in range(_MAX_RETRIES):
                try:
                    resp = await client.post(url, json=payload)
                    resp.raise_for_status()
                    return resp.json()["message"]["content"]  # type: ignore[index]
                except (httpx.HTTPError, KeyError) as exc:
                    wait = _BASE_BACKOFF_S * (2 ** attempt)
                    logger.warning(
                        "Ollama request failed (attempt %d/%d): %s. Retrying in %.1fs.",
                        attempt + 1,
                        _MAX_RETRIES,
                        exc,
                        wait,
                    )
                    if attempt < _MAX_RETRIES - 1:
                        await asyncio.sleep(wait)
        raise RuntimeError(f"Ollama request failed after {_MAX_RETRIES} attempts.")

    def _parse_response(self, raw: str) -> list[TriagedMessage]:
        """Parse LLM output. Uses json_repair only as a true last resort."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("LLM output not valid JSON — attempting json_repair.")
            data = json.loads(repair_json(raw))

        # Ollama may return {"items": [...]} (TriagedMessageList) or [...] directly
        if isinstance(data, dict) and "items" in data:
            items = data["items"]
        elif isinstance(data, list):
            items = data
        else:
            logger.error("Unexpected LLM output shape: %r", data)
            return []

        results: list[TriagedMessage] = []
        for item in items:
            try:
                results.append(TriagedMessage.model_validate(item))
            except Exception as exc:
                logger.warning("Skipping invalid item from LLM: %s — %r", exc, item)
        return results
