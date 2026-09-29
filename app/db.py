from __future__ import annotations

from typing import Any

from app.config import Settings


class DataUnavailable(Exception):
    pass


def impala_connect_kwargs(settings: Settings) -> dict[str, Any]:
    if not settings.impala_host:
        raise DataUnavailable("IMPALA_HOST is not set")
    auth = (settings.impala_auth or "").upper()
    if not auth:
        auth = "LDAP" if settings.impala_password else "GSSAPI"
    kwargs: dict[str, Any] = {
        "host": settings.impala_host,
        "port": settings.impala_port,
        "database": settings.impala_database or None,
        "auth_mechanism": auth,
        "use_ssl": settings.impala_use_ssl,
        "kerberos_service_name": settings.impala_kerberos_service or "impala",
    }
    if auth == "LDAP":
        kwargs["user"] = settings.impala_user
        kwargs["password"] = settings.impala_password
    if settings.impala_use_http_transport:
        kwargs["use_http_transport"] = True
        kwargs["http_path"] = settings.impala_http_path or "cliservice"
    if settings.impala_krb_host:
        kwargs["krb_host"] = settings.impala_krb_host
    if settings.impala_ca_cert:
        kwargs["ca_cert"] = settings.impala_ca_cert
    return kwargs


def query(settings: Settings, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    kwargs = impala_connect_kwargs(settings)
    try:
        from impala.dbapi import connect
    except ImportError as exc:
        raise DataUnavailable("impyla is not installed") from exc

    try:
        conn = connect(**kwargs)
    except Exception as exc:
        raise DataUnavailable(str(exc)) from exc

    try:
        cursor = conn.cursor()
        cursor.execute(sql, params or None)
        if not cursor.description:
            return []
        columns = [desc[0].lower() for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    except Exception as exc:
        raise DataUnavailable(str(exc)) from exc
    finally:
        conn.close()
