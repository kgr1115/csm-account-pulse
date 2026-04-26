"""Health score tests. Pin the bucket boundaries and signal contributions so a tweak
to the scoring formula doesn't silently move accounts out of the at-risk bucket
the README screenshots depend on."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from datasource import FixtureDataSource
from health import compute_health, usage_decay_pct
from models import Account, HealthBucket, NpsResponse, Ticket, UsageEvent


TODAY = date(2026, 4, 26)


def _account(id: str = "ACC-X") -> Account:
    return Account(
        id=id,
        name="Test Co",
        industry="SaaS",
        employee_count=100,
        plan_tier="Pro",
        arr_usd=50000,
        contract_start=date(2025, 1, 1),
        renewal_date=date(2026, 12, 1),
        csm_owner="Test CSM",
        primary_contact_name="Test Contact",
        primary_contact_title="VP Test",
    )


def _events(account_id: str, day_counts: dict[date, int]) -> list[UsageEvent]:
    out: list[UsageEvent] = []
    for d, count in day_counts.items():
        for _ in range(count):
            out.append(UsageEvent(
                account_id=account_id,
                timestamp=datetime.combine(d, datetime.min.time()),
                event_type="session_start",
                feature="dashboard",
                user_id="u-1",
            ))
    return out


def test_usage_decay_pct_no_prior_baseline_returns_zero() -> None:
    assert usage_decay_pct([], TODAY) == 0.0


def test_usage_decay_pct_50_percent_drop() -> None:
    prior = {TODAY - timedelta(days=10): 20}
    last = {TODAY - timedelta(days=3): 10}
    events = _events("ACC-X", {**prior, **last})
    assert usage_decay_pct(events, TODAY) == 50.0


def test_compute_health_healthy_when_all_signals_calm() -> None:
    a = _account()
    events = _events(a.id, {TODAY - timedelta(days=i): 10 for i in range(1, 14)})
    nps = [NpsResponse(account_id=a.id, submitted_at=datetime(2026, 4, 1, 12), score=9)]
    h = compute_health(a, events, [], nps, TODAY)
    assert h.bucket == HealthBucket.HEALTHY
    assert h.score >= 80


def test_compute_health_critical_when_all_signals_bad() -> None:
    a = _account()
    events = _events(a.id, {
        TODAY - timedelta(days=10): 30,
        TODAY - timedelta(days=3): 1,
    })
    tickets = [
        Ticket(
            id=f"T-{i:04d}",
            account_id=a.id,
            created_at=datetime(2026, 4, 20, 12),
            severity="critical",
            status="open",
            subject="API down",
            category="bug",
        )
        for i in range(3)
    ]
    nps = [NpsResponse(account_id=a.id, submitted_at=datetime(2026, 4, 10, 12), score=1)]
    h = compute_health(a, events, tickets, nps, TODAY)
    assert h.bucket == HealthBucket.CRITICAL
    assert h.score <= 35


def test_three_handcrafted_accounts_are_in_critical_bucket() -> None:
    """The README's whole pitch depends on at least 2-3 unmistakably at-risk accounts.
    If this regresses, screenshots stop showing actionable signals."""
    ds = FixtureDataSource()
    handcrafted = ["ACC-001", "ACC-002", "ACC-003"]
    for aid in handcrafted:
        a = next(x for x in ds.list_accounts() if x.id == aid)
        h = compute_health(
            a,
            ds.get_usage_events(a.id),
            ds.get_tickets(a.id),
            ds.get_nps_responses(a.id),
            TODAY,
        )
        assert h.bucket == HealthBucket.CRITICAL, f"{aid} expected Critical, got {h.bucket}"


def test_signals_breakdown_reflects_inputs() -> None:
    a = _account()
    tickets = [
        Ticket(id="T-1", account_id=a.id, created_at=datetime(2026, 4, 20, 12),
               severity="high", status="open", subject="x", category="bug"),
        Ticket(id="T-2", account_id=a.id, created_at=datetime(2026, 4, 21, 12),
               severity="critical", status="pending", subject="y", category="bug"),
        Ticket(id="T-3", account_id=a.id, created_at=datetime(2026, 4, 22, 12),
               severity="low", status="open", subject="z", category="bug"),
    ]
    h = compute_health(a, [], tickets, [], TODAY)
    assert h.signals.open_high_severity_tickets == 2
    assert h.signals.ticket_volume_30d == 3
