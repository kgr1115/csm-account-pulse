"""DataSource contract tests. The interface is the README's load-bearing claim;
tests pin its shape so a refactor that breaks it gets caught at PR time."""

from __future__ import annotations

from datetime import date

import pytest

from datasource import FixtureDataSource
from models import Account, NpsResponse, Ticket, UsageEvent


@pytest.fixture(scope="module")
def ds() -> FixtureDataSource:
    return FixtureDataSource()


def test_list_accounts_returns_typed_accounts(ds: FixtureDataSource) -> None:
    """50 seed-generated (ACC-001..ACC-050) plus 7 hand-crafted eval-scenario
    accounts (ACC-051..ACC-057) — see evals/methodology.md "Scenario expansion policy"."""
    accounts = ds.list_accounts()
    assert len(accounts) == 57
    assert all(isinstance(a, Account) for a in accounts)
    assert len({a.id for a in accounts}) == 57, "account ids must be unique"


def test_account_ids_match_id_format(ds: FixtureDataSource) -> None:
    for a in ds.list_accounts():
        assert a.id.startswith("ACC-") and a.id[4:].isdigit()


def test_get_usage_events_returns_typed(ds: FixtureDataSource) -> None:
    a = ds.list_accounts()[0]
    events = ds.get_usage_events(a.id)
    assert len(events) > 0
    assert all(isinstance(e, UsageEvent) for e in events)
    assert all(e.account_id == a.id for e in events)


def test_get_usage_events_since_filters_correctly(ds: FixtureDataSource) -> None:
    a = ds.list_accounts()[0]
    all_events = ds.get_usage_events(a.id)
    cutoff = date(2026, 4, 1)
    filtered = ds.get_usage_events(a.id, since=cutoff)
    assert all(e.timestamp.date() >= cutoff for e in filtered)
    assert len(filtered) <= len(all_events)


def test_get_tickets_returns_typed(ds: FixtureDataSource) -> None:
    a = ds.list_accounts()[0]
    tickets = ds.get_tickets(a.id)
    assert all(isinstance(t, Ticket) for t in tickets)
    assert all(t.account_id == a.id for t in tickets)


def test_get_nps_responses_returns_typed(ds: FixtureDataSource) -> None:
    a = ds.list_accounts()[0]
    nps = ds.get_nps_responses(a.id)
    assert all(isinstance(n, NpsResponse) for n in nps)
    assert all(n.account_id == a.id for n in nps)


def test_unknown_account_returns_empty_lists(ds: FixtureDataSource) -> None:
    assert ds.get_usage_events("ACC-999") == []
    assert ds.get_tickets("ACC-999") == []
    assert ds.get_nps_responses("ACC-999") == []
