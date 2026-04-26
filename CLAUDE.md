# csm-account-pulse — standing brief

> Read this first when working in this repository.

## What this project is

A single-page Streamlit dashboard a CSM opens every Monday to see which of their accounts need attention this week. Aggregates synthetic CRM/usage/ticket data per account, computes a health score, and an LLM produces a 3-bullet "what to focus on this week" briefing per account, with citations to the underlying signals.

This repo is portfolio code — built to be cloned, run, and read by hiring managers and recruiters. See `README.md` for the "What it would take to swap in Salesforce" walkthrough.

## What this project is NOT

- **Not a real CRM integration.** Synthetic JSON fixtures only — no OAuth into Salesforce / HubSpot / Gainsight.
- **Not a CSM workflow / CRUD tool.** Read-only insights; no edit-account, create-task, log-activity, or notes features.
- **Not an action-taking system.** No auto-email, auto-task, auto-Slack, auto-digest. Dashboard surfaces; humans act.
- **Not a real-customer-data system.** Synthetic fixtures only.
- No paid SaaS dependencies beyond the optional Anthropic API call for briefing generation.
- No hosted infra. Local-only execution.

## How to run it

```
pip install -r requirements.txt
streamlit run app.py
pytest
```

Anthropic API key is optional. Without it, briefings render from a deterministic stub so the demo still runs end-to-end.

## Tech stack

- **Language:** Python 3.13
- **Framework:** Streamlit
- **Structured LLM output:** Pydantic + JSON-mode (Anthropic API)
- **Test runner:** pytest
- **Package manager:** pip + `requirements.txt`

## Architecture — the load-bearing rule

All data layer access flows through a `DataSource` interface. Only `FixtureDataSource` is implemented.

```
DataSource (interface)
  ├── list_accounts() -> list[Account]
  ├── get_usage_events(account_id, since) -> list[UsageEvent]
  ├── get_tickets(account_id) -> list[Ticket]
  └── get_nps_responses(account_id) -> list[NpsResponse]
```

**IMPORTANT:** Application code MUST go through `DataSource`. Reading fixtures directly outside `FixtureDataSource` defeats the architecture's claim that Salesforce/HubSpot/Gainsight could be swapped in. See `README.md` for the swap walkthrough.

## Conventions

- Comments: minimal — only when the WHY is non-obvious.
- Pydantic models for every LLM output. Never parse free-text JSON; always JSON-mode + schema validation.
- Prompts live under `prompts/` with a version string at the top. Bump the version on any wording change.

## AI collaboration rules

- **IMPORTANT:** Never `git add -A` or `git add .`. Stage files explicitly.
- **IMPORTANT:** Never `--no-verify`, `--no-gpg-sign`, or `--dangerously-skip-permissions`.
- **IMPORTANT:** Never call paid APIs unilaterally. Use the deterministic stub or confirm first.
- For changes that would touch the `DataSource` interface signature, use plan mode first.
- Don't add new dependencies to `requirements.txt` without confirming.

## Gotchas / known landmines

- **JSON-mode is not a guarantee.** Even with Pydantic + `response_format={"type":"json_object"}`, validation can still fail. Always wrap LLM calls in try/except with a structured fallback.
- **The LLM will invent signals if the prompt isn't constrained.** Briefings must cite only fields present in the input account state — enforce in the prompt and verify in tests.
- **Streamlit's `@st.cache_data` invalidates on input hash, not file content.** When fixtures change, bump a `_cache_version` arg or `streamlit cache clear`.
- **At least 2-3 fixture accounts must be unmistakably at-risk.** Hand-craft them so the LLM has unmissable signals to surface in screenshots.
- **Prompt versioning matters.** Wording changes in `prompts/briefing.md` should bump the version comment AND re-run the regression on synthetic fixtures.
- **The `DataSource` boundary is a portfolio claim, not just a code style.** Bypassing it invalidates the README's swap pitch.

## Glossary

- **CSM** — Customer Success Manager.
- **Health score** — single signal summarizing how at-risk an account is. Composed of usage trend, ticket volume/severity, and NPS.
- **NPS proxy** — synthetic Net Promoter Score response per account.
- **Usage decay** — week-over-week drop in active usage events; a leading churn indicator.
- **Briefing** — the 3-bullet LLM-generated summary per account.
- **Citation** — reference back to the specific fixture field/value the LLM used (e.g. `usage_events[2026-04-12..2026-04-19]`, `tickets[T-1042]`).
- **Account state** — the full per-account data bundle the LLM sees.

## See also

- `@README.md` — public-facing overview and the Salesforce swap walkthrough.
