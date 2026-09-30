from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from app.config import Settings
from app.features import feature_sql
from app.main import create_app
from app.sfdc import MemorySalesforce

ROOT = Path(__file__).resolve().parents[1]
CATALOG = (ROOT / "rules" / "actionable_events.yaml").read_text()


def _client(tmp_path, features, sfdc=None, account_field=""):
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
    return TestClient(app), rules_path


def _auth():
    return {"Authorization": "Bearer test-key"}


def _event(body, name):
    return next(item for item in body["events"] if item["event_name"] == name)


def test_feature_sql_uses_a_bound_client_predicate():
    from impala.interface import _bind_parameters_dict

    sql = feature_sql("client_id")
    rendered = _bind_parameters_dict(sql, {"client_id": "C123"})
    assert "CAST(client_id AS STRING) = 'C123'" in rendered
    assert "LIKE '%contribution%'" in rendered
    assert "CHECKING" in rendered

    numeric_column = _bind_parameters_dict(feature_sql("account_id"), {"client_id": "P-7011"})
    assert "CAST(account_id AS STRING) = 'P-7011'" in numeric_column
    assert "account_id = 'P-7011'" not in numeric_column


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
