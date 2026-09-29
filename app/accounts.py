from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.config import Settings
from app.db import DataUnavailable, query

router = APIRouter(prefix="/v1")

TABLE = "retirement_distributions.yodlee_held_away_accounts"

LIST_COLUMNS = (
    "account_id",
    "provider_id",
    "provider_name",
    "account_number",
    "account_name",
    "displayed_name",
    "container",
    "account_type",
    "account_status",
    "is_asset",
    "include_in_net_worth",
    "balance_amount",
    "balance_currency",
    "current_balance_amount",
    "available_balance_amount",
    "last_updated",
)

DETAIL_COLUMNS = (
    "account_id",
    "provider_account_id",
    "provider_id",
    "provider_name",
    "account_number",
    "account_name",
    "displayed_name",
    "container",
    "account_type",
    "account_status",
    "user_classification",
    "classification",
    "aggregation_source",
    "is_asset",
    "is_manual",
    "include_in_net_worth",
    "balance_amount",
    "balance_currency",
    "current_balance_amount",
    "current_balance_currency",
    "available_balance_amount",
    "available_balance_currency",
    "running_balance_amount",
    "running_balance_currency",
    "available_credit_amount",
    "available_credit_currency",
    "total_credit_line_amount",
    "total_credit_line_currency",
    "available_cash_amount",
    "available_cash_currency",
    "total_cash_limit_amount",
    "total_cash_limit_currency",
    "last_payment_amount",
    "last_payment_currency",
    "last_payment_date",
    "apr",
    "cash_apr",
    "vested_balance_amount",
    "vested_balance_currency",
    "unvested_balance_amount",
    "unvested_balance_currency",
    "margin_balance_amount",
    "margin_balance_currency",
    "short_balance_amount",
    "short_balance_currency",
    "buying_power_amount",
    "buying_power_currency",
    "created_date",
    "last_updated",
    "ingestion_timestamp",
)

MONEY_COLUMNS = {
    "balance_amount",
    "current_balance_amount",
    "available_balance_amount",
    "running_balance_amount",
    "available_credit_amount",
    "total_credit_line_amount",
    "available_cash_amount",
    "total_cash_limit_amount",
    "last_payment_amount",
    "apr",
    "cash_apr",
    "vested_balance_amount",
    "unvested_balance_amount",
    "margin_balance_amount",
    "short_balance_amount",
    "buying_power_amount",
}

FILTERS = ("container", "account_type", "account_status", "provider_name", "provider_id")


def money(value: Any) -> str | None:
    if value is None:
        return None
    return f"{Decimal(str(value)):.4f}"


def as_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, Decimal)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "1", "t", "yes"}:
        return True
    if text in {"false", "0", "f", "no"}:
        return False
    return None


def json_value(column: str, value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if column in MONEY_COLUMNS:
        return money(value)
    if column in {"is_asset", "is_manual", "include_in_net_worth"}:
        return as_bool(value)
    return value


def row_json(row: dict[str, Any], columns: tuple[str, ...]) -> dict[str, Any]:
    return {column: json_value(column, row.get(column)) for column in columns}


def _where(filters: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    for name in FILTERS:
        value = filters.get(name)
        if value is None or value == "":
            continue
        clauses.append(f"{name} = %({name})s")
        params[name] = value
    if filters.get("last_updated_day"):
        clauses.append("to_date(last_updated) = %(last_updated_day)s")
        params["last_updated_day"] = filters["last_updated_day"]
    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def build_list_sql(filters: dict[str, Any], limit: int, offset: int) -> tuple[str, dict[str, Any]]:
    where, params = _where(filters)
    params["limit"] = int(limit)
    params["offset"] = int(offset)
    columns = ", ".join(LIST_COLUMNS)
    sql = (
        f"SELECT {columns} FROM {TABLE}{where} "
        "ORDER BY last_updated DESC LIMIT %(limit)s OFFSET %(offset)s"
    )
    return sql, params


def build_detail_sql() -> tuple[str, str]:
    columns = ", ".join(DETAIL_COLUMNS)
    return f"SELECT {columns} FROM {TABLE} WHERE account_id = %(account_id)s", "account_id"


def build_summary_sql(filters: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    where, params = _where(filters)
    sql = (
        "SELECT balance_currency, is_asset, include_in_net_worth, container, "
        "COUNT(*) AS account_count, SUM(balance_amount) AS balance_amount "
        f"FROM {TABLE}{where} "
        "GROUP BY balance_currency, is_asset, include_in_net_worth, container"
    )
    return sql, params


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    currencies: dict[str, dict[str, Any]] = {}
    for row in rows:
        currency = row.get("balance_currency") or "UNKNOWN"
        bucket = currencies.setdefault(
            currency,
            {
                "assets": Decimal("0"),
                "liabilities": Decimal("0"),
                "included_account_count": 0,
                "excluded_account_count": 0,
                "containers": {},
            },
        )
        count = int(row.get("account_count") or 0)
        balance = row.get("balance_amount")
        amount = Decimal(str(balance)) if balance is not None else None
        included = as_bool(row.get("include_in_net_worth"))
        asset = as_bool(row.get("is_asset"))
        if included:
            bucket["included_account_count"] += count
            if amount is not None and asset is True:
                bucket["assets"] += amount
            elif amount is not None and asset is False:
                bucket["liabilities"] += amount
        else:
            bucket["excluded_account_count"] += count
        container = row.get("container") or "unknown"
        containers = bucket["containers"]
        entry = containers.setdefault(container, {"account_count": 0, "balance": Decimal("0")})
        entry["account_count"] += count
        if amount is not None:
            entry["balance"] += amount

    payload = []
    for currency in sorted(currencies):
        bucket = currencies[currency]
        assets = bucket["assets"]
        liabilities = bucket["liabilities"]
        payload.append(
            {
                "currency": currency,
                "net_worth": money(assets - liabilities),
                "assets": money(assets),
                "liabilities": money(liabilities),
                "included_account_count": bucket["included_account_count"],
                "excluded_account_count": bucket["excluded_account_count"],
                "by_container": [
                    {
                        "container": name,
                        "account_count": bucket["containers"][name]["account_count"],
                        "balance": money(bucket["containers"][name]["balance"]),
                    }
                    for name in sorted(bucket["containers"])
                ],
            }
        )
    return {"currencies": payload}


def get_account_source(request: Request):
    return request.app.state.account_source


def _filters(
    container: str | None,
    account_type: str | None,
    account_status: str | None,
    provider_name: str | None,
    provider_id: str | None,
    last_updated_day: date | None,
) -> dict[str, Any]:
    return {
        "container": container,
        "account_type": account_type,
        "account_status": account_status,
        "provider_name": provider_name,
        "provider_id": provider_id,
        "last_updated_day": last_updated_day.isoformat() if last_updated_day else None,
    }


@router.get("/accounts/summary")
def account_summary(
    container: str | None = None,
    account_type: str | None = None,
    account_status: str | None = None,
    provider_name: str | None = None,
    provider_id: str | None = None,
    last_updated_day: date | None = None,
    source=Depends(get_account_source),
) -> dict[str, Any]:
    filters = _filters(
        container, account_type, account_status, provider_name, provider_id, last_updated_day
    )
    try:
        rows = source.summary(filters)
    except DataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return summarize(rows)


@router.get("/accounts")
def list_accounts(
    container: str | None = None,
    account_type: str | None = None,
    account_status: str | None = None,
    provider_name: str | None = None,
    provider_id: str | None = None,
    last_updated_day: date | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    source=Depends(get_account_source),
) -> dict[str, Any]:
    filters = _filters(
        container, account_type, account_status, provider_name, provider_id, last_updated_day
    )
    try:
        rows = source.list_accounts(filters, limit, offset)
    except DataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "accounts": [row_json(row, LIST_COLUMNS) for row in rows],
        "limit": limit,
        "offset": offset,
    }


@router.get("/accounts/{account_id}")
def get_account(account_id: int, source=Depends(get_account_source)) -> dict[str, Any]:
    try:
        row = source.get_account(account_id)
    except DataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return row_json(row, DETAIL_COLUMNS)


class ImpalaAccounts:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def list_accounts(self, filters: dict[str, Any], limit: int, offset: int) -> list[dict[str, Any]]:
        sql, params = build_list_sql(filters, limit, offset)
        return query(self.settings, sql, params)

    def get_account(self, account_id: int) -> dict[str, Any] | None:
        sql, param = build_detail_sql()
        rows = query(self.settings, sql, {param: account_id})
        return rows[0] if rows else None

    def summary(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        sql, params = build_summary_sql(filters)
        return query(self.settings, sql, params)
