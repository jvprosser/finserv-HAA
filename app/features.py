from __future__ import annotations

import re
from typing import Any

from app.config import Settings
from app.db import query

FEATURE_NAMES = (
    "days_since_last_contribution",
    "max_balance_drop_30d",
    "holdings_value_change_30d",
    "competitor_transfer_count_90d",
    "retirement_income_started",
    "payroll_source_changed",
    "disconnected_account_count",
    "cd_maturity_inflow_amount",
    "education_debit_count_90d",
    "margin_interest_debit_count_90d",
    "large_real_estate_wire_amount",
    "mortgage_payments_stopped",
    "idle_cash_days_above_100k",
)

MONEY_FEATURES = {
    "max_balance_drop_30d",
    "holdings_value_change_30d",
    "cd_maturity_inflow_amount",
    "large_real_estate_wire_amount",
}

COLUMN_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

CONTRIBUTION = """
(
  base_type = 'CREDIT' AND (
    LOWER(category) LIKE '%%contribution%%'
    OR LOWER(description) LIKE '%%contribution%%'
    OR LOWER(description) LIKE '%%401k%%'
    OR LOWER(description) LIKE '%%403b%%'
    OR LOWER(description) LIKE '%%deferral%%'
  )
)
"""

COMPETITOR = """
(
  base_type = 'DEBIT'
  AND posted_date >= date_sub(to_date(now()), 90)
  AND (
    LOWER(description) LIKE '%%hysa%%'
    OR LOWER(description) LIKE '%%high yield%%'
    OR LOWER(description) LIKE '%%high-yield%%'
    OR (
      LOWER(category) LIKE '%%transfer%%'
      AND LOWER(COALESCE(merchant_name, '')) NOT LIKE '%%tiaa%%'
    )
  )
)
"""

RETIREMENT_INCOME = """
(
  base_type = 'CREDIT' AND (
    LOWER(description) LIKE '%%social security%%'
    OR LOWER(description) LIKE '%%pension%%'
    OR LOWER(description) LIKE '%%annuity%%'
    OR LOWER(COALESCE(merchant_name, '')) LIKE '%%social security%%'
  )
)
"""

PAYROLL = """
(
  base_type = 'CREDIT' AND (
    LOWER(description) LIKE '%%payroll%%'
    OR LOWER(description) LIKE '%%direct dep%%'
    OR LOWER(category) LIKE '%%payroll%%'
  )
)
"""

CD_INFLOW = """
(
  base_type = 'CREDIT' AND (
    LOWER(description) LIKE '%%certificate of deposit%%'
    OR LOWER(description) LIKE '%%cd maturity%%'
    OR LOWER(description) LIKE '%%cd matured%%'
    OR LOWER(category) LIKE '%%cd%%'
  )
)
"""

EDUCATION = """
(
  base_type = 'DEBIT'
  AND posted_date >= date_sub(to_date(now()), 90)
  AND (
    LOWER(description) LIKE '%%529%%'
    OR LOWER(description) LIKE '%%tuition%%'
  )
)
"""

MARGIN_INTEREST = """
(
  base_type = 'DEBIT'
  AND posted_date >= date_sub(to_date(now()), 90)
  AND (
    LOWER(description) LIKE '%%margin interest%%'
    OR LOWER(description) LIKE '%%line of credit%%'
    OR LOWER(description) LIKE '%%loc interest%%'
  )
)
"""

MORTGAGE = """
(
  base_type = 'DEBIT' AND (
    LOWER(description) LIKE '%%mortgage%%'
    OR LOWER(description) LIKE '%%escrow%%'
  )
)
"""

REAL_ESTATE_WIRE = """
(
  (
    LOWER(description) LIKE '%%mortgage%%'
    OR LOWER(description) LIKE '%%escrow%%'
    OR LOWER(description) LIKE '%%title company%%'
  )
)
"""

DAILY = "retirement_distributions.yodlee_held_away_account_daily"
TRANSACTIONS = "retirement_distributions.yodlee_transactions"
HOLDINGS = "retirement_distributions.yodlee_holdings"


def require_column(name: str) -> str:
    if not COLUMN_NAME.match(name or ""):
        raise ValueError("CLIENT_ID_COLUMN must be a single SQL identifier")
    return name


def feature_sql(client_column: str) -> str:
    column = require_column(client_column)
    # Client ids such as P-7011 are strings. CAST keeps Impala from rejecting
    # the comparison when the configured column is numeric (account_id is BIGINT).
    client_predicate = f"CAST({column} AS STRING) = %(client_id)s"
    return f"""
SELECT
  txn.txn_rows AS txn_rows,
  txn.days_since_last_contribution AS days_since_last_contribution,
  txn.competitor_transfer_count_90d AS competitor_transfer_count_90d,
  txn.retirement_income_started AS retirement_income_started,
  txn.payroll_sources AS payroll_sources,
  txn.cd_maturity_inflow_amount AS cd_maturity_inflow_amount,
  txn.education_debit_count_90d AS education_debit_count_90d,
  txn.margin_interest_debit_count_90d AS margin_interest_debit_count_90d,
  txn.large_real_estate_wire_amount AS large_real_estate_wire_amount,
  txn.days_since_last_mortgage AS days_since_last_mortgage,
  txn.mortgage_payment_count AS mortgage_payment_count,
  daily.daily_rows AS daily_rows,
  daily.max_balance_drop_30d AS max_balance_drop_30d,
  daily.idle_cash_days_above_100k AS idle_cash_days_above_100k,
  daily.disconnected_account_count AS disconnected_account_count,
  holdings.holding_rows AS holding_rows,
  holdings.holdings_value_change_30d AS holdings_value_change_30d
FROM (
  SELECT
    COUNT(*) AS txn_rows,
    DATEDIFF(now(), MAX(CASE WHEN {CONTRIBUTION} THEN posted_date END))
      AS days_since_last_contribution,
    SUM(CASE WHEN {COMPETITOR} THEN 1 ELSE 0 END) AS competitor_transfer_count_90d,
    CASE
      WHEN SUM(CASE WHEN {RETIREMENT_INCOME} THEN 1 ELSE 0 END) > 0
       AND MIN(CASE WHEN {RETIREMENT_INCOME} THEN posted_date END)
           >= date_sub(to_date(now()), 90)
      THEN 1 ELSE 0
    END AS retirement_income_started,
    COUNT(DISTINCT CASE WHEN {PAYROLL} THEN COALESCE(merchant_name, description) END)
      AS payroll_sources,
    SUM(CASE WHEN {CD_INFLOW} THEN amount END) AS cd_maturity_inflow_amount,
    SUM(CASE WHEN {EDUCATION} THEN 1 ELSE 0 END) AS education_debit_count_90d,
    SUM(CASE WHEN {MARGIN_INTEREST} THEN 1 ELSE 0 END) AS margin_interest_debit_count_90d,
    MAX(CASE WHEN {REAL_ESTATE_WIRE} AND amount >= 10000 THEN amount END)
      AS large_real_estate_wire_amount,
    DATEDIFF(now(), MAX(CASE WHEN {MORTGAGE} THEN posted_date END))
      AS days_since_last_mortgage,
    SUM(CASE WHEN {MORTGAGE} THEN 1 ELSE 0 END) AS mortgage_payment_count
  FROM {TRANSACTIONS}
  WHERE {client_predicate}
) txn
CROSS JOIN (
  SELECT
    COUNT(*) AS daily_rows,
    (
      SELECT MAX(start_balance - end_balance)
      FROM (
        SELECT
          account_id,
          FIRST_VALUE(balance_amount) OVER (
            PARTITION BY account_id ORDER BY as_of_date
          ) AS start_balance,
          FIRST_VALUE(balance_amount) OVER (
            PARTITION BY account_id ORDER BY as_of_date DESC
          ) AS end_balance,
          account_type
        FROM {DAILY}
        WHERE {client_predicate}
          AND as_of_date >= date_sub(to_date(now()), 30)
          AND account_type IN ('CHECKING', 'IRA', 'BROKERAGE')
      ) drops
    ) AS max_balance_drop_30d,
    COUNT(DISTINCT CASE
      WHEN container = 'bank'
       AND account_type IN ('CHECKING', 'SAVINGS')
       AND balance_amount > 100000
       AND as_of_date >= date_sub(to_date(now()), 120)
      THEN as_of_date
    END) AS idle_cash_days_above_100k,
    SUM(CASE
      WHEN as_of_date = latest_day AND UPPER(COALESCE(account_status, '')) != 'ACTIVE' THEN 1
      ELSE 0
    END) AS disconnected_account_count
  FROM (
    SELECT
      as_of_date,
      balance_amount,
      container,
      account_type,
      account_status,
      MAX(as_of_date) OVER () AS latest_day
    FROM {DAILY}
    WHERE {client_predicate}
  ) history
) daily
CROSS JOIN (
  SELECT
    COUNT(*) AS holding_rows,
    SUM(CASE WHEN as_of_date = latest_day THEN value_amount ELSE 0 END)
      - SUM(CASE WHEN as_of_date = prior_day THEN value_amount ELSE 0 END)
      AS holdings_value_change_30d
  FROM (
    SELECT
      as_of_date,
      value_amount,
      MAX(as_of_date) OVER () AS latest_day,
      MIN(as_of_date) OVER () AS prior_day
    FROM {HOLDINGS}
    WHERE {client_predicate}
      AND as_of_date >= date_sub(to_date(now()), 30)
  ) span
) holdings
""".strip()


def _int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def features_from_row(row: dict[str, Any]) -> dict[str, Any]:
    txn_rows = int(row.get("txn_rows") or 0)
    daily_rows = int(row.get("daily_rows") or 0)
    holding_rows = int(row.get("holding_rows") or 0)
    features: dict[str, Any] = {name: None for name in FEATURE_NAMES}

    if txn_rows:
        features["days_since_last_contribution"] = _int(row.get("days_since_last_contribution"))
        features["competitor_transfer_count_90d"] = _int(row.get("competitor_transfer_count_90d")) or 0
        features["retirement_income_started"] = _int(row.get("retirement_income_started")) or 0
        sources = _int(row.get("payroll_sources")) or 0
        features["payroll_source_changed"] = 1 if sources > 1 else 0
        features["cd_maturity_inflow_amount"] = _float(row.get("cd_maturity_inflow_amount")) or 0.0
        features["education_debit_count_90d"] = _int(row.get("education_debit_count_90d")) or 0
        features["margin_interest_debit_count_90d"] = _int(row.get("margin_interest_debit_count_90d")) or 0
        features["large_real_estate_wire_amount"] = _float(row.get("large_real_estate_wire_amount")) or 0.0
        days_since_mortgage = _int(row.get("days_since_last_mortgage"))
        mortgage_count = _int(row.get("mortgage_payment_count")) or 0
        stopped = bool(
            days_since_mortgage is not None and days_since_mortgage > 45 and mortgage_count >= 3
        )
        features["mortgage_payments_stopped"] = 1 if stopped else 0

    if daily_rows:
        drop = row.get("max_balance_drop_30d")
        features["max_balance_drop_30d"] = 0.0 if drop is None else float(drop)
        features["idle_cash_days_above_100k"] = _int(row.get("idle_cash_days_above_100k")) or 0
        features["disconnected_account_count"] = _int(row.get("disconnected_account_count")) or 0

    if holding_rows:
        change = row.get("holdings_value_change_30d")
        features["holdings_value_change_30d"] = 0.0 if change is None else float(change)

    return features


def load_features(settings: Settings, client_id: str) -> dict[str, Any]:
    if not settings.client_id_column:
        raise RuntimeError("CLIENT_ID_COLUMN is not set")
    sql = feature_sql(settings.client_id_column)
    rows = query(settings, sql, {"client_id": client_id})
    if not rows:
        return {name: None for name in FEATURE_NAMES}
    return features_from_row(rows[0])
