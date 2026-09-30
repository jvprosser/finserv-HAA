from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote, urlencode

import httpx

from app.config import Settings

LABELS = {
    "create_task": "Create task",
    "create_opportunity": "Create opportunity",
    "update_account": "Update account",
}
SOBJECTS = {
    "create_task": "Task",
    "create_opportunity": "Opportunity",
    "update_account": "Account",
}


def stable_key(event_name: str, client_id: str) -> str:
    return f"HAA|{event_name}|{client_id}"


def description_body(rule_fields: dict[str, str], evidence: dict[str, Any]) -> str:
    lines = [
        rule_fields["description"],
        "",
        rule_fields["business_opportunity"],
        "",
        f"Next steps: {rule_fields['suggested_next_steps']}",
    ]
    if evidence:
        rendered = ", ".join(f"{name}={value}" for name, value in evidence.items())
        lines.extend(["", f"Evidence: {rendered}"])
    return "\n".join(lines)


def soql_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _trimmed(value: str) -> str:
    return (value or "").strip().strip('"').strip("'")


def oauth_token_url(login_url: str) -> str:
    base = _trimmed(login_url).rstrip("/")
    suffix = "/services/oauth2/token"
    if base.endswith(suffix):
        return base
    return f"{base}{suffix}"


def oauth_form(client_id: str, client_secret: str) -> dict[str, str]:
    return {
        "grant_type": "client_credentials",
        "client_id": _trimmed(client_id),
        "client_secret": _trimmed(client_secret),
    }


class SalesforceError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        self.status_code = status_code
        super().__init__(message)


class MemorySalesforce:
    """In-process stand-in used by tests and DEMO_MODE."""

    def __init__(self) -> None:
        self.records: dict[tuple[str, str], dict[str, Any]] = {}
        self.instance_url = "https://example.my.salesforce.com"
        self._sequence = 1

    def upsert(self, sobject: str, key: str, fields: dict[str, Any], client_id: str = "") -> tuple[str, str]:
        del client_id
        existing = self.records.get((sobject, key))
        if existing:
            existing.update(fields)
            return "updated", existing["id"]
        if sobject == "Account":
            raise SalesforceError("No Salesforce Account matches this client", 422)
        record_id = f"{sobject[:3]}{self._sequence:06d}"
        self._sequence += 1
        self.records[(sobject, key)] = {"id": record_id, "sobject": sobject, **fields}
        return "created", record_id

    def fetch(self, sobject: str, key: str, client_id: str = "") -> dict[str, Any] | None:
        del client_id
        record = self.records.get((sobject, key))
        if record is None:
            return None
        return self._view(sobject, record)

    def _view(self, sobject: str, record: dict[str, Any]) -> dict[str, Any]:
        record_id = record["id"]
        url = f"{self.instance_url}/lightning/r/{sobject}/{record_id}/view"
        if sobject == "Opportunity":
            return {
                "sobject": sobject,
                "id": record_id,
                "name": record.get("Name"),
                "stage_name": record.get("StageName"),
                "close_date": record.get("CloseDate"),
                "description": record.get("Description"),
                "url": url,
            }
        if sobject == "Task":
            return {
                "sobject": sobject,
                "id": record_id,
                "subject": record.get("Subject"),
                "status": record.get("Status"),
                "description": record.get("Description"),
                "url": url,
            }
        return {
            "sobject": sobject,
            "id": record_id,
            "description": record.get("Description"),
            "url": url,
        }


class SalesforceRest:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.instance_url = ""
        self._token = ""
        self._expires_at = 0.0

    def _login(self) -> str:
        if self._token and time.time() < self._expires_at:
            return self._token
        response = httpx.post(
            oauth_token_url(self.settings.sfdc_login_url),
            content=urlencode(oauth_form(self.settings.sfdc_client_id, self.settings.sfdc_client_secret)),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
            follow_redirects=False,
        )
        if response.status_code >= 400:
            raise SalesforceError(f"Salesforce login failed: {response.text}", 502)
        body = response.json()
        self._token = body["access_token"]
        self.instance_url = body["instance_url"].rstrip("/")
        self._expires_at = time.time() + int(body.get("expires_in", 3600)) - 60
        return self._token

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        token = self._login()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        response = httpx.request(method, f"{self.instance_url}{path}", headers=headers, timeout=30, **kwargs)
        if response.status_code >= 400:
            raise SalesforceError(f"Salesforce {method} {path} failed: {response.text}", 502)
        return response

    def _query(self, soql: str) -> list[dict[str, Any]]:
        response = self._request("GET", "/services/data/v{}/query".format(self.settings.sfdc_api_version), params={"q": soql})
        return response.json().get("records", [])

    def _find_id(self, sobject: str, key: str, client_id: str) -> str | None:
        if sobject == "Task":
            soql = f"SELECT Id FROM Task WHERE Subject = '{soql_escape(key)}' LIMIT 1"
        elif sobject == "Opportunity":
            soql = f"SELECT Id FROM Opportunity WHERE Name = '{soql_escape(key[:120])}' LIMIT 1"
        else:
            field = self.settings.sfdc_account_external_id_field
            soql = f"SELECT Id FROM Account WHERE {field} = '{soql_escape(client_id)}' LIMIT 1"
        records = self._query(soql)
        if not records:
            return None
        return records[0]["Id"]

    def upsert(self, sobject: str, key: str, fields: dict[str, Any], client_id: str) -> tuple[str, str]:
        existing = self._find_id(sobject, key, client_id)
        version = self.settings.sfdc_api_version
        if existing:
            self._request(
                "PATCH",
                f"/services/data/v{version}/sobjects/{sobject}/{existing}",
                json={"Description": fields.get("Description")},
            )
            return "updated", existing
        if sobject == "Account":
            raise SalesforceError("No Salesforce Account matches this client", 422)
        payload = dict(fields)
        if sobject == "Opportunity":
            payload["Name"] = key[:120]
        response = self._request(
            "POST",
            f"/services/data/v{version}/sobjects/{sobject}",
            json=payload,
        )
        return "created", response.json()["id"]

    def fetch(self, sobject: str, key: str, client_id: str) -> dict[str, Any] | None:
        record_id = self._find_id(sobject, key, client_id)
        if not record_id:
            return None
        version = self.settings.sfdc_api_version
        if sobject == "Opportunity":
            fields = "Id,Name,StageName,CloseDate,Description"
        elif sobject == "Task":
            fields = "Id,Subject,Status,Description"
        else:
            fields = "Id,Description"
        response = self._request("GET", f"/services/data/v{version}/sobjects/{sobject}/{record_id}", params={"fields": fields})
        record = response.json()
        url = f"{self.instance_url}/lightning/r/{sobject}/{record_id}/view"
        if sobject == "Opportunity":
            return {
                "sobject": sobject,
                "id": record["Id"],
                "name": record.get("Name"),
                "stage_name": record.get("StageName"),
                "close_date": record.get("CloseDate"),
                "description": record.get("Description"),
                "url": url,
            }
        if sobject == "Task":
            return {
                "sobject": sobject,
                "id": record["Id"],
                "subject": record.get("Subject"),
                "status": record.get("Status"),
                "description": record.get("Description"),
                "url": url,
            }
        return {
            "sobject": sobject,
            "id": record["Id"],
            "description": record.get("Description"),
            "url": url,
        }


def opportunity_fields(key: str, body: str, stage: str) -> dict[str, Any]:
    return {
        "Name": key[:120],
        "StageName": stage,
        "CloseDate": (date.today() + timedelta(days=30)).isoformat(),
        "Description": body,
    }


def task_fields(key: str, body: str) -> dict[str, Any]:
    return {"Subject": key, "Status": "Not Started", "Description": body}


def account_fields(body: str) -> dict[str, Any]:
    return {"Description": body}


def record_key(action: str, event_name: str, client_id: str) -> str:
    if action == "update_account":
        return client_id
    return stable_key(event_name, client_id)


def lightning_path(client_id: str, event_name: str) -> str:
    return f"/v1/clients/{quote(client_id, safe='')}/events/{quote(event_name, safe='')}/sfdc"
