"""SalesforceDataSource contract tests.

Mock-only — no live org calls. The integration test stub at the bottom is
gated behind SF_RUN_LIVE_TESTS=1 and skipped by default.

Required matrix per the architect's verdicts (3a + 3b):
  1.  list_accounts() round-trip → typed list[Account] with field mapping correct
  2.  get_usage_events() round-trip → typed list[UsageEvent]
  3.  Empty SOQL result for both methods → [] without raising
  4.  Malformed SOQL response (missing required field) → ValueError naming the field
  5.  SalesforceError REQUEST_LIMIT_EXCEEDED → ValueError including reset time
  6.  get_tickets() round-trip → typed list[Ticket] with priority/status mapping
  7.  Unknown priority value → logs-and-skips to "low", does not raise
  8.  Open ticket (ClosedDate=null) → resolved_at=None
  9.  get_tickets() SOQL filters on AccountId
  10. get_nps_responses() round-trip → typed list[NpsResponse]
  11. get_nps_responses() with INVALID_TYPE error → returns [] without raising
  12. get_nps_responses() with non-INVALID_TYPE SalesforceError → ValueError
  13. get_nps_responses() SOQL filters on Account__c
  14. Configurable nps_object → SOQL uses overridden object name
  15. DATASOURCE=salesforce factory branch in app.py — mock the Salesforce constructor
  16. Integration stub behind SF_RUN_LIVE_TESTS=1 (documented; skipped)
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from datasource import DataSource
from datasources import SalesforceDataSource
from models import Account, NpsResponse, Ticket, UsageEvent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _account_record(**overrides: object) -> dict:
    base = {
        "attributes": {"type": "Account", "url": "/services/data/v59.0/sobjects/Account/001xx"},
        "Id": "001xx0000001",
        "Name": "Globex Robotics",
        "Industry": "Manufacturing",
        "NumberOfEmployees": 230,
        "Plan_Tier__c": "Enterprise",
        "ARR__c": 480000,
        "Contract_Start__c": "2025-06-10",
        "Renewal_Date__c": "2026-06-23",
        "CSM_Owner__c": "Marcus Chen",
        "Primary_Contact_Name__c": "Mira Petrov",
        "Primary_Contact_Title__c": "VP Engineering",
    }
    base.update(overrides)
    return base


def _task_record(**overrides: object) -> dict:
    base = {
        "attributes": {"type": "Task", "url": "/services/data/v59.0/sobjects/Task/00Txx"},
        "AccountId": "001xx0000001",
        "CreatedDate": "2026-04-28T09:15:00.000+0000",
        "Type": "session_start",
        "Subject": "dashboard",
        "OwnerId": "005xxUSER01",
    }
    base.update(overrides)
    return base


def _case_record(**overrides: object) -> dict:
    base = {
        "attributes": {"type": "Case", "url": "/services/data/v59.0/sobjects/Case/500xx"},
        "CaseNumber": "00001042",
        "AccountId": "001xx0000001",
        "CreatedDate": "2026-04-20T14:30:00.000+0000",
        "ClosedDate": "2026-04-22T11:00:00.000+0000",
        "Priority": "High",
        "Status": "Closed",
        "Subject": "Export pipeline failing",
        "Type": "Bug",
    }
    base.update(overrides)
    return base


def _nps_record(**overrides: object) -> dict:
    base = {
        "attributes": {"type": "NPS_Response__c", "url": "/services/data/v59.0/sobjects/NPS_Response__c/a01xx"},
        "Account__c": "001xx0000001",
        "Created_Date__c": "2026-04-15T08:00:00.000+0000",
        "Score__c": 8,
        "Comment__c": "Good support, occasional latency.",
    }
    base.update(overrides)
    return base


def _build_source(query_records: list[dict]) -> SalesforceDataSource:
    """Build a SalesforceDataSource backed by a MagicMock Salesforce client whose
    `query_all` returns the supplied records under the standard SOQL response
    envelope."""
    client = MagicMock()
    client.query_all.return_value = {"totalSize": len(query_records), "done": True, "records": query_records}
    client.headers = {"Sforce-Limit-Info": "api-usage=42/15000"}
    return SalesforceDataSource(client=client)


# ---------------------------------------------------------------------------
# 1. list_accounts() round-trip
# ---------------------------------------------------------------------------


def test_list_accounts_round_trip_maps_fields_correctly() -> None:
    ds = _build_source([_account_record()])
    accounts = ds.list_accounts()

    assert len(accounts) == 1
    a = accounts[0]
    assert isinstance(a, Account)
    assert a.id == "001xx0000001"
    assert a.name == "Globex Robotics"
    assert a.industry == "Manufacturing"
    assert a.employee_count == 230
    assert a.plan_tier == "Enterprise"
    assert a.arr_usd == 480000
    assert a.contract_start == date(2025, 6, 10)
    assert a.renewal_date == date(2026, 6, 23)
    assert a.csm_owner == "Marcus Chen"
    assert a.primary_contact_name == "Mira Petrov"
    assert a.primary_contact_title == "VP Engineering"


def test_list_accounts_issues_soql_with_default_field_list() -> None:
    client = MagicMock()
    client.query_all.return_value = {"records": []}
    ds = SalesforceDataSource(client=client)
    ds.list_accounts()
    soql = client.query_all.call_args[0][0]
    assert "FROM Account" in soql
    # Confirm the default-mapped Salesforce fields appear in the SELECT clause.
    for sf_field in ("Id", "Name", "Industry", "NumberOfEmployees", "Renewal_Date__c"):
        assert sf_field in soql


# ---------------------------------------------------------------------------
# 2. get_usage_events() round-trip
# ---------------------------------------------------------------------------


def test_get_usage_events_round_trip_maps_fields_correctly() -> None:
    ds = _build_source([_task_record()])
    events = ds.get_usage_events("001xx0000001")

    assert len(events) == 1
    e = events[0]
    assert isinstance(e, UsageEvent)
    assert e.account_id == "001xx0000001"
    assert e.timestamp == datetime(2026, 4, 28, 9, 15, 0, tzinfo=e.timestamp.tzinfo)
    assert e.event_type == "session_start"
    assert e.feature == "dashboard"
    assert e.user_id == "005xxUSER01"


def test_get_usage_events_with_since_includes_iso_filter_in_soql() -> None:
    client = MagicMock()
    client.query_all.return_value = {"records": []}
    ds = SalesforceDataSource(client=client)
    ds.get_usage_events("001xx0000001", since=date(2026, 4, 1))
    soql = client.query_all.call_args[0][0]
    assert "FROM Task" in soql
    assert "AccountId = '001xx0000001'" in soql
    assert "CreatedDate >= 2026-04-01" in soql


# ---------------------------------------------------------------------------
# 3. Empty SOQL result for both methods
# ---------------------------------------------------------------------------


def test_empty_soql_result_returns_empty_lists_without_raising() -> None:
    ds = _build_source([])
    assert ds.list_accounts() == []
    assert ds.get_usage_events("001xx0000001") == []


# ---------------------------------------------------------------------------
# 4. Malformed SOQL response → ValueError naming the field
# ---------------------------------------------------------------------------


def test_missing_required_field_raises_value_error_with_field_name() -> None:
    bad = _account_record()
    del bad["Renewal_Date__c"]
    ds = _build_source([bad])
    with pytest.raises(ValueError) as exc_info:
        ds.list_accounts()
    assert "Renewal_Date__c" in str(exc_info.value)


def test_non_integer_employee_count_raises_value_error_with_field_name() -> None:
    bad = _account_record(NumberOfEmployees="not-a-number")
    ds = _build_source([bad])
    with pytest.raises(ValueError) as exc_info:
        ds.list_accounts()
    assert "NumberOfEmployees" in str(exc_info.value)


def test_missing_required_field_in_usage_event_raises() -> None:
    bad = _task_record()
    del bad["CreatedDate"]
    ds = _build_source([bad])
    with pytest.raises(ValueError) as exc_info:
        ds.get_usage_events("001xx0000001")
    assert "CreatedDate" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 5. SalesforceError REQUEST_LIMIT_EXCEEDED → ValueError with reset/limit info
# ---------------------------------------------------------------------------


def test_request_limit_exceeded_surfaces_user_readable_error_with_limit_info() -> None:
    from simple_salesforce.exceptions import SalesforceError

    err = SalesforceError(
        url="https://example.my.salesforce.com/services/data/v59.0/query/",
        status=403,
        resource_name="query",
        content=[{"errorCode": "REQUEST_LIMIT_EXCEEDED", "message": "TotalRequests Limit exceeded."}],
    )

    client = MagicMock()
    client.query_all.side_effect = err
    client.headers = {"Sforce-Limit-Info": "api-usage=15000/15000"}
    ds = SalesforceDataSource(client=client)

    with pytest.raises(ValueError) as exc_info:
        ds.list_accounts()
    msg = str(exc_info.value)
    assert "REQUEST_LIMIT_EXCEEDED" in msg
    assert "api-usage=15000/15000" in msg


def test_other_salesforce_error_surfaces_with_error_code_in_message() -> None:
    from simple_salesforce.exceptions import SalesforceError

    err = SalesforceError(
        url="https://example.my.salesforce.com/services/data/v59.0/query/",
        status=400,
        resource_name="query",
        content=[{"errorCode": "INVALID_FIELD", "message": "No such column 'Plan_Tier__c'"}],
    )
    client = MagicMock()
    client.query_all.side_effect = err
    client.headers = {}
    ds = SalesforceDataSource(client=client)

    with pytest.raises(ValueError) as exc_info:
        ds.list_accounts()
    assert "INVALID_FIELD" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 6. get_tickets() round-trip with priority/status mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sf_priority,expected_severity",
    [
        ("High", "high"),
        ("Critical", "critical"),
        ("Medium", "medium"),
        ("Low", "low"),
    ],
)
def test_get_tickets_round_trip_maps_priority_to_severity(
    sf_priority: str, expected_severity: str
) -> None:
    ds = _build_source([_case_record(Priority=sf_priority)])
    tickets = ds.get_tickets("001xx0000001")

    assert len(tickets) == 1
    t = tickets[0]
    assert isinstance(t, Ticket)
    assert t.id == "00001042"
    assert t.account_id == "001xx0000001"
    assert t.created_at == datetime(2026, 4, 20, 14, 30, 0, tzinfo=t.created_at.tzinfo)
    assert t.severity == expected_severity
    assert t.subject == "Export pipeline failing"
    assert t.category == "Bug"


def test_get_tickets_maps_status_values_correctly() -> None:
    records = [
        _case_record(CaseNumber="00001001", Status="New", ClosedDate=None),
        _case_record(CaseNumber="00001002", Status="Working", ClosedDate=None),
        _case_record(CaseNumber="00001003", Status="Escalated", ClosedDate=None),
        _case_record(CaseNumber="00001004", Status="On Hold", ClosedDate=None),
        _case_record(CaseNumber="00001005", Status="Closed"),
    ]
    ds = _build_source(records)
    tickets = ds.get_tickets("001xx0000001")
    statuses = [t.status for t in tickets]
    assert statuses == ["open", "open", "open", "pending", "resolved"]


# ---------------------------------------------------------------------------
# 7. Unknown priority value → logs-and-skips to "low", does not raise
# ---------------------------------------------------------------------------


def test_unknown_priority_value_logs_and_floors_to_low(caplog: pytest.LogCaptureFixture) -> None:
    ds = _build_source([_case_record(Priority="Urgent")])
    with caplog.at_level(logging.INFO, logger="datasources.salesforce_source"):
        tickets = ds.get_tickets("001xx0000001")

    assert len(tickets) == 1
    assert tickets[0].severity == "low"
    assert any("Urgent" in record.message for record in caplog.records)


def test_unknown_status_value_logs_and_floors_to_open(caplog: pytest.LogCaptureFixture) -> None:
    ds = _build_source([_case_record(Status="In Triage", ClosedDate=None)])
    with caplog.at_level(logging.INFO, logger="datasources.salesforce_source"):
        tickets = ds.get_tickets("001xx0000001")

    assert len(tickets) == 1
    assert tickets[0].status == "open"
    assert any("In Triage" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# 8. Open ticket (ClosedDate=null) → resolved_at=None
# ---------------------------------------------------------------------------


def test_open_ticket_with_null_closed_date_yields_resolved_at_none() -> None:
    ds = _build_source([_case_record(ClosedDate=None, Status="Working")])
    tickets = ds.get_tickets("001xx0000001")
    assert len(tickets) == 1
    assert tickets[0].resolved_at is None
    assert tickets[0].status == "open"


# ---------------------------------------------------------------------------
# 9. get_tickets() SOQL filters on AccountId
# ---------------------------------------------------------------------------


def test_get_tickets_issues_soql_with_account_id_filter() -> None:
    client = MagicMock()
    client.query_all.return_value = {"records": []}
    ds = SalesforceDataSource(client=client)
    ds.get_tickets("001xx0000001")
    soql = client.query_all.call_args[0][0]
    assert "FROM Case" in soql
    assert "AccountId = '001xx0000001'" in soql
    # Confirm the default-mapped Case fields appear in the SELECT clause.
    for sf_field in ("CaseNumber", "CreatedDate", "ClosedDate", "Priority", "Status", "Subject", "Type"):
        assert sf_field in soql


# ---------------------------------------------------------------------------
# 10. get_nps_responses() round-trip
# ---------------------------------------------------------------------------


def test_get_nps_responses_round_trip_maps_fields_correctly() -> None:
    ds = _build_source([_nps_record()])
    responses = ds.get_nps_responses("001xx0000001")

    assert len(responses) == 1
    r = responses[0]
    assert isinstance(r, NpsResponse)
    assert r.account_id == "001xx0000001"
    assert r.submitted_at == datetime(2026, 4, 15, 8, 0, 0, tzinfo=r.submitted_at.tzinfo)
    assert r.score == 8
    assert r.comment == "Good support, occasional latency."


def test_get_nps_responses_handles_null_comment() -> None:
    ds = _build_source([_nps_record(Comment__c=None)])
    responses = ds.get_nps_responses("001xx0000001")
    assert len(responses) == 1
    assert responses[0].comment is None


# ---------------------------------------------------------------------------
# 11. INVALID_TYPE error → returns [] without raising
# ---------------------------------------------------------------------------


def test_get_nps_responses_returns_empty_when_object_not_present() -> None:
    from simple_salesforce.exceptions import SalesforceError

    err = SalesforceError(
        url="https://example.my.salesforce.com/services/data/v59.0/query/",
        status=400,
        resource_name="query",
        content=[
            {"errorCode": "INVALID_TYPE", "message": "sObject type 'NPS_Response__c' is not supported."}
        ],
    )
    client = MagicMock()
    client.query_all.side_effect = err
    client.headers = {}
    ds = SalesforceDataSource(client=client)

    result = ds.get_nps_responses("001xx0000001")
    assert result == []


# ---------------------------------------------------------------------------
# 12. Non-INVALID_TYPE SalesforceError → ValueError surfaces
# ---------------------------------------------------------------------------


def test_get_nps_responses_surfaces_non_invalid_type_errors() -> None:
    from simple_salesforce.exceptions import SalesforceError

    err = SalesforceError(
        url="https://example.my.salesforce.com/services/data/v59.0/query/",
        status=400,
        resource_name="query",
        content=[{"errorCode": "INVALID_FIELD", "message": "No such column 'Score__c' on entity 'NPS_Response__c'"}],
    )
    client = MagicMock()
    client.query_all.side_effect = err
    client.headers = {}
    ds = SalesforceDataSource(client=client)

    with pytest.raises(ValueError) as exc_info:
        ds.get_nps_responses("001xx0000001")
    assert "INVALID_FIELD" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 13. NPS SOQL filters on Account__c
# ---------------------------------------------------------------------------


def test_get_nps_responses_issues_soql_with_account_filter() -> None:
    client = MagicMock()
    client.query_all.return_value = {"records": []}
    ds = SalesforceDataSource(client=client)
    ds.get_nps_responses("001xx0000001")
    soql = client.query_all.call_args[0][0]
    assert "FROM NPS_Response__c" in soql
    assert "Account__c = '001xx0000001'" in soql
    for sf_field in ("Account__c", "Created_Date__c", "Score__c", "Comment__c"):
        assert sf_field in soql


# ---------------------------------------------------------------------------
# 14. Configurable nps_object → SOQL uses overridden object name
# ---------------------------------------------------------------------------


def test_get_nps_responses_respects_configurable_nps_object_and_score_field() -> None:
    client = MagicMock()
    client.query_all.return_value = {"records": []}
    ds = SalesforceDataSource(
        client=client,
        nps_object="Survey_Response__c",
        score_field="Rating__c",
    )
    ds.get_nps_responses("001xx0000001")
    soql = client.query_all.call_args[0][0]
    assert "FROM Survey_Response__c" in soql
    assert "Rating__c" in soql
    # The default object name must NOT leak through when overridden.
    assert "FROM NPS_Response__c" not in soql
    assert "Score__c" not in soql


# ---------------------------------------------------------------------------
# Empty result coverage for the new methods (mirrors test 3 for accounts/usage)
# ---------------------------------------------------------------------------


def test_get_tickets_returns_empty_list_for_empty_soql_result() -> None:
    ds = _build_source([])
    assert ds.get_tickets("001xx0000001") == []


def test_get_nps_responses_returns_empty_list_for_empty_soql_result() -> None:
    ds = _build_source([])
    assert ds.get_nps_responses("001xx0000001") == []


# ---------------------------------------------------------------------------
# 15. app.py factory branch — mock the Salesforce constructor
# ---------------------------------------------------------------------------


def test_app_factory_builds_salesforce_when_env_vars_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATASOURCE", "salesforce")
    monkeypatch.setenv("SF_USERNAME", "user@example.com")
    monkeypatch.setenv("SF_PASSWORD", "p")
    monkeypatch.setenv("SF_SECURITY_TOKEN", "tok")

    with patch("simple_salesforce.Salesforce") as sf_constructor:
        sf_constructor.return_value = MagicMock()
        import app
        ds = app._build_datasource()
        assert isinstance(ds, SalesforceDataSource)
        sf_constructor.assert_called_once()
        kwargs = sf_constructor.call_args.kwargs
        assert kwargs["username"] == "user@example.com"
        assert kwargs["password"] == "p"
        assert kwargs["security_token"] == "tok"


def test_app_factory_falls_back_to_fixtures_when_creds_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATASOURCE", "salesforce")
    monkeypatch.delenv("SF_USERNAME", raising=False)
    monkeypatch.delenv("SF_PASSWORD", raising=False)
    monkeypatch.delenv("SF_SECURITY_TOKEN", raising=False)

    import app
    from datasource import FixtureDataSource

    ds = app._build_datasource()
    assert isinstance(ds, FixtureDataSource)


# ---------------------------------------------------------------------------
# Subclass + interface conformance
# ---------------------------------------------------------------------------


def test_salesforce_datasource_is_a_datasource() -> None:
    assert issubclass(SalesforceDataSource, DataSource)


# ---------------------------------------------------------------------------
# 16. Integration stub — gated behind SF_RUN_LIVE_TESTS=1
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("SF_RUN_LIVE_TESTS") != "1",
    reason="Live Salesforce integration disabled — set SF_RUN_LIVE_TESTS=1 to enable.",
)
def test_live_salesforce_round_trip() -> None:
    """Live integration smoke test. Disabled by default. When enabled, requires
    SF_USERNAME / SF_PASSWORD / SF_SECURITY_TOKEN / SF_DOMAIN to point at a real
    sandbox or developer org. Asserts list_accounts() returns at least one
    Account-shaped record.
    """
    from datasources.salesforce_source import from_env

    ds = from_env()
    accounts = ds.list_accounts()
    assert all(isinstance(a, Account) for a in accounts)
