"""Procedural fixture generator. Run from repo root:

    python scripts/generate_fixtures.py

Produces 50 accounts across data/fixtures/accounts.json + usage_events.json
+ tickets.json + nps_responses.json. The first 3 accounts are hand-crafted
at-risk with deep usage decay + ticket spike + bad NPS in the same window,
so the dashboard always has unmissable signals to surface in screenshots.
The remaining 47 are procedurally generated with realistic mixes.

Deterministic — fixed seed. Edit the constants below to regenerate.
"""

from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path


SEED = 26042026
TODAY = date(2026, 4, 26)
WINDOW_DAYS = 90
WINDOW_START = TODAY - timedelta(days=WINDOW_DAYS)

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = REPO_ROOT / "data" / "fixtures"

INDUSTRIES = [
    "SaaS", "Manufacturing", "Logistics", "Healthcare", "Retail",
    "Finance", "Education", "Media", "Construction", "Energy",
]
CSM_OWNERS = ["Jordan Lee", "Priya Patel", "Marcus Chen", "Elena Rossi", "Sam Okonkwo"]
FEATURES = [
    "dashboard", "exports", "api", "integrations", "alerts",
    "reports", "search", "billing", "user_admin", "audit_log",
]
EVENT_TYPES = ["session_start", "feature_used", "export_generated", "api_call", "report_run"]
TICKET_CATEGORIES = ["billing", "integration", "bug", "performance", "feature_request", "access"]
NAME_PREFIXES = [
    "Acme", "Globex", "Initech", "Umbrella", "Hooli", "Stark", "Wayne", "Wonka", "Pied Piper",
    "Soylent", "Cyberdyne", "Massive Dynamic", "Aperture", "BluthCo", "Vandelay", "Tyrell",
    "Weyland", "Dunder Mifflin", "Prestige Worldwide", "Sterling Cooper", "Los Pollos",
    "Oscorp", "LexCorp", "Gringotts", "Black Mesa", "Veidt", "Rekall", "Spectre", "Strickland",
    "Yoyodyne", "Monarch", "InGen", "Yutani", "Frobozz", "Plumbus", "Macrosoft", "Bigweld",
    "Globo Gym", "Gorch", "Tessier-Ashpool", "Encom", "Genco", "Soylent Green", "Cogswell",
    "Spacely", "Krustyco", "Slate Quarry", "Combine", "Aperture Science", "Praxis",
]
NAME_SUFFIXES = ["Corp", "Industries", "Solutions", "Systems", "Labs", "Group", "Holdings", "LLC"]


def _date_to_dt(d: date, hour: int = 9, minute: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hour, minute)


def _make_account(idx: int, rng: random.Random, name: str | None = None) -> dict:
    plan = rng.choices(
        ["Starter", "Pro", "Enterprise"], weights=[0.3, 0.45, 0.25]
    )[0]
    if plan == "Starter":
        arr, employees = rng.randint(8_000, 24_000), rng.randint(10, 75)
    elif plan == "Pro":
        arr, employees = rng.randint(36_000, 140_000), rng.randint(75, 600)
    else:
        arr, employees = rng.randint(180_000, 600_000), rng.randint(600, 8_000)
    arr = round(arr / 1000) * 1000
    contract_start = TODAY - timedelta(days=rng.randint(180, 720))
    renewal_date = TODAY + timedelta(days=rng.randint(20, 330))
    final_name = name or f"{rng.choice(NAME_PREFIXES)} {rng.choice(NAME_SUFFIXES)}"
    return {
        "id": f"ACC-{idx:03d}",
        "name": final_name,
        "industry": rng.choice(INDUSTRIES),
        "employee_count": employees,
        "plan_tier": plan,
        "arr_usd": arr,
        "contract_start": contract_start.isoformat(),
        "renewal_date": renewal_date.isoformat(),
        "csm_owner": rng.choice(CSM_OWNERS),
        "primary_contact_name": rng.choice([
            "Alex Morgan", "Sasha Kim", "Robin Diaz", "Taylor Nguyen", "Jamie Cohen",
            "Casey Park", "Drew Foster", "Morgan Rivera", "Jordan Wells", "Quinn Hayes",
        ]),
        "primary_contact_title": rng.choice([
            "VP Operations", "Director of Engineering", "Head of Customer Ops",
            "COO", "CTO", "VP Customer Success", "Director of IT", "Head of Analytics",
        ]),
    }


def _baseline_daily_events(plan: str, rng: random.Random) -> int:
    base = {"Starter": 4, "Pro": 14, "Enterprise": 40}[plan]
    return max(1, int(rng.gauss(base, base * 0.25)))


def _gen_usage(
    account: dict,
    rng: random.Random,
    decay_profile: str = "stable",
) -> list[dict]:
    """decay_profile in {stable, slight_growth, slight_decay, steep_decay, near_zero_recent}."""
    events: list[dict] = []
    user_pool = [f"u-{account['id']}-{i}" for i in range(rng.randint(3, 18))]
    daily = _baseline_daily_events(account["plan_tier"], rng)

    for day_idx in range(WINDOW_DAYS):
        d = WINDOW_START + timedelta(days=day_idx)
        progress = day_idx / max(1, WINDOW_DAYS - 1)

        if decay_profile == "stable":
            mult = 1.0 + rng.uniform(-0.15, 0.15)
        elif decay_profile == "slight_growth":
            mult = 0.85 + 0.4 * progress + rng.uniform(-0.1, 0.1)
        elif decay_profile == "slight_decay":
            mult = 1.1 - 0.35 * progress + rng.uniform(-0.1, 0.1)
        elif decay_profile == "steep_decay":
            if progress < 0.65:
                mult = 1.0 + rng.uniform(-0.1, 0.1)
            else:
                local = (progress - 0.65) / 0.35
                mult = max(0.05, 1.0 - 0.95 * local) + rng.uniform(-0.05, 0.05)
        elif decay_profile == "near_zero_recent":
            if progress < 0.55:
                mult = 1.0 + rng.uniform(-0.1, 0.1)
            else:
                mult = max(0.02, 0.15 - 0.13 * (progress - 0.55) / 0.45) + rng.uniform(0, 0.05)
        else:
            mult = 1.0

        if d.weekday() >= 5:
            mult *= 0.35

        n = max(0, int(daily * mult))
        for _ in range(n):
            ts = _date_to_dt(d, hour=rng.randint(7, 19), minute=rng.randint(0, 59))
            events.append({
                "account_id": account["id"],
                "timestamp": ts.isoformat(),
                "event_type": rng.choice(EVENT_TYPES),
                "feature": rng.choice(FEATURES) if rng.random() < 0.7 else None,
                "user_id": rng.choice(user_pool),
            })
    return events


def _gen_tickets(
    account: dict,
    rng: random.Random,
    profile: str = "calm",
    starting_id: int = 1000,
) -> list[dict]:
    """profile in {calm, normal, spike_recent, sustained_critical}."""
    tickets: list[dict] = []

    if profile == "calm":
        count = rng.randint(0, 2)
        severities = ["low", "medium"]
        recent_bias = False
    elif profile == "normal":
        count = rng.randint(2, 6)
        severities = ["low", "low", "medium", "medium", "high"]
        recent_bias = False
    elif profile == "spike_recent":
        count = rng.randint(5, 9)
        severities = ["medium", "high", "high", "critical"]
        recent_bias = True
    elif profile == "sustained_critical":
        count = rng.randint(4, 7)
        severities = ["high", "critical", "critical"]
        recent_bias = True
    else:
        count = 0
        severities = ["low"]
        recent_bias = False

    for i in range(count):
        if recent_bias and rng.random() < 0.7:
            created = TODAY - timedelta(days=rng.randint(0, 25))
        else:
            created = WINDOW_START + timedelta(days=rng.randint(0, WINDOW_DAYS - 1))
        sev = rng.choice(severities)
        if sev in ("low", "medium"):
            resolved = created + timedelta(days=rng.randint(1, 8))
            status = "resolved" if resolved < TODAY else "pending"
        elif sev == "high":
            resolved_offset = rng.randint(3, 20)
            resolved = created + timedelta(days=resolved_offset)
            status = "resolved" if resolved < TODAY and rng.random() < 0.7 else "open"
        else:
            if rng.random() < 0.5:
                resolved = created + timedelta(days=rng.randint(7, 25))
                status = "resolved" if resolved < TODAY else "open"
            else:
                resolved = None
                status = "open"

        tickets.append({
            "id": f"T-{starting_id + i:04d}",
            "account_id": account["id"],
            "created_at": _date_to_dt(created, hour=rng.randint(8, 18)).isoformat(),
            "resolved_at": _date_to_dt(resolved, hour=rng.randint(8, 18)).isoformat() if resolved else None,
            "severity": sev,
            "status": status if resolved is not None else "open",
            "subject": rng.choice([
                "API returning 502 on bulk export",
                "Dashboard timeout under load",
                "SSO login loop after IdP rotation",
                "Webhook signature validation failing",
                "Integration with Slack stopped sending",
                "Report scheduler skipping every other run",
                "User invites going to spam",
                "Audit log missing entries for last week",
                "Charge appeared on wrong invoice",
                "Custom field not syncing to CRM",
            ]),
            "category": rng.choice(TICKET_CATEGORIES),
        })
    return tickets


def _gen_nps(account: dict, rng: random.Random, profile: str = "neutral") -> list[dict]:
    """profile in {promoter, neutral, detractor_recent, sustained_detractor}."""
    responses: list[dict] = []
    # scores list ordered oldest -> newest so the iteration below produces
    # increasing submitted_at timestamps.
    if profile == "promoter":
        scores = [rng.randint(8, 10), rng.randint(8, 10)]
    elif profile == "neutral":
        scores = [rng.randint(6, 9), rng.randint(6, 9)]
    elif profile == "detractor_recent":
        scores = [rng.randint(7, 9), rng.randint(0, 4)]
    elif profile == "sustained_detractor":
        scores = [rng.randint(2, 5), rng.randint(0, 3)]
    else:
        scores = [7]

    n = len(scores)
    for i, score in enumerate(scores):
        # Spread responses across the window from oldest (i=0) to newest (i=n-1).
        offset_days = int((WINDOW_DAYS - 5) * (i + 1) / n) - 5
        offset_days = max(1, min(WINDOW_DAYS - 1, offset_days))
        d = WINDOW_START + timedelta(days=offset_days)
        comment = None
        if score <= 4:
            comment = rng.choice([
                "Constant outages this quarter, considering alternatives.",
                "Support response times have collapsed.",
                "API reliability is unacceptable for our scale.",
                "We have lost trust after the last few incidents.",
            ])
        elif score >= 9:
            comment = rng.choice([
                "Has become core to our weekly operations.",
                "Excellent partnership with the CSM team.",
                "Reliable and the new dashboard saves us hours.",
                None,
            ])
        responses.append({
            "account_id": account["id"],
            "submitted_at": _date_to_dt(d, hour=14).isoformat(),
            "score": score,
            "comment": comment,
        })
    return responses


# Hand-crafted at-risk accounts — first 3 IDs. Their fixtures come from explicit
# profile combinations rather than random rolls so the demo screenshots are stable.
HAND_CRAFTED = [
    {
        "name": "Globex Robotics",
        "industry": "Manufacturing",
        "plan_tier": "Enterprise",
        "arr_usd": 480_000,
        "renewal_in_days": 58,
        "decay": "steep_decay",
        "tickets": "spike_recent",
        "nps": "detractor_recent",
        "primary_contact_name": "Mira Petrov",
        "primary_contact_title": "VP Engineering",
    },
    {
        "name": "Initech Manufacturing",
        "industry": "Manufacturing",
        "plan_tier": "Pro",
        "arr_usd": 96_000,
        "renewal_in_days": 89,
        "decay": "near_zero_recent",
        "tickets": "sustained_critical",
        "nps": "sustained_detractor",
        "primary_contact_name": "Bill Lumbergh",
        "primary_contact_title": "Director of Operations",
    },
    {
        "name": "Hooli Logistics",
        "industry": "Logistics",
        "plan_tier": "Enterprise",
        "arr_usd": 360_000,
        "renewal_in_days": 44,
        "decay": "steep_decay",
        "tickets": "sustained_critical",
        "nps": "sustained_detractor",
        "primary_contact_name": "Gavin Belson",
        "primary_contact_title": "Chief Innovation Officer",
    },
]


def main() -> None:
    rng = random.Random(SEED)
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    accounts: list[dict] = []
    usage: dict[str, list[dict]] = {}
    tickets: dict[str, list[dict]] = {}
    nps: dict[str, list[dict]] = {}

    ticket_counter = 1000

    for i, hc in enumerate(HAND_CRAFTED, start=1):
        acct = _make_account(i, rng, name=hc["name"])
        acct["industry"] = hc["industry"]
        acct["plan_tier"] = hc["plan_tier"]
        acct["arr_usd"] = hc["arr_usd"]
        acct["renewal_date"] = (TODAY + timedelta(days=hc["renewal_in_days"])).isoformat()
        acct["primary_contact_name"] = hc["primary_contact_name"]
        acct["primary_contact_title"] = hc["primary_contact_title"]
        accounts.append(acct)
        usage[acct["id"]] = _gen_usage(acct, rng, decay_profile=hc["decay"])
        t = _gen_tickets(acct, rng, profile=hc["tickets"], starting_id=ticket_counter)
        tickets[acct["id"]] = t
        ticket_counter += len(t) + 5
        nps[acct["id"]] = _gen_nps(acct, rng, profile=hc["nps"])

    decay_profiles = (
        ["slight_decay"] * 6
        + ["stable"] * 28
        + ["slight_growth"] * 10
        + ["steep_decay"] * 3
    )
    ticket_profiles = (
        ["calm"] * 18 + ["normal"] * 24 + ["spike_recent"] * 5
    )
    nps_profiles = (
        ["promoter"] * 14
        + ["neutral"] * 26
        + ["detractor_recent"] * 5
        + ["sustained_detractor"] * 2
    )
    rng.shuffle(decay_profiles)
    rng.shuffle(ticket_profiles)
    rng.shuffle(nps_profiles)

    for j in range(47):
        idx = len(HAND_CRAFTED) + j + 1
        acct = _make_account(idx, rng)
        accounts.append(acct)
        usage[acct["id"]] = _gen_usage(acct, rng, decay_profile=decay_profiles[j])
        t = _gen_tickets(acct, rng, profile=ticket_profiles[j], starting_id=ticket_counter)
        tickets[acct["id"]] = t
        ticket_counter += len(t) + 5
        nps[acct["id"]] = _gen_nps(acct, rng, profile=nps_profiles[j])

    (FIXTURES_DIR / "accounts.json").write_text(json.dumps(accounts, indent=2))
    # usage_events is the heaviest file; keep compact so the repo stays light to clone.
    (FIXTURES_DIR / "usage_events.json").write_text(json.dumps(usage, separators=(",", ":")))
    (FIXTURES_DIR / "tickets.json").write_text(json.dumps(tickets, indent=2))
    (FIXTURES_DIR / "nps_responses.json").write_text(json.dumps(nps, indent=2))

    total_events = sum(len(v) for v in usage.values())
    total_tickets = sum(len(v) for v in tickets.values())
    total_nps = sum(len(v) for v in nps.values())
    print(
        f"Wrote {len(accounts)} accounts, {total_events} usage events, "
        f"{total_tickets} tickets, {total_nps} NPS responses -> {FIXTURES_DIR}"
    )


if __name__ == "__main__":
    main()
