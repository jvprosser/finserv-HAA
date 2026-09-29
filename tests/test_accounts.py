from decimal import Decimal

from app.accounts import build_detail_sql, build_list_sql, summarize
from app.config import Settings
from app.db import impala_connect_kwargs
import cml_app
from cml_app import listen_address


def test_cml_serve_uses_a_thread_when_jupyter_loop_is_running(monkeypatch):
    calls = []
    monkeypatch.setattr("cml_app.uvicorn.run", lambda **kwargs: calls.append(kwargs))
    monkeypatch.setattr("cml_app.asyncio.get_running_loop", lambda: object())
    monkeypatch.setattr("cml_app.listen_address", lambda: ("127.0.0.1", 8100))

    cml_app.serve()

    assert calls == [{"app": "app.main:app", "host": "127.0.0.1", "port": 8100}]


def test_cml_listens_on_loopback_and_cdsw_port(monkeypatch):
    monkeypatch.delenv("CDSW_APP_PORT", raising=False)
    assert listen_address() == ("127.0.0.1", 8000)
    monkeypatch.setenv("CDSW_APP_PORT", "8100")
    assert listen_address() == ("127.0.0.1", 8100)


def test_impala_uses_kerberos_unless_ldap_password_is_set():
    kerberos = impala_connect_kwargs(
        Settings(_env_file=None, impala_host="coordinator.example", impala_password="")
    )
    assert kerberos["auth_mechanism"] == "GSSAPI"
    assert kerberos["host"] == "coordinator.example"
    assert "password" not in kerberos

    ldap = impala_connect_kwargs(
        Settings(
            _env_file=None,
            impala_host="coordinator.example",
            impala_user="svc",
            impala_password="secret",
        )
    )
    assert ldap["auth_mechanism"] == "LDAP"
    assert ldap["user"] == "svc"
    assert ldap["password"] == "secret"

    warehouse = impala_connect_kwargs(
        Settings(
            _env_file=None,
            impala_host="coordinator.example",
            impala_port=443,
            impala_use_http_transport=True,
            impala_krb_host="dwx-env.cdp.local",
            impala_kerberos_service="hive",
        )
    )
    assert warehouse["use_http_transport"] is True
    assert warehouse["http_path"] == "cliservice"
    assert warehouse["krb_host"] == "dwx-env.cdp.local"
    assert warehouse["kerberos_service_name"] == "hive"


def test_list_sql_binds_only_provided_filters():
    sql, params = build_list_sql({"container": "bank", "account_type": None}, 50, 10)
    assert "container = %(container)s" in sql
    assert "account_type = %(account_type)s" not in sql
    assert "bank" not in sql
    assert params == {"container": "bank", "limit": 50, "offset": 10}
    assert "LIMIT %(limit)s OFFSET %(offset)s" in sql


def test_detail_sql_binds_account_id():
    sql, param = build_detail_sql()
    assert param == "account_id"
    assert "%(account_id)s" in sql
    assert "yodlee_held_away_accounts" in sql


def test_summary_splits_currencies_and_liabilities():
    rows = [
        {
            "balance_currency": "USD",
            "is_asset": True,
            "include_in_net_worth": True,
            "container": "bank",
            "account_count": 1,
            "balance_amount": Decimal("150000"),
        },
        {
            "balance_currency": "USD",
            "is_asset": False,
            "include_in_net_worth": True,
            "container": "creditCard",
            "account_count": 1,
            "balance_amount": Decimal("4000"),
        },
        {
            "balance_currency": "USD",
            "is_asset": True,
            "include_in_net_worth": False,
            "container": "investment",
            "account_count": 2,
            "balance_amount": Decimal("999"),
        },
        {
            "balance_currency": "EUR",
            "is_asset": True,
            "include_in_net_worth": True,
            "container": "bank",
            "account_count": 1,
            "balance_amount": Decimal("10"),
        },
        {
            "balance_currency": "USD",
            "is_asset": True,
            "include_in_net_worth": True,
            "container": "bank",
            "account_count": 1,
            "balance_amount": None,
        },
    ]
    payload = summarize(rows)
    by_currency = {item["currency"]: item for item in payload["currencies"]}
    usd = by_currency["USD"]
    assert usd["assets"] == "150000.0000"
    assert usd["liabilities"] == "4000.0000"
    assert usd["net_worth"] == "146000.0000"
    assert usd["included_account_count"] == 3
    assert usd["excluded_account_count"] == 2
    eur = by_currency["EUR"]
    assert eur["net_worth"] == "10.0000"
    assert eur["assets"] == "10.0000"
