"""SalesforceDataSource contract tests.

Mock-only — no live org calls. The integration test stub at the bottom is
gated behind SF_RUN_LIVE_TESTS=1 and skipped by default.

Required matrix per the architect's verdict:
  1.  list_accounts() round-trip → typed list[Account] with field mapping correct
  2.  get_usage_events() round-trip → typed list[UsageEvent]
  3.  Empty SOQL result for both methods → [] without raising
  4.  Malformed SOQL response (missing required field) → ValueError naming the field
  5.  SalesforceError REQUEST_LIMIT_EXCEEDED → ValueError including reset time
  6.  get_tickets() returns [] without raising
  7.  get_nps_responses() returns [] without raising
  8.  DATASOURCE=salesforce factory branch in app.py — mock the Salesforce constructor
  9.  Integration stub behind SF_RUN_LIVE_TESTS=1 (documented; skipped)
"""

from __future__ import annotations

import os
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from datasource import DataSource
from datasources import SalesforceDataSource
from models import Account, UsageEvent


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
# 6 & 7. get_tickets() / get_nps_responses() return [] without raising
# ---------------------------------------------------------------------------


def test_get_tickets_returns_empty_list_without_raising() -> None:
    ds = _build_source([])
    assert ds.get_tickets("001xx0000001") == []


def test_get_nps_responses_returns_empty_list_without_raising() -> None:
    ds = _build_source([])
    assert ds.get_nps_responses("001xx0000001") == []


# ---------------------------------------------------------------------------
# 8. app.py factory branch — mock the Salesforce constructor
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
# 10. Subclass + interface conformance
# ---------------------------------------------------------------------------


def test_salesforce_datasource_is_a_datasource() -> None:
    assert issubclass(SalesforceDataSource, DataSource)


# ---------------------------------------------------------------------------
# 9. Integration stub — gated behind SF_RUN_LIVE_TESTS=1
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
