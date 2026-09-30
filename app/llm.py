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
    "Use only facts in the JSON. Do not invent balances, merchants, dates, account types, or causes. "
    "Name the account with account_name or displayed_name. "
    "Use account_type exactly as given; never call an account a savings or checking account "
    "unless account_type is SAVINGS or CHECKING. "
    "If a transaction description names a product such as 401k, do not describe the account as a different product. "
    "Do not mention CEL, rules, event names, JSON, field names, models, or disclaimers. "
    "Do not give investment advice. Write 4 to 6 sentences. "
    "Reply with the advisor note only. No planning, no restating these instructions, no </think>."
)
RULE_SYSTEM = (
    "You propose a CEL expression for one named wealth event. "
    "Reply with JSON only, no markdown: {\"cel\": \"...\", \"features\": [\"...\"]}. "
    "Use only these feature names: "
    + ", ".join(FEATURE_NAMES)
    + ". The CEL must compile. Do not change the event name. "
    "Reply with the JSON only. No planning, no restating these instructions, no </think>."
)
PLANNING_PREFIXES = (
    "we need to",
    "we have json",
    "we must",
    "we can say",
    "we'll ",
    "let's ",
    "lets ",
    "make sure to",
    "so we need",
    "so we can",
    "write 4",
    "write 5",
    "write 6",
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


def _is_planning_line(line: str) -> bool:
    lowered = line.strip().lower()
    if not lowered:
        return True
    return any(lowered.startswith(prefix) for prefix in PLANNING_PREFIXES)


def strip_reasoning(text: str) -> str:
    raw = text or ""
    marker = "</think>"
    found = raw.lower().rfind(marker)
    if found >= 0:
        raw = raw[found + len(marker) :]
    raw = raw.replace("<think>", "").strip()
    kept: list[str] = []
    skipping = True
    for line in raw.splitlines():
        if skipping and _is_planning_line(line):
            continue
        skipping = False
        kept.append(line)
    return "\n".join(kept).strip()


def chat_request_body(settings: Settings, messages: list[dict[str, str]]) -> dict[str, Any]:
    return {
        "model": settings.llm_model_id.strip(),
        "messages": messages,
        "temperature": 0.2,
        "top_p": 0.7,
        "max_tokens": settings.llm_max_tokens,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }


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
            json=chat_request_body(settings, messages),
            timeout=settings.llm_timeout,
        )
    except httpx.HTTPError as exc:
        raise LLMError(f"LLM request failed: {exc}", 502) from exc
    if response.status_code >= 400:
        raise LLMError(f"LLM request failed: {response.text}", 502)
    try:
        body = response.json()
        message = body["choices"][0]["message"]
        content = message.get("content") if isinstance(message, dict) else None
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LLMError("LLM response was missing content", 502) from exc
    if not isinstance(content, str):
        raise LLMError("LLM response was missing content", 502)
    cleaned = strip_reasoning(content)
    if not cleaned:
        raise LLMError("LLM response was missing content", 502)
    return cleaned


Completer = Callable[[list[dict[str, str]]], str]


def run_complete(request: Any, messages: list[dict[str, str]]) -> str:
    override = getattr(request.app.state, "llm_complete", None)
    if override is not None:
        return override(messages)
    return complete(request.app.state.settings, messages)


def brief_payload(evaluated: dict[str, Any]) -> dict[str, Any]:
    evidence = evaluated.get("evidence") or {}
    return {
        "situation": evaluated.get("description"),
        "suggested_next_steps": evaluated.get("suggested_next_steps"),
        "measurements": [
            {"name": str(name).replace("_", " "), "value": value} for name, value in evidence.items()
        ],
        "accounts": evaluated.get("accounts") or [],
        "transactions": evaluated.get("transactions") or [],
    }


def advisor_brief(evaluated: dict[str, Any], complete_fn: Completer) -> str:
    return strip_reasoning(
        complete_fn(
            [
                {"role": "system", "content": BRIEF_SYSTEM},
                {"role": "user", "content": json.dumps(brief_payload(evaluated))},
            ]
        )
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
    payload = parse_json_object(strip_reasoning(raw))
    cel = str(payload.get("cel") or "").strip()
    features = payload.get("features")
    if not cel:
        raise LLMError("The model did not return a CEL expression", 502)
    if not isinstance(features, list) or not features:
        raise LLMError("The model did not return a features list", 502)
    return {"cel": cel, "features": [str(name) for name in features]}
