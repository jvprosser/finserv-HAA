from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.auth import require_api_key
from app.config import Settings
from app.db import DataUnavailable
from app.features import MONEY_FEATURES, pick_supporting
from app.llm import llm_configured
from app.rules import Rule, RuleValidationError, load_rules
from app.sfdc import (
    LABELS,
    SOBJECTS,
    SalesforceError,
    account_fields,
    brief_path,
    description_body,
    lightning_path,
    opportunity_fields,
    record_key,
    task_fields,
)

router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])


class SfdcBody(BaseModel):
    brief: str = ""


def _features(request: Request, client_id: str) -> dict[str, Any]:
    loader: Callable[[str], dict[str, Any]] | None = request.app.state.feature_loader
    if loader is None:
        raise HTTPException(status_code=503, detail="CLIENT_ID_COLUMN is not set")
    try:
        return loader(client_id)
    except DataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _rules(settings: Settings) -> list[Rule]:
    try:
        return load_rules(settings.rules_path)
    except RuleValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="Rules file is missing") from exc


def _evidence_value(name: str, value: Any) -> Any:
    if name in MONEY_FEATURES:
        return f"{Decimal(str(value)):.4f}"
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _activation(rule: Rule, features: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for name in rule.features:
        value = features.get(name)
        if name in MONEY_FEATURES:
            values[name] = float(value)
        else:
            values[name] = int(value) if isinstance(value, float) and value.is_integer() else value
    return values


def _button(rule: Rule, client_id: str, status: str, settings: Settings) -> dict[str, Any]:
    path = lightning_path(client_id, rule.event_name)
    enabled = status == "matched"
    reason = None if enabled else status
    if enabled and rule.action == "update_account" and not settings.sfdc_account_external_id_field:
        enabled = False
        reason = "no_salesforce_account_field"
    return {
        "enabled": enabled,
        "label": LABELS[rule.action],
        "method": "POST",
        "path": path,
        "view_path": path,
        "brief_path": brief_path(client_id, rule.event_name),
        "disabled_reason": reason,
    }


def evaluate_rule(
    rule: Rule,
    features: dict[str, Any],
    client_id: str,
    settings: Settings,
    supporting: dict[str, Any] | None = None,
) -> dict[str, Any]:
    import celpy

    missing = [name for name in rule.features if features.get(name) is None]
    item: dict[str, Any] = {
        "event_name": rule.event_name,
        "action": rule.action,
        "description": rule.description,
        "business_opportunity": rule.business_opportunity,
        "suggested_next_steps": rule.suggested_next_steps,
        "cel": rule.cel,
    }
    if missing:
        item.update(
            {
                "status": "insufficient_data",
                "matched": False,
                "missing": missing,
                "sfdc_action": _button(rule, client_id, "insufficient_data", settings),
            }
        )
        return item
    try:
        environment = celpy.Environment()
        program = environment.program(environment.compile(rule.cel))
        matched = bool(program.evaluate(_activation(rule, features)))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=[{"event_name": rule.event_name, "field": "cel", "message": str(exc)}]) from exc
    status = "matched" if matched else "not_matched"
    item.update(
        {
            "status": status,
            "matched": matched,
            "evidence": {name: _evidence_value(name, features.get(name)) for name in rule.features},
            "sfdc_action": _button(rule, client_id, status, settings),
        }
    )
    if matched:
        accounts, transactions = pick_supporting(rule.features, supporting)
        item["accounts"] = accounts
        item["transactions"] = transactions
    return item


def _sfdc(request: Request):
    client = getattr(request.app.state, "sfdc_client", None)
    if client is not None:
        return client
    settings: Settings = request.app.state.settings
    if settings.sfdc_client_id and settings.sfdc_client_secret:
        rest = getattr(request.app.state, "sfdc_rest", None)
        if rest is None:
            from app.sfdc import SalesforceRest

            rest = SalesforceRest(settings)
            request.app.state.sfdc_rest = rest
        return rest
    if settings.demo_mode:
        from app.sfdc import MemorySalesforce

        memory = getattr(request.app.state, "memory_sfdc", None)
        if memory is None:
            memory = MemorySalesforce()
            request.app.state.memory_sfdc = memory
        return memory
    raise HTTPException(status_code=503, detail="Salesforce is not configured")


def _supporting(request: Request, client_id: str) -> dict[str, Any]:
    loader = getattr(request.app.state, "supporting_loader", None)
    if loader is None:
        return {"accounts": [], "transactions": []}
    try:
        return loader(client_id)
    except DataUnavailable:
        return {"accounts": [], "transactions": []}


def _account_name(supporting: dict[str, Any], client_id: str) -> str:
    names = []
    seen: set[str] = set()
    for row in supporting.get("accounts") or []:
        name = str(row.get("account_name") or "").strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return ", ".join(names) if names else client_id


def _complete(request: Request, messages: list[dict[str, str]]) -> str:
    from app.llm import LLMError, run_complete

    try:
        return run_complete(request, messages)
    except LLMError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def _fields(rule: Rule, key: str, evaluated: dict[str, Any], settings: Settings, brief: str = "") -> dict[str, Any]:
    body = description_body(
        rule.public(),
        evaluated.get("evidence") or {},
        evaluated.get("accounts") or [],
        evaluated.get("transactions") or [],
        brief,
    )
    if rule.action == "create_opportunity":
        return opportunity_fields(key, body, settings.sfdc_opportunity_stage)
    if rule.action == "create_task":
        return task_fields(key, body)
    return account_fields(body)


@router.get("/clients/{client_id}/events")
def client_events(
    client_id: str,
    request: Request,
    matched_only: bool = Query(False),
) -> dict[str, Any]:
    settings = request.app.state.settings
    features = _features(request, client_id)
    supporting = _supporting(request, client_id)
    events = [
        evaluate_rule(rule, features, client_id, settings, supporting)
        for rule in _rules(settings)
    ]
    if matched_only:
        events = [event for event in events if event["matched"]]
    return {
        "client_id": client_id,
        "account_name": _account_name(supporting, client_id),
        "llm_enabled": bool(getattr(request.app.state, "llm_complete", None)) or llm_configured(settings),
        "evaluated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "events": events,
    }


@router.post("/clients/{client_id}/events/{event_name}/brief")
def create_advisor_brief(client_id: str, event_name: str, request: Request) -> dict[str, str]:
    from app.llm import advisor_brief

    settings = request.app.state.settings
    rule = next((item for item in _rules(settings) if item.event_name == event_name), None)
    if rule is None:
        raise HTTPException(status_code=404, detail="Unknown event")
    evaluated = evaluate_rule(
        rule, _features(request, client_id), client_id, settings, _supporting(request, client_id)
    )
    if not evaluated["matched"]:
        raise HTTPException(status_code=409, detail="Event is not matched")
    brief = advisor_brief(evaluated, lambda messages: _complete(request, messages))
    return {"brief": brief, "event_name": event_name, "client_id": client_id}


@router.post("/clients/{client_id}/events/{event_name}/sfdc")
def create_sfdc_record(
    client_id: str,
    event_name: str,
    request: Request,
    body: SfdcBody | None = Body(default=None),
) -> dict[str, str]:
    settings = request.app.state.settings
    rule = next((item for item in _rules(settings) if item.event_name == event_name), None)
    if rule is None:
        raise HTTPException(status_code=404, detail="Unknown event")
    if rule.action == "update_account" and not settings.sfdc_account_external_id_field:
        raise HTTPException(status_code=422, detail="SFDC_ACCOUNT_EXTERNAL_ID_FIELD is not set")
    evaluated = evaluate_rule(
        rule, _features(request, client_id), client_id, settings, _supporting(request, client_id)
    )
    if not evaluated["matched"]:
        raise HTTPException(status_code=409, detail="Event is not matched")
    key = record_key(rule.action, event_name, client_id)
    brief = (body.brief if body else "").strip()
    fields = _fields(rule, key, evaluated, settings, brief)
    try:
        result, record_id = _sfdc(request).upsert(SOBJECTS[rule.action], key, fields, client_id)
    except SalesforceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return {"result": result, "sobject": SOBJECTS[rule.action], "id": record_id}


@router.get("/clients/{client_id}/events/{event_name}/sfdc")
def read_sfdc_record(client_id: str, event_name: str, request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    rule = next((item for item in _rules(settings) if item.event_name == event_name), None)
    if rule is None:
        raise HTTPException(status_code=404, detail="Unknown event")
    if rule.action == "update_account" and not settings.sfdc_account_external_id_field:
        raise HTTPException(status_code=422, detail="SFDC_ACCOUNT_EXTERNAL_ID_FIELD is not set")
    key = record_key(rule.action, event_name, client_id)
    try:
        record = _sfdc(request).fetch(SOBJECTS[rule.action], key, client_id)
    except SalesforceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    if record is None:
        raise HTTPException(status_code=404, detail="Salesforce record not found")
    return record
