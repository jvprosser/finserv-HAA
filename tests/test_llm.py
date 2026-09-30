from app.config import Settings
from app.llm import (
    advisor_brief,
    chat_completions_url,
    parse_json_object,
    resolve_api_key,
    rule_draft,
)


def test_chat_completions_url_appends_the_openai_path():
    assert chat_completions_url("https://example/v1/") == "https://example/v1/chat/completions"
    assert chat_completions_url("https://example/v1/chat/completions") == "https://example/v1/chat/completions"


def test_parse_json_object_strips_fences():
    payload = parse_json_object('```json\n{"cel": "idle_cash_days_above_100k >= 90", "features": ["idle_cash_days_above_100k"]}\n```')
    assert payload["cel"] == "idle_cash_days_above_100k >= 90"


def test_resolve_api_key_prefers_settings(tmp_path, monkeypatch):
    monkeypatch.delenv("CDP_TOKEN", raising=False)
    settings = Settings(_env_file=None, llm_api_key="  token  ")
    assert resolve_api_key(settings) == "token"


def test_advisor_brief_sends_evidence_to_the_model():
    captured = []

    def complete_fn(messages):
        captured.append(messages)
        return "TESTDATA had no contribution for 120 days."

    brief = advisor_brief(
        {
            "event_name": "CONTRIBUTIONS_STOPPED_OVER_90_DAYS",
            "evidence": {"days_since_last_contribution": 120},
            "accounts": [{"account_name": "TESTDATA"}],
            "transactions": [{"description": "401k contribution"}],
        },
        complete_fn,
    )
    assert brief.startswith("TESTDATA")
    user = captured[0][1]["content"]
    assert "TESTDATA" in user
    assert "401k contribution" in user


def test_rule_draft_parses_model_json():
    proposed = rule_draft(
        "IDLE_CASH_DRAG_IDENTIFIED",
        "idle cash over 100000 for 90 days",
        "idle_cash_days_above_100k >= 90",
        lambda messages: '{"cel": "idle_cash_days_above_100k >= 90", "features": ["idle_cash_days_above_100k"]}',
    )
    assert proposed["features"] == ["idle_cash_days_above_100k"]
