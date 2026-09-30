from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    impala_host: str = ""
    impala_port: int = 21050
    impala_database: str = "retirement_distributions"
    impala_user: str = ""
    impala_password: str = ""
    impala_use_ssl: bool = True
    impala_ca_cert: str = ""
    # Empty selects LDAP when a password is set, and GSSAPI otherwise.
    # Cloudera AI applications use the workload Kerberos ticket (GSSAPI).
    impala_auth: str = ""
    impala_kerberos_service: str = "impala"
    impala_krb_host: str = ""
    impala_use_http_transport: bool = False
    impala_http_path: str = "cliservice"

    client_id_column: str = "client_id"
    daily_id_column: str = "account_id"
    api_key: str = ""
    demo_mode: bool = False

    sfdc_login_url: str = "https://login.salesforce.com"
    sfdc_client_id: str = ""
    sfdc_client_secret: str = ""
    sfdc_opportunity_stage: str = "Prospecting"
    sfdc_account_external_id_field: str = ""
    sfdc_api_version: str = "59.0"

    llm_base_url: str = ""
    llm_model_id: str = "nvidia/nemotron-3-super-120b-a12b"
    llm_api_key: str = ""
    llm_timeout: float = 60.0
    llm_max_tokens: int = 512

    rules_path: Path = ROOT / "rules" / "actionable_events.yaml"
