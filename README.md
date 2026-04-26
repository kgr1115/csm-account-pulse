# csm-account-pulse

A single-page Streamlit dashboard a CSM opens every Monday to see which of their accounts need attention this week. Aggregates synthetic CRM/usage/ticket data per account, computes a health score, and an LLM generates a 3-bullet "what to focus on this week" briefing per account, with citations to the underlying signals.

## Who this is for

Customer Success Managers — and the people hiring them. Built as a portfolio piece illustrating the kind of internal AI tool an AI Implementation Specialist would deploy at a non-AI company. Shows account-level data thinking, structured LLM output, prompt versioning, and CSM workflow understanding.

## Quick start

```bash
git clone <this-repo>
cd csm-account-pulse
pip install -r requirements.txt
python -m streamlit run app.py
```

`pytest` runs the test suite. Anthropic API key is optional — without one, the dashboard renders briefings from a deterministic stub so the demo runs end-to-end. Copy `.env.example` to `.env` and paste your key there to switch on the live model.

## What's inside

- **`app.py`** — the Streamlit dashboard. One page; opens on accounts ranked by health bucket then score.
- **`models.py`** — Pydantic models for every entity (Account, UsageEvent, Ticket, NpsResponse) and for the validated `Briefing` output. Each `BriefingBullet` is required to carry at least one citation.
- **`datasource.py`** — the `DataSource` interface and `FixtureDataSource`, the only implementation. All reads flow through here.
- **`health.py`** — composes usage decay + ticket volume + NPS into a 0–100 score with categorical bucket and per-signal breakdown.
- **`briefing.py`** — the LLM call. Pydantic + JSON-mode against Anthropic. Falls back to a deterministic stub when the API key is unset or validation fails — both paths produce the same shape.
- **`prompts/briefing.md`** — versioned prompt for briefing generation. Bumped on any wording change.
- **`scripts/generate_fixtures.py`** — deterministic fixture generator. Three accounts (Globex, Initech, Hooli) are hand-crafted to land in the Critical bucket so the demo has unmissable signals.
- **`data/fixtures/`** — 50 accounts × 90 days of usage events, plus tickets and NPS responses.
- **`tests/`** — DataSource contract, health-score boundaries, and a regression that every citation in every briefing resolves to a real fixture field.

## Architecture — the load-bearing rule

Every data read flows through a `DataSource` interface:

```python
class DataSource(Protocol):
    def list_accounts(self) -> list[Account]: ...
    def get_usage_events(self, account_id: str, since: date) -> list[UsageEvent]: ...
    def get_tickets(self, account_id: str) -> list[Ticket]: ...
    def get_nps_responses(self, account_id: str) -> list[NpsResponse]: ...
```

`FixtureDataSource` is the only concrete implementation. The interface is the load-bearing claim — it's what makes the next section credible.

## What it would take to swap in Salesforce

The fixtures are not the architecture; the interface is. Replacing synthetic data with a real CRM is a localized change:

1. **New implementation: `SalesforceDataSource(DataSource)`** in `datasource_salesforce.py` (or wherever you keep adapters).
   - `list_accounts()` → `SOQL: SELECT Id, Name, ... FROM Account WHERE OwnerId = :csm_id`
   - `get_usage_events(account_id, since)` → either a custom object query (`SELECT ... FROM Usage_Event__c WHERE Account__c = :account_id AND CreatedDate >= :since`) or a Snowflake/Redshift query if usage telemetry lives in the warehouse rather than Salesforce itself.
   - `get_tickets(account_id)` → `SELECT Id, Subject, Priority, Status, CreatedDate FROM Case WHERE AccountId = :account_id`
   - `get_nps_responses(account_id)` → wherever NPS lives (often a separate vendor like Qualtrics or Delighted; another adapter, same interface).

2. **Auth:** OAuth 2.0 web server flow against Salesforce. Refresh token stored in OS keyring (e.g. `keyring.set_password("csm-account-pulse", "salesforce-refresh", token)`); never on disk. Anthropic API key already follows the same pattern via `.env`.

3. **Caching:** real CRM calls are slow and rate-limited. Wrap `SalesforceDataSource` methods in `@functools.lru_cache` (in-memory) or `diskcache` (per-session) keyed on `(account_id, since)`. Streamlit's `@st.cache_data` continues to wrap the dashboard-level calls.

4. **Config wiring:** in `app.py`, replace
   ```python
   data_source = FixtureDataSource("data/fixtures/")
   ```
   with
   ```python
   data_source = SalesforceDataSource(
       client_id=os.environ["SF_CLIENT_ID"],
       refresh_token=keyring.get_password("csm-account-pulse", "salesforce-refresh"),
   )
   ```
   No other application code changes. The dashboard, health score, and briefing call sites all already speak `DataSource`.

5. **Health-score & briefing tuning:** synthetic fixtures are tuned to make the demo legible. Real Salesforce data will have different distributions (more noise, fewer pure at-risk signals, more partial nulls). The health-score weights and the briefing prompt would need a calibration pass against real data — a few days of work, not a rewrite.

6. **Out of scope (deliberately):** writing back to Salesforce. This dashboard is read-only; the architecture has no `DataSink` symmetric to `DataSource`. Adding actions (auto-task creation, etc.) is a separate scope conversation, not an integration step.

The total effort estimate: ~3-5 days for a single CRM, most of it in OAuth setup, schema mapping, and health-score recalibration. The interface boundary is what makes that estimate small instead of "weeks."

## Tech stack

- Python 3.13
- Streamlit (dashboard)
- Pydantic + Anthropic API JSON-mode (structured LLM output)
- pytest

## License

MIT
