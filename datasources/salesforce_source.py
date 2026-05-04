"""SalesforceDataSource — read account-shaped data from a real Salesforce org.

All four `DataSource` methods are wired: `list_accounts` (Account), `get_usage_events`
(Task by default), `get_tickets` (Case), and `get_nps_responses` (custom NPS object,
default `NPS_Response__c`). Auth is username + password + security token via
`simple_salesforce.Salesforce`. The Connected-App / OAuth flow is intentionally
deferred — username+password is the lowest-friction first connection for a CSM
running this locally.

Schema is documented in `docs/datasources/salesforce.md`. The default field
mapping targets a stock Salesforce org; orgs with renamed or hidden fields can
override the default field lists via constructor arguments. NPS objects are
particularly variable across orgs — the constructor exposes `nps_object` and
`score_field` overrides, and an org without an NPS custom object at all gets a
soft `[]` fallback rather than a hard error.
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

# Case (Tickets) field mapping. Case is a stock object every org has. Subject /
# Type / Priority / Status are standard fields; CaseNumber is the
# user-facing display ID and the natural choice for `Ticket.id`.
DEFAULT_CASE_FIELDS: dict[str, str] = {
    "id": "CaseNumber",
    "account_id": "AccountId",
    "created_at": "CreatedDate",
    "resolved_at": "ClosedDate",
    "severity": "Priority",
    "status": "Status",
    "subject": "Subject",
    "category": "Type",
}

# Salesforce Case Priority picklist → TicketSeverity literal.
# Stock orgs ship with High / Medium / Low. Many orgs add Critical. Anything
# outside this set logs-and-skips to "low" (a quiet floor) rather than raising,
# so an unfamiliar picklist value never breaks the dashboard.
DEFAULT_PRIORITY_MAP: dict[str, str] = {
    "Critical": "critical",
    "High": "high",
    "Medium": "medium",
    "Low": "low",
}

# Salesforce Case Status picklist → TicketStatus literal.
# Stock New/Working/Escalated map to "open"; Closed → "resolved"; On Hold →
# "pending". Unknown values log-and-skip to "open" (the safest floor — a ticket
# we don't recognize is probably still actionable).
DEFAULT_STATUS_MAP: dict[str, str] = {
    "New": "open",
    "Working": "open",
    "Escalated": "open",
    "On Hold": "pending",
    "Closed": "resolved",
}

# NPS custom object. Salesforce has no stock NPS object — orgs add their own
# (commonly `NPS_Response__c`) or use a third-party survey app's schema. The
# defaults below assume the common case and the constructor exposes
# `nps_object` and `score_field` for orgs whose schema differs.
DEFAULT_NPS_OBJECT = "NPS_Response__c"
DEFAULT_NPS_SCORE_FIELD = "Score__c"
DEFAULT_NPS_FIELDS: dict[str, str] = {
    "account_id": "Account__c",
    "submitted_at": "Created_Date__c",
    # `score` is filled from the configurable `score_field` arg, not this dict.
    "comment": "Comment__c",
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


def _is_invalid_type_error(exc: Any) -> bool:
    """True if a SalesforceError signals that the requested sObject doesn't
    exist in this org. Salesforce surfaces this as `errorCode=INVALID_TYPE`."""
    content = getattr(exc, "content", None) or []
    if isinstance(content, list) and content:
        entry = content[0] if isinstance(content[0], dict) else {}
        return entry.get("errorCode") == "INVALID_TYPE"
    return False


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
    """Read accounts, usage events, tickets, and NPS responses from a Salesforce
    org via SOQL.

    Constructor accepts either a pre-built `simple_salesforce.Salesforce` client
    (for tests) or credentials directly. Field maps default to stock-org names;
    pass `account_fields=...` / `usage_fields=...` / `case_fields=...` /
    `nps_fields=...` to override for non-standard orgs. NPS object and score
    field are also configurable (`nps_object=`, `score_field=`).
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
        case_fields: dict[str, str] | None = None,
        priority_map: dict[str, str] | None = None,
        status_map: dict[str, str] | None = None,
        nps_object: str = DEFAULT_NPS_OBJECT,
        score_field: str = DEFAULT_NPS_SCORE_FIELD,
        nps_fields: dict[str, str] | None = None,
    ) -> None:
        self.account_fields = account_fields or dict(DEFAULT_ACCOUNT_FIELDS)
        self.usage_object = usage_object
        self.usage_fields = usage_fields or dict(DEFAULT_USAGE_FIELDS)
        self.case_fields = case_fields or dict(DEFAULT_CASE_FIELDS)
        self.priority_map = priority_map or dict(DEFAULT_PRIORITY_MAP)
        self.status_map = status_map or dict(DEFAULT_STATUS_MAP)
        self.nps_object = nps_object
        self.score_field = score_field
        self.nps_fields = nps_fields or dict(DEFAULT_NPS_FIELDS)

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
        fields = self.case_fields
        select_fields = ", ".join(fields[k] for k in fields)
        where = f"{fields['account_id']} = '{self._soql_quote(account_id)}'"
        soql = f"SELECT {select_fields} FROM Case WHERE {where}"
        records = self._query(soql)

        out: list[Ticket] = []
        for record in records:
            severity = self._map_priority(record.get(fields["severity"]))
            status = self._map_status(record.get(fields["status"]))
            resolved_raw = record.get(fields["resolved_at"])
            resolved_at = (
                _coerce_datetime(resolved_raw, field=fields["resolved_at"])
                if resolved_raw is not None
                else None
            )
            payload = {
                "id": _coerce_str(record.get(fields["id"]), field=fields["id"]),
                "account_id": _coerce_str(
                    record.get(fields["account_id"]),
                    field=fields["account_id"],
                ),
                "created_at": _coerce_datetime(
                    record.get(fields["created_at"]),
                    field=fields["created_at"],
                ),
                "resolved_at": resolved_at,
                "severity": severity,
                "status": status,
                "subject": _coerce_str(
                    record.get(fields["subject"]),
                    field=fields["subject"],
                ),
                "category": _coerce_str(
                    record.get(fields["category"]),
                    field=fields["category"],
                ),
            }
            out.append(Ticket.model_validate(payload))
        return out

    def get_nps_responses(self, account_id: str) -> list[NpsResponse]:
        from simple_salesforce.exceptions import SalesforceError

        fields = self.nps_fields
        select_clause = ", ".join(
            [fields["account_id"], fields["submitted_at"], self.score_field, fields["comment"]]
        )
        where = f"{fields['account_id']} = '{self._soql_quote(account_id)}'"
        soql = f"SELECT {select_clause} FROM {self.nps_object} WHERE {where}"

        try:
            result = self._client.query_all(soql)
        except SalesforceError as exc:
            if _is_invalid_type_error(exc):
                log.info(
                    "NPS object '%s' not present in this org — returning [] (override "
                    "via nps_object= constructor arg if your org uses a different name).",
                    self.nps_object,
                )
                return []
            self._raise_user_error(exc)

        self._log_remaining_calls()
        records = result.get("records", []) if isinstance(result, dict) else []
        records = [{k: v for k, v in r.items() if k != "attributes"} for r in records]

        out: list[NpsResponse] = []
        for record in records:
            payload = {
                "account_id": _coerce_str(
                    record.get(fields["account_id"]),
                    field=fields["account_id"],
                ),
                "submitted_at": _coerce_datetime(
                    record.get(fields["submitted_at"]),
                    field=fields["submitted_at"],
                ),
                "score": _coerce_int(
                    record.get(self.score_field),
                    field=self.score_field,
                ),
                "comment": record.get(fields["comment"]),  # optional in the model
            }
            out.append(NpsResponse.model_validate(payload))
        return out

    def _map_priority(self, raw: Any) -> str:
        """Map a Salesforce Case Priority value to TicketSeverity. Unknown
        values log and floor to 'low' so an unfamiliar picklist value never
        breaks the dashboard."""
        if raw in self.priority_map:
            return self.priority_map[raw]
        log.info(
            "Unknown Case Priority value %r — defaulting severity to 'low'. "
            "Override via priority_map= constructor arg to map this value explicitly.",
            raw,
        )
        return "low"

    def _map_status(self, raw: Any) -> str:
        """Map a Salesforce Case Status value to TicketStatus. Unknown values
        log and floor to 'open' so unrecognized states still surface for
        review."""
        if raw in self.status_map:
            return self.status_map[raw]
        log.info(
            "Unknown Case Status value %r — defaulting status to 'open'. "
            "Override via status_map= constructor arg to map this value explicitly.",
            raw,
        )
        return "open"


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
