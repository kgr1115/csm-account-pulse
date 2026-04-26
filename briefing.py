"""Briefing generation: Anthropic JSON-mode call validated against the Briefing schema.

If no API key is configured, OR if the live call fails / fails validation, fall back to
a deterministic stub that produces a structurally identical Briefing built from the
HealthScore + signals. The dashboard renders the same regardless — generated_by tells
the user which path produced it.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from models import AccountState, Briefing, BriefingBullet


PROMPT_PATH = Path(__file__).parent / "prompts" / "briefing.md"
DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 800


def _resolve_model() -> str:
    """Read the Anthropic model name from env at call time so tests / .env edits
    take effect without re-importing the module. Falls back to the default snapshot."""
    return os.environ.get("ANTHROPIC_MODEL", "").strip() or DEFAULT_ANTHROPIC_MODEL


# Backwards-compatible alias for code that imports the constant directly.
ANTHROPIC_MODEL = DEFAULT_ANTHROPIC_MODEL

log = logging.getLogger(__name__)


def _load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def _state_to_llm_payload(state: AccountState, today: date | None = None) -> dict:
    """Project the AccountState down to the JSON the LLM sees, keeping it small enough
    that even a heavy account fits in a Haiku context window without trimming context.
    `today` anchors the 7-day window; defaults to date.today() to match the stub path."""
    anchor = today or date.today()
    cutoff_7d = datetime.combine(anchor - timedelta(days=7), datetime.min.time())
    events_last_7d = sum(1 for e in state.recent_usage_events if e.timestamp >= cutoff_7d)
    if state.recent_usage_events:
        window_start = min(e.timestamp.date() for e in state.recent_usage_events)
        window_end = max(e.timestamp.date() for e in state.recent_usage_events)
        events_last_7d_end = window_end
        events_last_7d_start = window_end - timedelta(days=6)
    else:
        window_start = window_end = events_last_7d_start = events_last_7d_end = None
    # Precomputed so the LLM doesn't do its own date arithmetic — eliminates the
    # day-count hallucination class observed in the v2-vs-v3 eval (worst case:
    # "564 days" vs actual 64 for ACC-019). The v4 prompt requires bullets that
    # cite account.renewal_date to copy this value verbatim.
    days_to_renewal = (state.account.renewal_date - anchor).days
    return {
        "account": state.account.model_dump(mode="json"),
        "health": state.health.model_dump(mode="json"),
        "usage_window": {
            "start": window_start,
            "end": window_end,
            "total_events": len(state.recent_usage_events),
            "events_last_7d": events_last_7d,
            "events_last_7d_start": events_last_7d_start,
            "events_last_7d_end": events_last_7d_end,
            "days_to_renewal": days_to_renewal,
        },
        "tickets": [t.model_dump(mode="json") for t in state.tickets],
        "nps_responses": [n.model_dump(mode="json") for n in state.nps_responses],
    }


def _stub_briefing(state: AccountState) -> Briefing:
    """Deterministic, citation-correct fallback. Mirrors the live LLM's output shape
    so the UI is identical regardless of path."""
    a = state.account
    h = state.health
    days_to_renewal = (a.renewal_date - date.today()).days

    bullets: list[BriefingBullet] = []

    if h.signals.open_high_severity_tickets > 0:
        crit_tickets = [t for t in state.tickets if t.severity in ("high", "critical") and t.status in ("open", "pending")]
        cite = [f"tickets[{t.id}]" for t in crit_tickets[:3]] or ["health.signals.open_high_severity_tickets"]
        bullets.append(BriefingBullet(
            text=f"Resolve the {h.signals.open_high_severity_tickets} open high/critical ticket(s) before any renewal conversation.",
            citations=cite,
        ))

    if h.signals.usage_decay_pct >= 20:
        decay_citations = ["health.signals.usage_decay_pct"]
        if state.recent_usage_events:
            window_end = max(e.timestamp.date() for e in state.recent_usage_events)
            window_start = window_end - timedelta(days=6)
            decay_citations.append(
                f"usage_events[{window_start.isoformat()}..{window_end.isoformat()}]"
            )
        bullets.append(BriefingBullet(
            text=f"Usage is down {h.signals.usage_decay_pct:.0f}% week-over-week — investigate which team or workflow stopped logging in.",
            citations=decay_citations,
        ))

    if h.signals.latest_nps_score is not None and h.signals.latest_nps_score <= 6:
        latest_nps = max(state.nps_responses, key=lambda r: r.submitted_at)
        # Name the primary contact in the action when we have one — mirrors the
        # live-path's strongest action-orientation pattern (v2 eval S1/S3 punch).
        nps_cite = [f"nps[{latest_nps.submitted_at.date().isoformat()}]"]
        if a.primary_contact_name:
            nps_text = (
                f"Most recent NPS was {h.signals.latest_nps_score} — schedule a "
                f"discovery call with {a.primary_contact_name} to surface what's behind the dip."
            )
            nps_cite.append("account.primary_contact_name")
        else:
            nps_text = (
                f"Most recent NPS was {h.signals.latest_nps_score} — schedule a "
                "discovery call to surface what's behind the dip."
            )
        bullets.append(BriefingBullet(text=nps_text, citations=nps_cite))

    if 0 <= days_to_renewal <= 90:
        renewal_cite = ["account.renewal_date"]
        if a.primary_contact_name:
            renewal_text = (
                f"Renewal in {days_to_renewal} days ({a.renewal_date.isoformat()}) — "
                f"confirm exec sponsor alignment with {a.primary_contact_name} now, not in week 12."
            )
            renewal_cite.append("account.primary_contact_name")
        else:
            renewal_text = (
                f"Renewal in {days_to_renewal} days ({a.renewal_date.isoformat()}) — "
                "confirm exec sponsor alignment now, not in week 12."
            )
        bullets.append(BriefingBullet(text=renewal_text, citations=renewal_cite))

    if not bullets:
        nps_cite = []
        if state.nps_responses:
            nps_cite = [f"nps[{max(state.nps_responses, key=lambda r: r.submitted_at).submitted_at.date().isoformat()}]"]
        bullets.append(BriefingBullet(
            text="Account is healthy across usage, support, and NPS — use this week for an expansion or advocacy ask.",
            citations=nps_cite or ["health.signals.usage_decay_pct"],
        ))
        bullets.append(BriefingBullet(
            text=f"Renewal is {days_to_renewal} days out — start aligning on a multi-year renewal motion.",
            citations=["account.renewal_date"],
        ))
        bullets.append(BriefingBullet(
            text="Send the quarterly value review on the contract anniversary; healthy accounts churn quietly.",
            citations=["account.contract_start"],
        ))

    bullets = bullets[:3]
    while len(bullets) < 3:
        bullets.append(BriefingBullet(
            text=f"Renewal in {days_to_renewal} days — confirm there are no quiet blockers on the buyer's side.",
            citations=["account.renewal_date"],
        ))

    if h.bucket.value in ("Critical", "At-Risk"):
        headline = f"Renewal at risk — {h.bucket.value.lower()} in week of {date.today().isoformat()}"
    elif h.bucket.value == "Watch":
        headline = f"Watch list: address signals before they compound"
    else:
        headline = "Healthy account — invest the time in expansion"

    return Briefing(
        account_id=a.id,
        headline=headline,
        bullets=bullets,
        generated_by="stub",
    )


def _live_briefing(state: AccountState, api_key: str) -> Briefing | None:
    """Call Anthropic JSON-mode. Returns None on any failure (caller falls back)."""
    try:
        from anthropic import Anthropic
    except ImportError:
        log.warning("anthropic SDK not installed; using stub")
        return None

    client = Anthropic(api_key=api_key)
    prompt = _load_prompt()
    payload = _state_to_llm_payload(state)

    try:
        resp = client.messages.create(
            model=_resolve_model(),
            max_tokens=MAX_TOKENS,
            system=prompt,
            messages=[{
                "role": "user",
                "content": (
                    "Here is the account JSON. Return ONLY the briefing JSON object as specified.\n\n"
                    + json.dumps(payload, default=str)
                ),
            }],
        )
        text = "".join(b.text for b in resp.content if hasattr(b, "text"))
        # Strip optional code fences the model sometimes adds despite instructions.
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.rsplit("```", 1)[0].strip()
        raw = json.loads(text)
        raw["generated_by"] = "anthropic"
        briefing = Briefing.model_validate(raw)
        if briefing.account_id != state.account.id:
            log.warning(
                "LLM returned account_id %s for state %s; falling back to stub",
                briefing.account_id, state.account.id,
            )
            return None
        return briefing
    except (json.JSONDecodeError, ValidationError) as e:
        log.warning("LLM output failed validation, falling back to stub: %s", e)
        return None
    except Exception as e:
        log.warning("LLM call failed, falling back to stub: %s", e)
        return None


def generate_briefing(state: AccountState, api_key: str | None = None) -> Briefing:
    """Public entry point. api_key=None forces stub; otherwise tries live then falls back."""
    key = api_key if api_key is not None else os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        result = _live_briefing(state, key)
        if result is not None:
            return result
    return _stub_briefing(state)
