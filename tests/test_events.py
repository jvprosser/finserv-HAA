from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from app.config import Settings
from app.features import feature_sql, pick_supporting, supporting_daily_sql, supporting_txn_sql, txn_filter_column
from app.main import create_app
from app.sfdc import MemorySalesforce, oauth_form, oauth_login_error, oauth_token_url

ROOT = Path(__file__).resolve().parents[1]
CATALOG = (ROOT / "rules" / "actionable_events.yaml").read_text()


def _client(tmp_path, features, sfdc=None, account_field="", supporting=None, llm=None):
    rules_path = tmp_path / "actionable_events.yaml"
    rules_path.write_text(CATALOG)
    settings = Settings(
        _env_file=None,
        api_key="test-key",
        demo_mode=False,
        rules_path=rules_path,
        client_id_column="",
        sfdc_account_external_id_field=account_field,
        sfdc_opportunity_stage="Prospecting",
    )
    app = create_app(settings)
    app.state.feature_loader = lambda client_id: features
    app.state.sfdc_client = sfdc if sfdc is not None else MemorySalesforce()
    app.state.supporting_loader = lambda client_id: supporting or {"accounts": [], "transactions": []}
    if llm is not None:
        app.state.llm_complete = llm
    return TestClient(app), rules_path


def _auth():
    return {"Authorization": "Bearer test-key"}


def _event(body, name):
    return next(item for item in body["events"] if item["event_name"] == name)


def test_feature_sql_uses_a_bound_client_predicate():
    from impala.interface import _bind_parameters_dict

    sql = feature_sql("client_id")
    rendered = _bind_parameters_dict(sql, {"client_id": "P-7015"})
    assert "CAST(client_id AS STRING) = 'P-7015'" in rendered
    assert "CAST(account_id AS STRING) = 'P-7015'" in rendered

    forced = _bind_parameters_dict(
        feature_sql(txn_filter_column("account_id"), "account_id"),
        {"client_id": "P-7015"},
    )
    assert "FROM retirement_distributions.yodlee_transactions" in forced
    assert forced.count("CAST(client_id AS STRING) = 'P-7015'") >= 1
    assert "LIKE '%contribution%'" in rendered
    assert "CHECKING" in rendered


def test_contribution_threshold_and_missing_history(tmp_path):
    over, _ = _client(tmp_path, {"days_since_last_contribution": 120})
    matched = _event(over.get("/v1/clients/C1/events", headers=_auth()).json(), "CONTRIBUTIONS_STOPPED_OVER_90_DAYS")
    assert matched["status"] == "matched"
    assert matched["sfdc_action"]["enabled"] is True
    assert matched["evidence"]["days_since_last_contribution"] == 120

    under, _ = _client(tmp_path, {"days_since_last_contribution": 30})
    quiet = _event(under.get("/v1/clients/C1/events", headers=_auth()).json(), "CONTRIBUTIONS_STOPPED_OVER_90_DAYS")
    assert quiet["status"] == "not_matched"
    assert quiet["sfdc_action"]["enabled"] is False

    empty, _ = _client(tmp_path, {"days_since_last_contribution": None})
    missing = _event(empty.get("/v1/clients/C1/events", headers=_auth()).json(), "CONTRIBUTIONS_STOPPED_OVER_90_DAYS")
    assert missing["status"] == "insufficient_data"
    assert missing["sfdc_action"]["enabled"] is False
    assert "evidence" not in missing
    assert missing["missing"] == ["days_since_last_contribution"]


def test_idle_cash_threshold(tmp_path):
    client, _ = _client(tmp_path, {"idle_cash_days_above_100k": 95})
    matched = _event(client.get("/v1/clients/C1/events", headers=_auth()).json(), "IDLE_CASH_DRAG_IDENTIFIED")
    assert matched["matched"] is True

    client, _ = _client(tmp_path, {"idle_cash_days_above_100k": 10})
    quiet = _event(client.get("/v1/clients/C1/events", headers=_auth()).json(), "IDLE_CASH_DRAG_IDENTIFIED")
    assert quiet["matched"] is False


def test_opportunity_is_created_then_updated_and_readable(tmp_path):
    features = {"max_balance_drop_30d": 48000.0, "holdings_value_change_30d": -1000.0}
    salesforce = MemorySalesforce()
    client, _ = _client(tmp_path, features, sfdc=salesforce)
    created = client.post("/v1/clients/C123/events/HELDAWAY_LIQUIDATION_DETECTED/sfdc", headers=_auth())
    assert created.status_code == 200
    assert created.json()["result"] == "created"
    assert created.json()["sobject"] == "Opportunity"

    viewed = client.get("/v1/clients/C123/events/HELDAWAY_LIQUIDATION_DETECTED/sfdc", headers=_auth())
    assert viewed.status_code == 200
    body = viewed.json()
    assert body["stage_name"] == "Prospecting"
    assert "managed portfolio" in body["description"]
    assert body["url"].endswith("/view")

    updated = client.post("/v1/clients/C123/events/HELDAWAY_LIQUIDATION_DETECTED/sfdc", headers=_auth())
    assert updated.json()["result"] == "updated"
    assert updated.json()["id"] == created.json()["id"]


def test_matched_event_adds_account_and_transaction_tables(tmp_path):
    supporting = {
        "accounts": [
            {
                "account_name": "TESTDATA",
                "displayed_name": "accountHolder",
                "account_type": "CHECKING",
                "balance": 150000,
                "amount": 0,
                "max_balance_drop_30d": 1,
                "idle_cash_days_above_100k": 1,
                "disconnected_account_count": 0,
            }
        ],
        "transactions": [
            {
                "posted_date": "2026-05-12",
                "amount": 500,
                "base_type": "CREDIT",
                "category": "contribution",
                "description": "401k contribution",
                "days_since_last_contribution": 1,
                "competitor_transfer_count_90d": 0,
            },
            {
                "posted_date": "2026-08-20",
                "amount": 1500,
                "base_type": "DEBIT",
                "category": "transfer",
                "description": "Transfer to high yield HYSA",
                "days_since_last_contribution": 0,
                "competitor_transfer_count_90d": 1,
            },
        ],
    }
    client, _ = _client(tmp_path, {"days_since_last_contribution": 120}, supporting=supporting)
    body = client.get("/v1/clients/C1/events", headers=_auth()).json()
    assert body["account_name"] == "TESTDATA"
    matched = _event(
        body,
        "CONTRIBUTIONS_STOPPED_OVER_90_DAYS",
    )
    assert matched["accounts"][0]["account_name"] == "TESTDATA"
    assert matched["accounts"][0]["displayed_name"] == "accountHolder"
    assert [row["category"] for row in matched["transactions"]] == ["contribution"]

    created = client.post("/v1/clients/C1/events/CONTRIBUTIONS_STOPPED_OVER_90_DAYS/sfdc", headers=_auth())
    assert created.status_code == 200
    description = client.get("/v1/clients/C1/events/CONTRIBUTIONS_STOPPED_OVER_90_DAYS/sfdc", headers=_auth()).json()[
        "description"
    ]
    assert "CEL fields" in description
    assert "days_since_last_contribution" in description
    assert "TESTDATA" in description
    assert "401k contribution" in description
    assert "high yield" not in description


def test_advisor_brief_and_salesforce_description_use_the_draft(tmp_path):
    supporting = {
        "accounts": [
            {
                "account_name": "TESTDATA",
                "displayed_name": "accountHolder",
                "account_type": "CHECKING",
                "balance": 150000,
                "amount": 0,
            }
        ],
        "transactions": [
            {
                "posted_date": "2026-05-12",
                "amount": 500,
                "base_type": "CREDIT",
                "category": "contribution",
                "description": "401k contribution",
                "days_since_last_contribution": 1,
            }
        ],
    }
    captured = []

    def llm(messages):
        captured.append(messages)
        return "TESTDATA has had no contribution for 120 days."

    client, _ = _client(
        tmp_path,
        {"days_since_last_contribution": 120},
        supporting=supporting,
        llm=llm,
    )
    events = client.get("/v1/clients/C1/events", headers=_auth()).json()
    assert events["llm_enabled"] is True
    unmatched = client.post("/v1/clients/C1/events/IDLE_CASH_DRAG_IDENTIFIED/brief", headers=_auth())
    assert unmatched.status_code == 409

    drafted = client.post("/v1/clients/C1/events/CONTRIBUTIONS_STOPPED_OVER_90_DAYS/brief", headers=_auth())
    assert drafted.status_code == 200
    assert "TESTDATA" in drafted.json()["brief"]
    assert "TESTDATA" in captured[0][1]["content"]

    created = client.post(
        "/v1/clients/C1/events/CONTRIBUTIONS_STOPPED_OVER_90_DAYS/sfdc",
        headers=_auth(),
        json={"brief": drafted.json()["brief"]},
    )
    assert created.status_code == 200
    description = client.get("/v1/clients/C1/events/CONTRIBUTIONS_STOPPED_OVER_90_DAYS/sfdc", headers=_auth()).json()[
        "description"
    ]
    assert "Advisor note" in description
    assert "no contribution for 120 days" in description
    assert description.index("Advisor note") < description.index("CEL fields")


def test_advisor_brief_requires_model_config(tmp_path):
    client, _ = _client(tmp_path, {"days_since_last_contribution": 120})
    response = client.post("/v1/clients/C1/events/CONTRIBUTIONS_STOPPED_OVER_90_DAYS/brief", headers=_auth())
    assert response.status_code == 503


def test_rules_draft_validates_cel_and_does_not_write(tmp_path):
    client, rules_path = _client(
        tmp_path,
        {},
        llm=lambda messages: '{"cel": "idle_cash_days_above_100k >= 90", "features": ["idle_cash_days_above_100k"]}',
    )
    original = rules_path.read_text()
    drafted = client.post(
        "/v1/rules/draft",
        headers=_auth(),
        json={"event_name": "IDLE_CASH_DRAG_IDENTIFIED", "prompt": "idle cash over 100000 for 90 days"},
    )
    assert drafted.status_code == 200
    assert drafted.json()["cel"] == "idle_cash_days_above_100k >= 90"
    assert rules_path.read_text() == original

    client.app.state.llm_complete = (
        lambda messages: '{"cel": "not_a_feature > 1", "features": ["days_since_last_contribution"]}'
    )
    rejected = client.post(
        "/v1/rules/draft",
        headers=_auth(),
        json={"event_name": "IDLE_CASH_DRAG_IDENTIFIED", "prompt": "break it"},
    )
    assert rejected.status_code == 422
    assert rules_path.read_text() == original


def test_pick_supporting_keeps_daily_rows_for_balance_rules():
    accounts, transactions = pick_supporting(
        ["max_balance_drop_30d", "holdings_value_change_30d"],
        {
            "accounts": [
                {"account_name": "Checking", "account_type": "CHECKING", "max_balance_drop_30d": 1, "balance": 10},
                {"account_name": "Credit", "account_type": "CREDIT", "max_balance_drop_30d": 0, "balance": 4},
            ],
            "transactions": [{"description": "401k contribution", "days_since_last_contribution": 1}],
        },
    )
    assert [row["account_name"] for row in accounts] == ["Checking"]
    assert transactions == []


def test_supporting_sql_binds_the_client_and_reuses_cel_predicates():
    from impala.interface import _bind_parameters_dict

    daily = _bind_parameters_dict(supporting_daily_sql("account_id"), {"client_id": "P-7015"})
    assert "CAST(account_id AS STRING) = 'P-7015'" in daily
    assert "account_name" in daily
    assert "displayed_name" in daily
    assert "last_payment_amount AS amount" in daily

    txn = _bind_parameters_dict(supporting_txn_sql("client_id"), {"client_id": "P-7015"})
    assert "CAST(client_id AS STRING) = 'P-7015'" in txn
    assert "LIKE '%contribution%'" in txn
    assert "posted_date" in txn


def test_unmatched_event_does_not_call_salesforce(tmp_path):
    client, _ = _client(tmp_path, {"days_since_last_contribution": 10})
    response = client.post("/v1/clients/C1/events/CONTRIBUTIONS_STOPPED_OVER_90_DAYS/sfdc", headers=_auth())
    assert response.status_code == 409


def test_rules_put_changes_action_and_rejects_bad_cel(tmp_path):
    client, rules_path = _client(tmp_path, {})
    original = rules_path.read_text()
    loaded = yaml.safe_load(original)
    broken = yaml.safe_dump(loaded, sort_keys=False)
    broken = broken.replace(
        "days_since_last_contribution > 90",
        "not_a_feature > 1",
        1,
    )
    rejected = client.put("/v1/rules", headers=_auth(), json={"yaml": broken})
    assert rejected.status_code == 422
    assert rules_path.read_text() == original

    changed = original.replace(
        "event_name: IDLE_CASH_DRAG_IDENTIFIED\n  action: create_task",
        "event_name: IDLE_CASH_DRAG_IDENTIFIED\n  action: create_opportunity",
        1,
    )
    saved = client.put("/v1/rules", headers=_auth(), json={"yaml": changed})
    assert saved.status_code == 200
    events = client.get("/v1/clients/C1/events", headers=_auth()).json()
    assert _event(events, "IDLE_CASH_DRAG_IDENTIFIED")["action"] == "create_opportunity"


def test_salesforce_token_url_and_form_are_plain_client_credentials():
    from urllib.parse import parse_qs, urlencode

    assert oauth_token_url("https://example.my.salesforce.com/") == (
        "https://example.my.salesforce.com/services/oauth2/token"
    )
    assert oauth_token_url("https://example.my.salesforce.com/services/oauth2/token") == (
        "https://example.my.salesforce.com/services/oauth2/token"
    )
    form = oauth_form('  "abc"  ', " secret\n")
    assert form["grant_type"] == "client_credentials"
    assert form["client_id"] == "abc"
    assert form["client_secret"] == "secret"
    assert parse_qs(urlencode(form))["grant_type"] == ["client_credentials"]
    assert "Run As" in oauth_login_error(
        '{"error":"invalid_grant","error_description":"no client credentials user enabled"}'
    )
    assert "SFDC_CLIENT_SECRET" in oauth_login_error(
        '{"error":"invalid_client","error_description":"invalid client credentials"}'
    )

