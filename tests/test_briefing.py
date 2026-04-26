"""Briefing tests. The two high-leverage invariants:
  1. The stub path produces structurally-valid Briefings without an API key
     (this is what runs on a recruiter's laptop with no key set).
  2. Every citation in every briefing resolves to a real fixture field
     (this is the "the LLM will invent signals" gotcha from CLAUDE.md).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from briefing import generate_briefing
from datasource import FixtureDataSource
from health import compute_health
from models import AccountState, Briefing, HealthBucket


TODAY = date(2026, 4, 26)


@pytest.fixture(scope="module")
def all_states() -> list[AccountState]:
    ds = FixtureDataSource()
    states = []
    for a in ds.list_accounts():
        events = ds.get_usage_events(a.id, since=TODAY - timedelta(days=30))
        all_events = ds.get_usage_events(a.id)
        tickets = ds.get_tickets(a.id)
        nps = ds.get_nps_responses(a.id)
        h = compute_health(a, all_events, tickets, nps, TODAY)
        states.append(AccountState(
            account=a, health=h,
            recent_usage_events=events,
            tickets=tickets, nps_responses=nps,
        ))
    return states


def test_stub_briefing_returns_validated_briefing(all_states: list[AccountState]) -> None:
    for state in all_states:
        b = generate_briefing(state, api_key=None)
        assert isinstance(b, Briefing)
        assert b.account_id == state.account.id
        assert len(b.bullets) == 3
        assert b.generated_by == "stub"


def test_stub_briefing_is_deterministic(all_states: list[AccountState]) -> None:
    """Two runs against the same input must produce identical bullets — the demo's
    screenshots and tests need stable output when no API key is set."""
    state = all_states[0]
    a = generate_briefing(state, api_key=None)
    b = generate_briefing(state, api_key=None)
    assert a.model_dump() == b.model_dump()


def test_every_citation_resolves_to_a_real_fixture_field(all_states: list[AccountState]) -> None:
    """The CLAUDE.md gotcha: the LLM (and the stub) must never cite a signal that
    isn't actually in the input. This is the regression that erodes trust fastest."""
    for state in all_states:
        b = generate_briefing(state, api_key=None)
        ticket_ids = {t.id for t in state.tickets}
        nps_dates = {n.submitted_at.date().isoformat() for n in state.nps_responses}
        for bullet in b.bullets:
            for cite in bullet.citations:
                if cite.startswith("tickets["):
                    tid = cite[len("tickets["):-1]
                    assert tid in ticket_ids, f"{state.account.id} cited unknown ticket {tid}"
                elif cite.startswith("nps["):
                    d = cite[len("nps["):-1]
                    assert d in nps_dates, f"{state.account.id} cited unknown nps date {d}"
                elif cite.startswith("health.signals."):
                    field = cite[len("health.signals."):]
                    assert hasattr(state.health.signals, field), \
                        f"{state.account.id} cited unknown signals field {field}"
                elif cite.startswith("account."):
                    field = cite[len("account."):]
                    assert hasattr(state.account, field), \
                        f"{state.account.id} cited unknown account field {field}"
                elif cite.startswith("usage_events["):
                    pass
                else:
                    pytest.fail(f"{state.account.id} unknown citation form: {cite}")


def test_critical_accounts_briefings_lead_with_remediation(all_states: list[AccountState]) -> None:
    """For the demo to land, critical-bucket briefings should lead with concrete
    remediation language (tickets, usage), not generic platitudes."""
    crits = [s for s in all_states if s.health.bucket == HealthBucket.CRITICAL]
    assert len(crits) >= 2, "demo expects at least 2 critical accounts"
    for state in crits:
        b = generate_briefing(state, api_key=None)
        first_bullet = b.bullets[0].text.lower()
        assert any(word in first_bullet for word in ["ticket", "resolve", "usage", "renewal"]), \
            f"{state.account.id} first bullet too generic: {first_bullet}"


def test_anthropic_path_is_skipped_when_api_key_blank(all_states: list[AccountState]) -> None:
    state = all_states[0]
    b = generate_briefing(state, api_key="")
    assert b.generated_by == "stub"
