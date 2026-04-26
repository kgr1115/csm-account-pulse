"""Briefing tests. The two high-leverage invariants:
  1. The stub path produces structurally-valid Briefings without an API key
     (this is what runs on a recruiter's laptop with no key set).
  2. Every citation in every briefing resolves to a real fixture field
     (this is the "the LLM will invent signals" gotcha from CLAUDE.md).

The live-path tests use a mocked Anthropic client (CLAUDE.md forbids unilateral
paid API calls). The mock simulates the SDK shape `_live_briefing` reads from
(resp.content[i].text), so a regression in JSON parsing, code-fence stripping,
or fallback handling is caught without spending a token.
"""

from __future__ import annotations

import json
import sys
import types
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
    from datetime import date as _date
    for state in all_states:
        b = generate_briefing(state, api_key=None)
        ticket_ids = {t.id for t in state.tickets}
        nps_dates = {n.submitted_at.date().isoformat() for n in state.nps_responses}
        usage_dates = {e.timestamp.date() for e in state.recent_usage_events}
        usage_min = min(usage_dates) if usage_dates else None
        usage_max = max(usage_dates) if usage_dates else None
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
                    inner = cite[len("usage_events["):-1]
                    assert ".." in inner, \
                        f"{state.account.id} usage_events citation missing range: {cite}"
                    start_s, end_s = inner.split("..", 1)
                    try:
                        start_d = _date.fromisoformat(start_s)
                        end_d = _date.fromisoformat(end_s)
                    except ValueError:
                        pytest.fail(f"{state.account.id} usage_events endpoints not ISO dates: {cite}")
                    assert start_d <= end_d, \
                        f"{state.account.id} usage_events range inverted: {cite}"
                    assert usage_min is not None, \
                        f"{state.account.id} cited usage_events but has no recent usage events: {cite}"
                    assert usage_min <= start_d <= usage_max, \
                        f"{state.account.id} usage_events start {start_d} outside window [{usage_min},{usage_max}]"
                    assert usage_min <= end_d <= usage_max, \
                        f"{state.account.id} usage_events end {end_d} outside window [{usage_min},{usage_max}]"
                else:
                    pytest.fail(f"{state.account.id} unknown citation form: {cite}")


def test_renewal_prose_matches_cited_renewal_date(all_states: list[AccountState]) -> None:
    """Bullets that cite `account.renewal_date` must not hallucinate the distance.

    The eval (evals/results/v1_vs_v2.md) caught both v1 and v2 emitting "renewal in
    14 months" / "renewal in 424 days" for ACC-001 (actual: 58 days). The citation
    is valid (account.renewal_date is real); the prose is not. The citation
    validator can't catch this — it only checks that fields exist. This test
    closes that gap by walking any number+unit phrase ("N days", "N months",
    "N weeks", "N years") in a bullet that cites account.renewal_date and
    verifying the value is consistent with the actual fixture distance.

    Stub-side this passes day one — the stub emits "Renewal in {days_to_renewal}
    days" exactly. Live-path is governed by the v3+ prompt rule that forbids
    months/weeks/years approximations on this citation.
    """
    import re

    pattern = re.compile(r"(\d+)\s*(day|days|week|weeks|month|months|year|years)\b", re.IGNORECASE)
    # The stub computes days_to_renewal against date.today() (real today), not the
    # test's TODAY constant. Match that behavior so the test isn't time-coupled —
    # it has to keep passing on any future calendar day, not just 2026-04-26.
    today_for_stub = date.today()

    for state in all_states:
        b = generate_briefing(state, api_key=None)
        actual_days = (state.account.renewal_date - today_for_stub).days
        for bullet in b.bullets:
            if "account.renewal_date" not in bullet.citations:
                continue
            for match in pattern.finditer(bullet.text):
                n = int(match.group(1))
                unit = match.group(2).lower().rstrip("s")
                if unit == "day":
                    assert n == actual_days, (
                        f"{state.account.id} bullet says '{n} {unit}s' but actual "
                        f"days_to_renewal={actual_days}: {bullet.text!r}"
                    )
                elif unit == "week":
                    expected = round(actual_days / 7)
                    assert abs(n - expected) <= 1, (
                        f"{state.account.id} bullet says '{n} {unit}s' but actual "
                        f"weeks~={expected} (days={actual_days}): {bullet.text!r}"
                    )
                elif unit == "month":
                    expected = round(actual_days / 30)
                    assert abs(n - expected) <= 1, (
                        f"{state.account.id} bullet says '{n} {unit}s' but actual "
                        f"months~={expected} (days={actual_days}): {bullet.text!r}"
                    )
                elif unit == "year":
                    expected = round(actual_days / 365)
                    assert abs(n - expected) <= 1, (
                        f"{state.account.id} bullet says '{n} {unit}s' but actual "
                        f"years~={expected} (days={actual_days}): {bullet.text!r}"
                    )


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


def test_state_to_llm_payload_runs_without_api_key(all_states: list[AccountState]) -> None:
    """_state_to_llm_payload only runs in the live path, so a NameError or
    bad import here would only manifest on a real Anthropic call. Covering the
    pure-function path keeps the live-path import surface honest."""
    from briefing import _state_to_llm_payload
    state = all_states[0]
    payload = _state_to_llm_payload(state, today=TODAY)
    assert payload["account"]["id"] == state.account.id
    assert "usage_window" in payload
    uw = payload["usage_window"]
    assert uw["total_events"] == len(state.recent_usage_events)
    assert uw["events_last_7d"] >= 0
    assert uw["events_last_7d"] <= uw["total_events"]
    # New in prompt v2: explicit 7-day endpoints so the LLM doesn't have to infer a range.
    assert uw["events_last_7d_start"] is not None
    assert uw["events_last_7d_end"] is not None
    assert uw["events_last_7d_end"] == uw["end"]
    assert (uw["events_last_7d_end"] - uw["events_last_7d_start"]).days == 6

    payload_default_today = _state_to_llm_payload(state)
    assert "usage_window" in payload_default_today

    empty_state = AccountState(
        account=state.account,
        health=state.health,
        recent_usage_events=[],
        tickets=state.tickets,
        nps_responses=state.nps_responses,
    )
    empty_payload = _state_to_llm_payload(empty_state, today=TODAY)
    assert empty_payload["usage_window"]["total_events"] == 0
    assert empty_payload["usage_window"]["events_last_7d"] == 0
    assert empty_payload["usage_window"]["start"] is None
    assert empty_payload["usage_window"]["end"] is None
    assert empty_payload["usage_window"]["events_last_7d_start"] is None
    assert empty_payload["usage_window"]["events_last_7d_end"] is None


# ---------------------------------------------------------------------------
# Live-path tests with a mocked Anthropic client.
#
# `briefing._live_briefing` lazy-imports `from anthropic import Anthropic`,
# so we install a fake `anthropic` module in sys.modules before generate_briefing
# is called. The fake client returns a response whose .content[0].text holds the
# JSON we want to test against. CLAUDE.md forbids unilateral paid API calls; this
# pattern lets us assert the live branch end-to-end without one.
# ---------------------------------------------------------------------------


class _FakeTextBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.content = [_FakeTextBlock(text)]


class _FakeMessages:
    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list[dict] = []

    def create(self, **kwargs: object) -> _FakeResponse:
        self.calls.append(kwargs)
        return _FakeResponse(self._text)


class _FakeAnthropic:
    last_instance: "_FakeAnthropic | None" = None

    def __init__(self, api_key: str | None = None, **kwargs: object) -> None:
        self.api_key = api_key
        self.messages = _FakeMessages(self.__class__._next_text)
        _FakeAnthropic.last_instance = self


def _install_fake_anthropic(monkeypatch: pytest.MonkeyPatch, response_text: str) -> None:
    _FakeAnthropic._next_text = response_text  # type: ignore[attr-defined]
    fake_module = types.ModuleType("anthropic")
    fake_module.Anthropic = _FakeAnthropic  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)


def _valid_briefing_json(state: AccountState) -> str:
    return json.dumps({
        "account_id": state.account.id,
        "headline": "Test headline for the week",
        "bullets": [
            {"text": "Bullet one.", "citations": ["account.renewal_date"]},
            {"text": "Bullet two.", "citations": ["account.renewal_date"]},
            {"text": "Bullet three.", "citations": ["account.renewal_date"]},
        ],
    })


def test_live_path_happy(all_states: list[AccountState], monkeypatch: pytest.MonkeyPatch) -> None:
    state = all_states[0]
    _install_fake_anthropic(monkeypatch, _valid_briefing_json(state))
    b = generate_briefing(state, api_key="sk-test-fake")
    assert b.generated_by == "anthropic"
    assert b.account_id == state.account.id
    assert len(b.bullets) == 3


def test_live_path_strips_json_code_fence(all_states: list[AccountState], monkeypatch: pytest.MonkeyPatch) -> None:
    state = all_states[0]
    fenced = "```json\n" + _valid_briefing_json(state) + "\n```"
    _install_fake_anthropic(monkeypatch, fenced)
    b = generate_briefing(state, api_key="sk-test-fake")
    assert b.generated_by == "anthropic"


def test_live_path_strips_bare_code_fence(all_states: list[AccountState], monkeypatch: pytest.MonkeyPatch) -> None:
    state = all_states[0]
    fenced = "```\n" + _valid_briefing_json(state) + "\n```"
    _install_fake_anthropic(monkeypatch, fenced)
    b = generate_briefing(state, api_key="sk-test-fake")
    assert b.generated_by == "anthropic"


def test_live_path_falls_back_on_malformed_json(all_states: list[AccountState], monkeypatch: pytest.MonkeyPatch) -> None:
    state = all_states[0]
    _install_fake_anthropic(monkeypatch, "this is not json at all")
    b = generate_briefing(state, api_key="sk-test-fake")
    assert b.generated_by == "stub"


def test_live_path_falls_back_on_validation_error(all_states: list[AccountState], monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM returns valid JSON but only 2 bullets — Briefing schema requires exactly 3."""
    state = all_states[0]
    bad = json.dumps({
        "account_id": state.account.id,
        "headline": "Two bullets only",
        "bullets": [
            {"text": "One.", "citations": ["account.renewal_date"]},
            {"text": "Two.", "citations": ["account.renewal_date"]},
        ],
    })
    _install_fake_anthropic(monkeypatch, bad)
    b = generate_briefing(state, api_key="sk-test-fake")
    assert b.generated_by == "stub"


def test_live_path_falls_back_on_account_id_mismatch(
    all_states: list[AccountState], monkeypatch: pytest.MonkeyPatch
) -> None:
    """LLM returns a Briefing for a different account than we asked about — must
    fall back to stub so the dashboard never shows wrong-account briefings."""
    state = all_states[0]
    other = all_states[1]
    assert state.account.id != other.account.id
    wrong = json.dumps({
        "account_id": other.account.id,  # mismatched on purpose
        "headline": "Briefing for the wrong account",
        "bullets": [
            {"text": "One.", "citations": ["account.renewal_date"]},
            {"text": "Two.", "citations": ["account.renewal_date"]},
            {"text": "Three.", "citations": ["account.renewal_date"]},
        ],
    })
    _install_fake_anthropic(monkeypatch, wrong)
    b = generate_briefing(state, api_key="sk-test-fake")
    assert b.generated_by == "stub"
    assert b.account_id == state.account.id


def test_resolve_model_uses_env_var_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from briefing import DEFAULT_ANTHROPIC_MODEL, _resolve_model
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    assert _resolve_model() == DEFAULT_ANTHROPIC_MODEL
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")
    assert _resolve_model() == "claude-sonnet-4-5-20250929"
    monkeypatch.setenv("ANTHROPIC_MODEL", "  ")
    assert _resolve_model() == DEFAULT_ANTHROPIC_MODEL


def test_live_path_falls_back_when_anthropic_sdk_missing(
    all_states: list[AccountState], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulate the SDK not being installed — the lazy import inside _live_briefing
    must catch ImportError and fall back to stub, not crash the dashboard."""
    state = all_states[0]
    # Block the import: setting the entry to None makes `import anthropic` raise ImportError.
    monkeypatch.setitem(sys.modules, "anthropic", None)
    b = generate_briefing(state, api_key="sk-test-fake")
    assert b.generated_by == "stub"
