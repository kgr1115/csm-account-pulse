"""Pydantic models for the entire data shape — fixtures, scoring, and LLM output.

The DataSource interface returns these. The briefing LLM call validates against Briefing.
Both consumers and the LLM see the same schema; that single source of truth is load-bearing.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


PlanTier = Literal["Starter", "Pro", "Enterprise"]
TicketSeverity = Literal["low", "medium", "high", "critical"]
TicketStatus = Literal["open", "pending", "resolved"]


class Account(BaseModel):
    id: str
    name: str
    industry: str
    employee_count: int
    plan_tier: PlanTier
    arr_usd: int = Field(description="Annual recurring revenue in US dollars")
    contract_start: date
    renewal_date: date
    csm_owner: str
    primary_contact_name: str
    primary_contact_title: str


class UsageEvent(BaseModel):
    account_id: str
    timestamp: datetime
    event_type: str = Field(description="e.g. session_start, feature_used, export_generated")
    feature: str | None = None
    user_id: str


class Ticket(BaseModel):
    id: str
    account_id: str
    created_at: datetime
    resolved_at: datetime | None = None
    severity: TicketSeverity
    status: TicketStatus
    subject: str
    category: str


class NpsResponse(BaseModel):
    account_id: str
    submitted_at: datetime
    score: int = Field(ge=0, le=10)
    comment: str | None = None

    @property
    def bucket(self) -> Literal["promoter", "passive", "detractor"]:
        if self.score >= 9:
            return "promoter"
        if self.score >= 7:
            return "passive"
        return "detractor"


class HealthBucket(str, Enum):
    HEALTHY = "Healthy"
    WATCH = "Watch"
    AT_RISK = "At-Risk"
    CRITICAL = "Critical"


class HealthSignals(BaseModel):
    """Per-signal numeric breakdown so the UI can show the why behind the score."""
    usage_decay_pct: float = Field(description="Week-over-week % drop in events; positive = decay")
    open_high_severity_tickets: int
    ticket_volume_30d: int
    latest_nps_score: int | None
    detractor_count_90d: int


class HealthScore(BaseModel):
    account_id: str
    score: int = Field(ge=0, le=100, description="Higher = healthier")
    bucket: HealthBucket
    signals: HealthSignals
    rationale: str = Field(description="One-line plain-English summary of why this bucket")


class AccountState(BaseModel):
    """Bundle the briefing LLM sees. The LLM may only cite fields present here."""
    account: Account
    health: HealthScore
    recent_usage_events: list[UsageEvent]
    tickets: list[Ticket]
    nps_responses: list[NpsResponse]


class BriefingBullet(BaseModel):
    text: str = Field(description="One sentence, action-oriented")
    citations: list[str] = Field(
        description=(
            "Identifiers of fixture fields the bullet rests on, "
            "e.g. 'tickets[T-1042]', 'usage_events[2026-04-12..2026-04-19]', 'nps[2026-03-30]'"
        )
    )

    @field_validator("citations")
    @classmethod
    def _at_least_one_citation(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("Every bullet must cite at least one signal")
        return v


class Briefing(BaseModel):
    """Validated LLM output. JSON-mode + this schema is the contract."""
    account_id: str
    headline: str = Field(description="A 6–10 word framing of the week ahead")
    bullets: list[BriefingBullet] = Field(min_length=3, max_length=3)
    generated_by: Literal["anthropic", "stub"] = Field(
        description="Which path produced this briefing — for transparency in the UI"
    )
