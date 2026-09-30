from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

import httpx

from app.config import Settings
from app.features import FEATURE_NAMES

JWT_PATH = Path("/tmp/jwt")
BRIEF_SYSTEM = (
    "You write a short internal note for a wealth advisor. "
    "Use only facts in the JSON. Do not invent balances, merchants, dates, or events. "
    "Do not give investment advice. Write 4 to 6 sentences. "
    "Cite CEL field names and table values that appear in the JSON."
)
RULE_SYSTEM = (
    "You propose a CEL expression for one named wealth event. "
    "Reply with JSON only, no markdown: {\"cel\": \"...\", \"features\": [\"...\"]}. "
    "Use only these feature names: "
    + ", ".join(FEATURE_NAMES)
    + ". The CEL must compile. Do not change the event name."
)


class LLMError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        self.status_code = status_code
        super().__init__(message)


def resolve_api_key(settings: Settings) -> str:
    key = (settings.llm_api_key or "").strip()
    if key:
        return key
    env = (os.environ.get("CDP_TOKEN") or "").strip()
    if env:
        return env
    if JWT_PATH.is_file():
        try:
            payload = json.loads(JWT_PATH.read_text())
        except (OSError, ValueError):
            return ""
        return str(payload.get("access_token") or "").strip()
    return ""


def llm_configured(settings: Settings) -> bool:
    return bool((settings.llm_base_url or "").strip() and resolve_api_key(settings) and (settings.llm_model_id or "").strip())


def chat_completions_url(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def parse_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        raise LLMError("The model did not return JSON", 502)
    try:
        payload = json.loads(raw[start : end + 1])
    except ValueError as exc:
        raise LLMError("The model did not return JSON", 502) from exc
    if not isinstance(payload, dict):
        raise LLMError("The model did not return JSON", 502)
    return payload


def complete(settings: Settings, messages: list[dict[str, str]]) -> str:
    if not llm_configured(settings):
        raise LLMError("LLM is not configured", 503)
    try:
        response = httpx.post(
            chat_completions_url(settings.llm_base_url),
            headers={
                "Authorization": f"Bearer {resolve_api_key(settings)}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.llm_model_id.strip(),
                "messages": messages,
                "temperature": 0.2,
                "top_p": 0.7,
                "max_tokens": settings.llm_max_tokens,
                "stream": False,
            },
            timeout=settings.llm_timeout,
        )
    except httpx.HTTPError as exc:
        raise LLMError(f"LLM request failed: {exc}", 502) from exc
    if response.status_code >= 400:
        raise LLMError(f"LLM request failed: {response.text}", 502)
    try:
        body = response.json()
        content = body["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LLMError("LLM response was missing content", 502) from exc
    if not isinstance(content, str) or not content.strip():
        raise LLMError("LLM response was missing content", 502)
    return content.strip()


Completer = Callable[[list[dict[str, str]]], str]


def run_complete(request: Any, messages: list[dict[str, str]]) -> str:
    override = getattr(request.app.state, "llm_complete", None)
    if override is not None:
        return override(messages)
    return complete(request.app.state.settings, messages)


def advisor_brief(evaluated: dict[str, Any], complete_fn: Completer) -> str:
    payload = {
        "event_name": evaluated.get("event_name"),
        "description": evaluated.get("description"),
        "cel": evaluated.get("cel"),
        "evidence": evaluated.get("evidence") or {},
        "accounts": evaluated.get("accounts") or [],
        "transactions": evaluated.get("transactions") or [],
        "suggested_next_steps": evaluated.get("suggested_next_steps"),
    }
    return complete_fn(
        [
            {"role": "system", "content": BRIEF_SYSTEM},
            {"role": "user", "content": json.dumps(payload)},
        ]
    )


def rule_draft(event_name: str, prompt: str, current_cel: str, complete_fn: Completer) -> dict[str, Any]:
    user = json.dumps(
        {
            "event_name": event_name,
            "request": prompt,
            "current_cel": current_cel,
        }
    )
    raw = complete_fn(
        [
            {"role": "system", "content": RULE_SYSTEM},
            {"role": "user", "content": user},
        ]
    )
    payload = parse_json_object(raw)
    cel = str(payload.get("cel") or "").strip()
    features = payload.get("features")
    if not cel:
        raise LLMError("The model did not return a CEL expression", 502)
    if not isinstance(features, list) or not features:
        raise LLMError("The model did not return a features list", 502)
    return {"cel": cel, "features": [str(name) for name in features]}
