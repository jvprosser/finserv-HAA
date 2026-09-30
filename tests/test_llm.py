from app.config import Settings
from app.llm import (
    BRIEF_SYSTEM,
    advisor_brief,
    chat_completions_url,
    chat_request_body,
    parse_json_object,
    resolve_api_key,
    rule_draft,
    strip_reasoning,
)


def test_chat_completions_url_appends_the_openai_path():
    assert chat_completions_url("https://example/v1/") == "https://example/v1/chat/completions"
    assert chat_completions_url("https://example/v1/chat/completions") == "https://example/v1/chat/completions"


def test_chat_request_turns_nemotron_thinking_off():
    settings = Settings(_env_file=None, llm_model_id="nvidia/nemotron-3-super-120b-a12b")
    body = chat_request_body(settings, [{"role": "user", "content": "hi"}])
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["max_tokens"] == 2048
    assert "Reply with the advisor note only" in BRIEF_SYSTEM


def test_strip_reasoning_drops_scratchpad_before_the_note():
    raw = (
        "We need to produce a short internal note.\n"
        "Let's craft 5 sentences.\n"
        "</think>\n"
        "The event RETIREMENT_INCOME_COMMENCED fired because retirement_income_started is 1."
    )
    assert strip_reasoning(raw) == (
        "The event RETIREMENT_INCOME_COMMENCED fired because retirement_income_started is 1."
    )


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
    assert "Reply with the advisor note only" in captured[0][0]["content"]

    cleaned = advisor_brief(
        {"event_name": "RETIREMENT_INCOME_COMMENCED", "evidence": {"retirement_income_started": 1}},
        lambda messages: "We need to produce a note.\n</think>\nretirement_income_started is 1.",
    )
    assert cleaned == "retirement_income_started is 1."


def test_rule_draft_parses_model_json():
    proposed = rule_draft(
        "IDLE_CASH_DRAG_IDENTIFIED",
        "idle cash over 100000 for 90 days",
        "idle_cash_days_above_100k >= 90",
        lambda messages: '{"cel": "idle_cash_days_above_100k >= 90", "features": ["idle_cash_days_above_100k"]}',
    )
    assert proposed["features"] == ["idle_cash_days_above_100k"]
