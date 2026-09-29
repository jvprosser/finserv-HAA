from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from app.features import FEATURE_NAMES

DEMO_CLIENT = "C123"

DEMO_FEATURES: dict[str, dict[str, Any]] = {
    DEMO_CLIENT: {
        "days_since_last_contribution": 120,
        "max_balance_drop_30d": 48000.0,
        "holdings_value_change_30d": -12000.0,
        "competitor_transfer_count_90d": 4,
        "retirement_income_started": 1,
        "payroll_source_changed": 0,
        "disconnected_account_count": 1,
        "cd_maturity_inflow_amount": 0.0,
        "education_debit_count_90d": 0,
        "margin_interest_debit_count_90d": 0,
        "large_real_estate_wire_amount": 0.0,
        "mortgage_payments_stopped": 0,
        "idle_cash_days_above_100k": 95,
    }
}


def demo_features(client_id: str) -> dict[str, Any]:
    found = DEMO_FEATURES.get(client_id)
    if found is None:
        return {name: None for name in FEATURE_NAMES}
    return dict(found)


def _account(**values: Any) -> dict[str, Any]:
    row = {
        "account_id": None,
        "provider_account_id": None,
        "provider_id": None,
        "provider_name": None,
        "account_number": None,
        "account_name": None,
        "displayed_name": None,
        "container": None,
        "account_type": None,
        "account_status": "ACTIVE",
        "user_classification": "PERSONAL",
        "classification": None,
        "aggregation_source": "USER",
        "is_asset": True,
        "is_manual": False,
        "include_in_net_worth": True,
        "balance_amount": None,
        "balance_currency": "USD",
        "current_balance_amount": None,
        "current_balance_currency": "USD",
        "available_balance_amount": None,
        "available_balance_currency": "USD",
        "running_balance_amount": None,
        "running_balance_currency": "USD",
        "available_credit_amount": None,
        "available_credit_currency": None,
        "total_credit_line_amount": None,
        "total_credit_line_currency": None,
        "available_cash_amount": None,
        "available_cash_currency": None,
        "total_cash_limit_amount": None,
        "total_cash_limit_currency": None,
        "last_payment_amount": None,
        "last_payment_currency": None,
        "last_payment_date": None,
        "apr": None,
        "cash_apr": None,
        "vested_balance_amount": None,
        "vested_balance_currency": None,
        "unvested_balance_amount": None,
        "unvested_balance_currency": None,
        "margin_balance_amount": None,
        "margin_balance_currency": None,
        "short_balance_amount": None,
        "short_balance_currency": None,
        "buying_power_amount": None,
        "buying_power_currency": None,
        "created_date": datetime(2024, 1, 15, 12, 0, 0),
        "last_updated": datetime(2026, 9, 27, 8, 0, 0),
        "ingestion_timestamp": datetime(2026, 9, 28, 6, 0, 0),
    }
    row.update(values)
    return row


DEMO_ACCOUNTS = [
    _account(
        account_id=1001,
        provider_id="ally",
        provider_name="Ally Bank",
        account_number="****4412",
        account_name="Spending",
        displayed_name="Ally Checking",
        container="bank",
        account_type="CHECKING",
        balance_amount=Decimal("152400.0000"),
        current_balance_amount=Decimal("152400.0000"),
        available_balance_amount=Decimal("152400.0000"),
    ),
    _account(
        account_id=1002,
        provider_id="fidelity",
        provider_name="Fidelity",
        account_number="****8831",
        account_name="Brokerage",
        displayed_name="Fidelity Brokerage",
        container="investment",
        account_type="BROKERAGE",
        balance_amount=Decimal("86000.0000"),
        current_balance_amount=Decimal("86000.0000"),
    ),
    _account(
        account_id=1003,
        provider_id="chase",
        provider_name="Chase",
        account_number="****2290",
        account_name="Sapphire",
        displayed_name="Chase Sapphire",
        container="creditCard",
        account_type="CREDIT",
        is_asset=False,
        balance_amount=Decimal("4200.0000"),
        current_balance_amount=Decimal("4200.0000"),
        apr=Decimal("21.99"),
    ),
    _account(
        account_id=1004,
        provider_id="bnp",
        provider_name="BNP Paribas",
        account_number="****1008",
        account_name="Savings",
        displayed_name="Euro Savings",
        container="bank",
        account_type="SAVINGS",
        balance_amount=Decimal("10000.0000"),
        balance_currency="EUR",
        current_balance_currency="EUR",
        available_balance_currency="EUR",
    ),
]


def _matches(row: dict[str, Any], filters: dict[str, Any]) -> bool:
    for name in ("container", "account_type", "account_status", "provider_name", "provider_id"):
        expected = filters.get(name)
        if expected and row.get(name) != expected:
            return False
    day = filters.get("last_updated_day")
    if day and str(row["last_updated"])[:10] != day:
        return False
    return True


class DemoAccounts:
    def list_accounts(self, filters: dict[str, Any], limit: int, offset: int) -> list[dict[str, Any]]:
        rows = [row for row in DEMO_ACCOUNTS if _matches(row, filters)]
        rows.sort(key=lambda row: row["last_updated"], reverse=True)
        return rows[offset : offset + limit]

    def get_account(self, account_id: int) -> dict[str, Any] | None:
        for row in DEMO_ACCOUNTS:
            if row["account_id"] == account_id:
                return row
        return None

    def summary(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        grouped: dict[tuple, dict[str, Any]] = {}
        for row in DEMO_ACCOUNTS:
            if not _matches(row, filters):
                continue
            key = (
                row["balance_currency"],
                row["is_asset"],
                row["include_in_net_worth"],
                row["container"],
            )
            bucket = grouped.setdefault(
                key,
                {
                    "balance_currency": row["balance_currency"],
                    "is_asset": row["is_asset"],
                    "include_in_net_worth": row["include_in_net_worth"],
                    "container": row["container"],
                    "account_count": 0,
                    "balance_amount": Decimal("0"),
                },
            )
            bucket["account_count"] += 1
            if row["balance_amount"] is not None:
                bucket["balance_amount"] += row["balance_amount"]
        return list(grouped.values())
