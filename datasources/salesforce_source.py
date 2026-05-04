"""SalesforceDataSource — read account-shaped data from a real Salesforce org.

Phase 3a covers Account (`list_accounts`) and Task (`get_usage_events`); Cases
(tickets) and NPS land in Phase 3b and currently return `[]`. The dashboard
displays a "Phase 3b pending" notice when this source is active so a user does
not mistake an empty ticket / NPS column for a healthy account.

Auth is username + password + security token via `simple_salesforce.Salesforce`.
The Connected-App / OAuth flow is intentionally deferred — username+password is
the lowest-friction first connection for a CSM running this locally.

Schema is documented in `docs/datasources/salesforce.md`. The default field
mapping targets a stock Salesforce org; orgs with renamed or hidden fields can
override the default field lists via constructor arguments.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Any

from datasource import DataSource
from models import Account, NpsResponse, Ticket, UsageEvent


log = logging.getLogger(__name__)


# Default Salesforce object/field mapping. A non-standard org overrides these via
# constructor arguments rather than editing the file.
DEFAULT_ACCOUNT_FIELDS: dict[str, str] = {
    # model_field: salesforce_field
    "id": "Id",
    "name": "Name",
    "industry": "Industry",
    "employee_count": "NumberOfEmployees",
    "plan_tier": "Plan_Tier__c",
    "arr_usd": "ARR__c",
    "contract_start": "Contract_Start__c",
    "renewal_date": "Renewal_Date__c",
    "csm_owner": "CSM_Owner__c",
    "primary_contact_name": "Primary_Contact_Name__c",
    "primary_contact_title": "Primary_Contact_Title__c",
}

# Task is the default usage-event source: a stock object every org has, with a
# CreatedDate that maps cleanly to UsageEvent.timestamp. Orgs that store usage
# telemetry on a custom object pass `usage_object="Usage_Event__c"` and override
# the field map.
DEFAULT_USAGE_OBJECT = "Task"
DEFAULT_USAGE_FIELDS: dict[str, str] = {
    "account_id": "AccountId",
    "timestamp": "CreatedDate",
    "event_type": "Type",
    "feature": "Subject",
    "user_id": "OwnerId",
}


def _coerce_int(value: Any, *, field: str, account_id: str | None = None) -> int:
    if value is None:
        ctx = f" (account {account_id})" if account_id else ""
        raise ValueError(f"Salesforce response missing required field '{field}'{ctx}")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Salesforce response field '{field}' is not an integer: {value!r}"
        ) from exc


def _coerce_str(value: Any, *, field: str, account_id: str | None = None) -> str:
    if value is None:
        ctx = f" (account {account_id})" if account_id else ""
        raise ValueError(f"Salesforce response missing required field '{field}'{ctx}")
    return str(value)


def _coerce_date(value: Any, *, field: str) -> date:
    if value is None:
        raise ValueError(f"Salesforce response missing required field '{field}'")
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise ValueError(
            f"Salesforce response field '{field}' is not an ISO date: {value!r}"
        ) from exc


def _coerce_datetime(value: Any, *, field: str) -> datetime:
    if value is None:
        raise ValueError(f"Salesforce response missing required field '{field}'")
    if isinstance(value, datetime):
        return value
    s = str(value)
    # Salesforce returns timestamps as 2026-04-15T14:00:00.000+0000 — strip the
    # fractional seconds and timezone offset down to a form Python's
    # datetime.fromisoformat (3.11+) accepts.
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        # Fall back: trim trailing milliseconds + tz to seconds-resolution.
        try:
            head = s.split("+")[0].split("-")
            # Reassemble YYYY-MM-DDTHH:MM:SS from the leading parts.
            if "T" in s:
                date_part, time_part = s.split("T", 1)
                time_seconds = time_part[:8]
                return datetime.fromisoformat(f"{date_part}T{time_seconds}")
        except (ValueError, IndexError):
            pass
        raise ValueError(
            f"Salesforce response field '{field}' is not an ISO datetime: {value!r}"
        )


class SalesforceDataSource(DataSource):
    """Read accounts and usage events from a Salesforce org via SOQL.

    Tickets and NPS responses return `[]` in Phase 3a. The dashboard shows a
    "Phase 3b pending" notice when this source is active.

    Constructor accepts either a pre-built `simple_salesforce.Salesforce` client
    (for tests) or credentials directly. Field maps default to stock-org names;
    pass `account_fields=...` / `usage_fields=...` to override for non-standard
    orgs.
    """

    def __init__(
        self,
        *,
        username: str | None = None,
        password: str | None = None,
        security_token: str | None = None,
        domain: str = "login",
        client: Any = None,
        account_fields: dict[str, str] | None = None,
        usage_object: str = DEFAULT_USAGE_OBJECT,
        usage_fields: dict[str, str] | None = None,
    ) -> None:
        self.account_fields = account_fields or dict(DEFAULT_ACCOUNT_FIELDS)
        self.usage_object = usage_object
        self.usage_fields = usage_fields or dict(DEFAULT_USAGE_FIELDS)

        if client is not None:
            self._client = client
            return

        if not (username and password and security_token):
            raise ValueError(
                "SalesforceDataSource requires SF_USERNAME, SF_PASSWORD, and "
                "SF_SECURITY_TOKEN (or an explicit `client=` argument)."
            )

        # Defer the import so installing the package doesn't pull simple_salesforce
        # into projects using only the fixture or CSV paths. The dependency is
        # required when this class is instantiated, not when the module is imported.
        from simple_salesforce import Salesforce

        self._client = Salesforce(
            username=username,
            password=password,
            security_token=security_token,
            domain=domain,
        )

    # ----- helpers --------------------------------------------------------

    def _query(self, soql: str) -> list[dict[str, Any]]:
        """Run a SOQL query, surface rate-limit errors, log remaining call count."""
        from simple_salesforce.exceptions import SalesforceError

        try:
            result = self._client.query_all(soql)
        except SalesforceError as exc:
            self._raise_user_error(exc)

        self._log_remaining_calls()
        records = result.get("records", []) if isinstance(result, dict) else []
        return [{k: v for k, v in r.items() if k != "attributes"} for r in records]

    def _raise_user_error(self, exc: Any) -> None:
        """Translate a SalesforceError into a ValueError the dashboard can render."""
        content = getattr(exc, "content", None) or []
        # `content` is typically a list of {"errorCode": ..., "message": ...} dicts.
        error_code = ""
        message = str(exc)
        if isinstance(content, list) and content:
            entry = content[0] if isinstance(content[0], dict) else {}
            error_code = entry.get("errorCode", "") or ""
            message = entry.get("message", message) or message

        if error_code == "REQUEST_LIMIT_EXCEEDED":
            reset_hint = self._format_limit_info()
            suffix = f" Limit info: {reset_hint}." if reset_hint else ""
            raise ValueError(
                f"Salesforce REQUEST_LIMIT_EXCEEDED: {message}{suffix}"
            ) from exc

        raise ValueError(f"Salesforce SOQL error ({error_code or 'unknown'}): {message}") from exc

    def _format_limit_info(self) -> str:
        """Read the most recent Sforce-Limit-Info header for human-readable
        rate-limit context. Returns an empty string if unavailable."""
        headers = self._latest_headers()
        if not headers:
            return ""
        info = headers.get("Sforce-Limit-Info") or headers.get("sforce-limit-info") or ""
        return str(info)

    def _latest_headers(self) -> dict[str, Any]:
        """simple_salesforce stashes the last response's headers on its session.
        Try a few attribute paths for cross-version compatibility; return {} on miss."""
        for attr in ("headers", "_last_headers"):
            value = getattr(self._client, attr, None)
            if isinstance(value, dict):
                return value
        session = getattr(self._client, "session", None)
        last = getattr(session, "headers", None)
        return last if isinstance(last, dict) else {}

    def _log_remaining_calls(self) -> None:
        """Log API consumption after each query so users with smaller orgs can
        watch the budget. Sforce-Limit-Info is `api-usage=N/M`."""
        info = self._format_limit_info()
        if info:
            log.info("Salesforce API usage: %s", info)

    @staticmethod
    def _soql_quote(value: str) -> str:
        """Escape a string for inline SOQL. simple_salesforce's bind-parameter
        support varies by version, so manual escaping is the portable path."""
        return value.replace("\\", "\\\\").replace("'", "\\'")

    # ----- DataSource interface ------------------------------------------

    def list_accounts(self) -> list[Account]:
        fields = self.account_fields
        select_fields = ", ".join(fields[k] for k in fields)
        soql = f"SELECT {select_fields} FROM Account"
        records = self._query(soql)

        out: list[Account] = []
        for record in records:
            account_id = record.get(fields["id"])
            payload = {
                "id": _coerce_str(account_id, field=fields["id"]),
                "name": _coerce_str(record.get(fields["name"]), field=fields["name"], account_id=account_id),
                "industry": _coerce_str(record.get(fields["industry"]), field=fields["industry"], account_id=account_id),
                "employee_count": _coerce_int(
                    record.get(fields["employee_count"]),
                    field=fields["employee_count"],
                    account_id=account_id,
                ),
                "plan_tier": _coerce_str(record.get(fields["plan_tier"]), field=fields["plan_tier"], account_id=account_id),
                "arr_usd": _coerce_int(
                    record.get(fields["arr_usd"]),
                    field=fields["arr_usd"],
                    account_id=account_id,
                ),
                "contract_start": _coerce_date(
                    record.get(fields["contract_start"]),
                    field=fields["contract_start"],
                ),
                "renewal_date": _coerce_date(
                    record.get(fields["renewal_date"]),
                    field=fields["renewal_date"],
                ),
                "csm_owner": _coerce_str(record.get(fields["csm_owner"]), field=fields["csm_owner"], account_id=account_id),
                "primary_contact_name": _coerce_str(
                    record.get(fields["primary_contact_name"]),
                    field=fields["primary_contact_name"],
                    account_id=account_id,
                ),
                "primary_contact_title": _coerce_str(
                    record.get(fields["primary_contact_title"]),
                    field=fields["primary_contact_title"],
                    account_id=account_id,
                ),
            }
            out.append(Account.model_validate(payload))
        return out

    def get_usage_events(self, account_id: str, since: date | None = None) -> list[UsageEvent]:
        fields = self.usage_fields
        select_fields = ", ".join(fields[k] for k in fields)
        where = f"{fields['account_id']} = '{self._soql_quote(account_id)}'"
        if since is not None:
            where += f" AND {fields['timestamp']} >= {since.isoformat()}T00:00:00Z"
        soql = f"SELECT {select_fields} FROM {self.usage_object} WHERE {where}"
        records = self._query(soql)

        out: list[UsageEvent] = []
        for record in records:
            payload = {
                "account_id": _coerce_str(
                    record.get(fields["account_id"]),
                    field=fields["account_id"],
                ),
                "timestamp": _coerce_datetime(
                    record.get(fields["timestamp"]),
                    field=fields["timestamp"],
                ),
                "event_type": _coerce_str(
                    record.get(fields["event_type"]),
                    field=fields["event_type"],
                ),
                "feature": record.get(fields["feature"]),  # optional in the model
                "user_id": _coerce_str(
                    record.get(fields["user_id"]),
                    field=fields["user_id"],
                ),
            }
            out.append(UsageEvent.model_validate(payload))
        return out

    def get_tickets(self, account_id: str) -> list[Ticket]:
        # Phase 3b: Cases land here. Returning [] keeps the dashboard renderable
        # against real Salesforce data; the sidebar surfaces a "Phase 3b pending"
        # notice so the empty column isn't mistaken for a healthy account.
        return []

    def get_nps_responses(self, account_id: str) -> list[NpsResponse]:
        # Phase 3b: NPS custom objects land here.
        return []


def from_env() -> SalesforceDataSource:
    """Build a SalesforceDataSource from SF_USERNAME / SF_PASSWORD /
    SF_SECURITY_TOKEN / SF_DOMAIN env vars. Raises ValueError when any required
    var is missing — the app.py factory catches that to fall back to fixtures."""
    return SalesforceDataSource(
        username=os.environ.get("SF_USERNAME"),
        password=os.environ.get("SF_PASSWORD"),
        security_token=os.environ.get("SF_SECURITY_TOKEN"),
        domain=os.environ.get("SF_DOMAIN", "login").strip() or "login",
    )
