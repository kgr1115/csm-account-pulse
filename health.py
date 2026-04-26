"""Health score: a single 0–100 number per account, with categorical bucket and signal breakdown.

Composed of three subsignals:
  * usage_decay_pct — last-7-days events vs prior-7-days
  * ticket pressure — open high/critical count + 30-day total
  * nps proxy — latest score, plus detractor count over 90 days

The score is intentionally interpretable, not ML. A CSM should be able to
read the rationale and immediately understand which signal triggered the bucket.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from models import (
    Account,
    HealthBucket,
    HealthScore,
    HealthSignals,
    NpsResponse,
    Ticket,
    UsageEvent,
)


def _events_in_window(events: list[UsageEvent], start: date, end: date) -> int:
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.min.time())
    return sum(1 for e in events if start_dt <= e.timestamp < end_dt)


def usage_decay_pct(events: list[UsageEvent], today: date) -> float:
    """Positive = decay (last week dropped vs the week before). 0 if no prior baseline."""
    last_week = _events_in_window(events, today - timedelta(days=7), today)
    prior_week = _events_in_window(events, today - timedelta(days=14), today - timedelta(days=7))
    if prior_week == 0:
        return 0.0
    return round((prior_week - last_week) / prior_week * 100, 1)


def ticket_pressure(tickets: list[Ticket], today: date) -> tuple[int, int]:
    """Returns (open_high_severity_count, total_30d_count)."""
    cutoff_30 = datetime.combine(today - timedelta(days=30), datetime.min.time())
    open_high = sum(
        1 for t in tickets
        if t.severity in ("high", "critical") and t.status in ("open", "pending")
    )
    total_30 = sum(1 for t in tickets if t.created_at >= cutoff_30)
    return open_high, total_30


def nps_signals(responses: list[NpsResponse], today: date) -> tuple[int | None, int]:
    """Returns (latest_score, detractor_count_in_last_90_days)."""
    cutoff_90 = datetime.combine(today - timedelta(days=90), datetime.min.time())
    in_window = [r for r in responses if r.submitted_at >= cutoff_90]
    latest = max(responses, key=lambda r: r.submitted_at) if responses else None
    detractors = sum(1 for r in in_window if r.bucket == "detractor")
    return (latest.score if latest else None), detractors


def compute_health(
    account: Account,
    events: list[UsageEvent],
    tickets: list[Ticket],
    nps: list[NpsResponse],
    today: date,
) -> HealthScore:
    decay = usage_decay_pct(events, today)
    open_high, total_30 = ticket_pressure(tickets, today)
    latest_nps, detractor_count = nps_signals(nps, today)

    score = 100

    if decay >= 70:
        score -= 35
    elif decay >= 40:
        score -= 22
    elif decay >= 20:
        score -= 12
    elif decay <= -20:
        score += 5

    score -= min(40, open_high * 12)
    if total_30 >= 6:
        score -= 8
    elif total_30 >= 3:
        score -= 4

    if latest_nps is not None:
        if latest_nps <= 3:
            score -= 25
        elif latest_nps <= 6:
            score -= 12
        elif latest_nps >= 9:
            score += 4
    if detractor_count >= 2:
        score -= 8

    score = max(0, min(100, score))

    if score >= 80:
        bucket = HealthBucket.HEALTHY
    elif score >= 60:
        bucket = HealthBucket.WATCH
    elif score >= 35:
        bucket = HealthBucket.AT_RISK
    else:
        bucket = HealthBucket.CRITICAL

    drivers: list[str] = []
    if decay >= 40:
        drivers.append(f"usage down {decay:.0f}% week-over-week")
    elif decay >= 20:
        drivers.append(f"usage softening ({decay:.0f}% WoW)")
    if open_high:
        drivers.append(f"{open_high} open high/critical ticket{'s' if open_high != 1 else ''}")
    if latest_nps is not None and latest_nps <= 4:
        drivers.append(f"NPS detractor (latest score {latest_nps})")
    elif latest_nps is not None and latest_nps <= 6:
        drivers.append(f"NPS softening (latest score {latest_nps})")

    if not drivers:
        if bucket == HealthBucket.HEALTHY:
            rationale = "All signals healthy across usage, support, and NPS."
        else:
            rationale = "No single dominant signal — composite of mild dips."
    else:
        rationale = "; ".join(drivers).capitalize() + "."

    return HealthScore(
        account_id=account.id,
        score=score,
        bucket=bucket,
        signals=HealthSignals(
            usage_decay_pct=decay,
            open_high_severity_tickets=open_high,
            ticket_volume_30d=total_30,
            latest_nps_score=latest_nps,
            detractor_count_90d=detractor_count,
        ),
        rationale=rationale,
    )
