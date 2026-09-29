from __future__ import annotations

from typing import Any

from app.config import Settings


class DataUnavailable(Exception):
    pass


def query(settings: Settings, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if not settings.impala_host:
        raise DataUnavailable("IMPALA_HOST is not set")
    try:
        from impala.dbapi import connect
    except ImportError as exc:
        raise DataUnavailable("impyla is not installed") from exc

    kwargs: dict[str, Any] = {
        "host": settings.impala_host,
        "port": settings.impala_port,
        "auth_mechanism": "LDAP",
        "user": settings.impala_user,
        "password": settings.impala_password,
        "database": settings.impala_database,
        "use_ssl": settings.impala_use_ssl,
    }
    if settings.impala_ca_cert:
        kwargs["ca_cert"] = settings.impala_ca_cert

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
