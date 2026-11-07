"""Provider-agnostic JSON completion. Returns None when no provider is configured or the
call fails, so every caller must have a rule-based fallback."""

import json
import logging
import re

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)


def is_enabled() -> bool:
    s = get_settings()
    return (s.llm_provider == "openai" and bool(s.openai_api_key)) or (
        s.llm_provider == "anthropic" and bool(s.anthropic_api_key)
    )


def _extract_json(text: str):
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1)
    return json.loads(text)


def complete_json(system: str, user: str, timeout: float = 60.0):
    if not is_enabled():
        return None
    s = get_settings()
    try:
        if s.llm_provider == "openai":
            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {s.openai_api_key}"},
                json={
                    "model": s.openai_model,
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            return _extract_json(resp.json()["choices"][0]["message"]["content"])
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": s.anthropic_api_key, "anthropic-version": "2023-06-01"},
            json={
                "model": s.anthropic_model,
                "max_tokens": 4096,
                "temperature": 0.2,
                "system": system + "\nRespond with a single JSON object only.",
                "messages": [{"role": "user", "content": user}],
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        return _extract_json(resp.json()["content"][0]["text"])
    except Exception:  # noqa: BLE001 - any failure falls back to rules
        log.exception("LLM call failed; using rule-based fallback")
        return None
