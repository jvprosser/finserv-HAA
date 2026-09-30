from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.auth import get_settings, require_api_key
from app.config import Settings

from app.features import FEATURE_NAMES

ACTIONS = ("create_task", "create_opportunity", "update_account")
EVENT_NAMES = (
    "CONTRIBUTIONS_STOPPED_OVER_90_DAYS",
    "HELDAWAY_LIQUIDATION_DETECTED",
    "COMPETITOR_OUTFLOW_TREND",
    "RETIREMENT_INCOME_COMMENCED",
    "EMPLOYMENT_PROVIDER_CHANGED",
    "HELDAWAY_DATA_CONNECTION_LOST",
    "HELDAWAY_CD_MATURED",
    "EDUCATION_EXPENSE_PHASE_STARTED",
    "HIGH_COST_DEBT_LEVERAGE_DETECTED",
    "REAL_ESTATE_LIQUIDITY_EVENT",
    "IDLE_CASH_DRAG_IDENTIFIED",
)
TEXT_FIELDS = ("description", "business_opportunity", "suggested_next_steps", "cel")


@dataclass
class Rule:
    event_name: str
    action: str
    description: str
    business_opportunity: str
    suggested_next_steps: str
    cel: str
    features: list[str]

    def public(self) -> dict:
        return {
            "event_name": self.event_name,
            "action": self.action,
            "description": self.description,
            "business_opportunity": self.business_opportunity,
            "suggested_next_steps": self.suggested_next_steps,
            "cel": self.cel,
            "features": list(self.features),
        }


class RuleValidationError(Exception):
    def __init__(self, errors: list[dict]) -> None:
        self.errors = errors
        super().__init__(str(errors))


def cel_identifiers(expression: str) -> set[str]:
    import lark

    import celpy

    tree = celpy.Environment().compile(expression)
    found: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, lark.Token):
            if node.type.lower() == "ident":
                found.add(str(node))
            return
        if isinstance(node, lark.Tree):
            for child in node.children:
                walk(child)

    walk(tree)
    return found


def _error(event_name: str | None, field: str, message: str) -> dict:
    return {"event_name": event_name, "field": field, "message": message}


def parse_rules(text: str) -> list[Rule]:
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RuleValidationError([_error(None, "yaml", f"YAML did not parse: {exc}")]) from exc
    if not isinstance(loaded, list):
        raise RuleValidationError([_error(None, "yaml", "The catalog must be a list of events")])

    errors: list[dict] = []
    rules: list[Rule] = []
    seen: list[str] = []
    known = set(FEATURE_NAMES)
    for index, item in enumerate(loaded):
        if not isinstance(item, dict):
            errors.append(_error(None, "yaml", f"Event {index + 1} is not a mapping"))
            continue
        name = item.get("event_name")
        seen.append(name if isinstance(name, str) else "")
        if name not in EVENT_NAMES:
            errors.append(_error(str(name), "event_name", "Unknown event name"))
        action = item.get("action")
        if action not in ACTIONS:
            errors.append(_error(name, "action", "action must be create_task, create_opportunity, or update_account"))
        texts: dict[str, str] = {}
        for field in TEXT_FIELDS:
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(_error(name, field, f"{field} is required"))
                texts[field] = ""
            else:
                texts[field] = value.strip()
        raw_features = item.get("features")
        if not isinstance(raw_features, list) or not raw_features:
            errors.append(_error(name, "features", "features must list the measurements the CEL reads"))
            raw_features = []
        features = [str(feature) for feature in raw_features]
        unknown = [feature for feature in features if feature not in known]
        if unknown:
            errors.append(_error(name, "features", f"Unknown features: {', '.join(unknown)}"))
        identifiers: set[str] = set()
        if texts.get("cel"):
            try:
                identifiers = cel_identifiers(texts["cel"])
            except Exception as exc:
                errors.append(_error(name, "cel", f"CEL did not compile: {exc}"))
            else:
                undeclared = sorted(identifiers - set(features))
                if undeclared:
                    errors.append(
                        _error(name, "cel", f"CEL references features not listed on the rule: {', '.join(undeclared)}")
                    )
                outside = sorted(identifiers - known)
                if outside:
                    errors.append(_error(name, "cel", f"CEL references unknown features: {', '.join(outside)}"))
        rules.append(
            Rule(
                event_name=str(name),
                action=str(action),
                description=texts.get("description", ""),
                business_opportunity=texts.get("business_opportunity", ""),
                suggested_next_steps=texts.get("suggested_next_steps", ""),
                cel=texts.get("cel", ""),
                features=features,
            )
        )

    missing = [name for name in EVENT_NAMES if name not in seen]
    extra = [name for name in seen if name and seen.count(name) > 1]
    if missing:
        errors.append(_error(None, "event_name", f"Missing events: {', '.join(missing)}"))
    if extra:
        errors.append(_error(None, "event_name", f"Duplicate events: {', '.join(sorted(set(extra)))}"))
    if errors:
        raise RuleValidationError(errors)
    return rules


def validate_cel_features(event_name: str, cel: str, features: list[str]) -> None:
    known = set(FEATURE_NAMES)
    errors: list[dict] = []
    if not isinstance(features, list) or not features:
        errors.append(_error(event_name, "features", "features must list the measurements the CEL reads"))
        features = []
    names = [str(feature) for feature in features]
    unknown = [feature for feature in names if feature not in known]
    if unknown:
        errors.append(_error(event_name, "features", f"Unknown features: {', '.join(unknown)}"))
    if not isinstance(cel, str) or not cel.strip():
        errors.append(_error(event_name, "cel", "cel is required"))
    else:
        try:
            identifiers = cel_identifiers(cel.strip())
        except Exception as exc:
            errors.append(_error(event_name, "cel", f"CEL did not compile: {exc}"))
        else:
            undeclared = sorted(identifiers - set(names))
            if undeclared:
                errors.append(
                    _error(event_name, "cel", f"CEL references features not listed on the rule: {', '.join(undeclared)}")
                )
            outside = sorted(identifiers - known)
            if outside:
                errors.append(_error(event_name, "cel", f"CEL references unknown features: {', '.join(outside)}"))
    if errors:
        raise RuleValidationError(errors)


def load_rules(path: Path) -> list[Rule]:
    return parse_rules(path.read_text())


router = APIRouter(prefix="/v1", dependencies=[Depends(require_api_key)])


class RulesBody(BaseModel):
    yaml: str


class RuleDraftBody(BaseModel):
    prompt: str
    event_name: str


@router.get("/rules")
def read_rules(settings: Settings = Depends(get_settings)) -> dict:
    text = settings.rules_path.read_text()
    try:
        rules = parse_rules(text)
    except RuleValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors) from exc
    return {"yaml": text, "events": [rule.public() for rule in rules]}


@router.put("/rules")
def write_rules(body: RulesBody, settings: Settings = Depends(get_settings)) -> dict:
    try:
        rules = save_rules(settings.rules_path, body.yaml)
    except RuleValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors) from exc
    return {"yaml": body.yaml, "events": [rule.public() for rule in rules]}


@router.post("/rules/draft")
def draft_rule(body: RuleDraftBody, request: Request, settings: Settings = Depends(get_settings)) -> dict:
    from app.llm import LLMError, rule_draft, run_complete

    if body.event_name not in EVENT_NAMES:
        raise HTTPException(status_code=404, detail="Unknown event")
    if not (body.prompt or "").strip():
        raise HTTPException(status_code=422, detail="prompt is required")
    current = next(rule for rule in load_rules(settings.rules_path) if rule.event_name == body.event_name)
    try:
        proposed = rule_draft(
            body.event_name,
            body.prompt.strip(),
            current.cel,
            lambda messages: run_complete(request, messages),
        )
        validate_cel_features(body.event_name, proposed["cel"], proposed["features"])
    except LLMError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except RuleValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors) from exc
    return {"event_name": body.event_name, "cel": proposed["cel"], "features": proposed["features"]}


def save_rules(path: Path, text: str) -> list[Rule]:
    rules = parse_rules(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text)
    os.replace(temporary, path)
    return rules
