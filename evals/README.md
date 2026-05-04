# Briefing prompt evals

This directory is the receipt for "the prompt is bumped on any wording change." Every prompt version in `prompts/briefing.md` ships with a result file produced by `scripts/run_eval.py` against a held-out scenario set, plus a comparison file grading the bump against the prior version. The grading rubric and held-out scenarios are documented in [`methodology.md`](methodology.md).

## The held-out scenario set

Twelve fixture accounts pinned in [`scenarios.json`](scenarios.json) span the dashboard's full output range. S1–S5 are drawn from the seed-generated fixture set (multi-signal critical, single-signal critical / abandonment, quiet at-risk, healthy with renewal soon, pure healthy). S6–S12 are hand-crafted accounts in the reserved ACC-051..ACC-070 range covering shapes the seed doesn't produce: no NPS data at all (S6), high ticket volume with zero usage decay (S7), long renewal horizon all green (S8), renewal in 7 days healthy (S9), mixed severity tickets none open H/C (S10), single NPS detractor (S11), and new account with thin window (S12). See [`methodology.md`](methodology.md) for the full table and the scenario expansion policy.

## Grading rubric

Each (scenario, prompt-version) pair is graded across five dimensions on a 1–5 scale: citation validity (objective), schema validity (objective), bullet count (objective), specificity (subjective), and action orientation (subjective). A bump is defensible if the new version ties or beats the prior on every dimension AND wins on at least one. Full criteria in [`methodology.md`](methodology.md).

## The v1 → v5 journey

Each bump targets a specific failure mode surfaced by the prior eval. The pattern: bump → eval → identify next-iteration target → bump again. The result files commit alongside the prompt change.

| Version | What it added | What it fixed | Result files |
|---|---|---|---|
| **v1** | Baseline prompt. Citation grammar (5 forms), 3-bullet schema, headline. | — | [`results/v1.md`](results/v1.md) |
| **v2** | Surfaced explicit `events_last_7d_*` window endpoints to the LLM. Citation rule for trailing-7-day usage. | v1's specificity / action-orientation slack on the abandonment scenario (S2) and pure-healthy scenario (S5). | [`results/v2.md`](results/v2.md), [`results/v1_vs_v2.md`](results/v1_vs_v2.md) |
| **v3** | Citation rule forbidding month/week/year approximations on `account.renewal_date`. New stub-side regression test (`test_renewal_prose_matches_cited_renewal_date`). | The `"renewal in 14 months"` / `"renewal in 424 days"` hallucinations both v1 and v2 produced for ACC-001 (actual: 58 days). | [`results/v3.md`](results/v3.md), [`results/v2_vs_v3.md`](results/v2_vs_v3.md) |
| **v4** | Precomputed `usage_window.days_to_renewal` in the LLM payload. Prompt rule requiring the integer be copied verbatim. Named-contact preference. Live-path renewal-prose check added to `run_eval.py`. | v3's day-count hallucinations (the worst was ACC-019 saying `"564 days"` vs actual 64). v3's stub-only regression test couldn't see this — the live-path check in `run_eval.py` now does. | [`results/v4.md`](results/v4.md), [`results/v3_vs_v4.md`](results/v3_vs_v4.md) |
| **v5** | `usage_window.<field>` added as a sixth allowed citation form. Test validator extended to recognize it (single source of truth via `_state_to_llm_payload`). | The citation-grammar gap surfaced in v4: live outputs cited `usage_window.days_to_renewal` because the prompt told them to use the value, but the formal grammar didn't permit that citation form. Methodology gap, not a correctness regression. | (no v5 eval yet — purely additive prompt + test change) |

Archived prompt versions live in [`old_prompts/`](old_prompts/) so any past run is reproducible.

## What is currently defended

After v5, the suite of guardrails covers:

- **Citation validity** (script-checked via `test_every_citation_resolves_to_a_real_fixture_field`): every citation in every briefing — stub-side or live — points at a real input field. Six allowed forms: `tickets[<id>]`, `usage_events[<range>]`, `nps[<date>]`, `health.signals.<field>`, `account.<field>`, `usage_window.<field>`.
- **Renewal-prose accuracy** (stub-side via `test_renewal_prose_matches_cited_renewal_date`; live-side via `_check_renewal_prose` in `run_eval.py`): bullets that cite `account.renewal_date` and include a numeric distance must match the fixture's actual day count. Days, weeks, months, and years all checked.
- **Schema validity, bullet count, headline length**: enforced by the Pydantic `Briefing` model on every parse, plus the live-path mocked tests.
- **Demo-screenshot integrity** (`test_three_handcrafted_accounts_are_in_critical_bucket`): the three hand-crafted critical accounts always land in the Critical bucket so a scoring tweak can't silently gut the demo.
- **Live-path import surface** (`test_state_to_llm_payload_runs_without_api_key`): the function pytest can't run for free against the live API is exercised against the stub so a NameError or bad import there fails locally instead of on a paid call.

## How to run an eval

```bash
# Set ANTHROPIC_API_KEY in .env or your shell.
python scripts/run_eval.py --prompts prompts/briefing.md --label v5
# Hand-grade specificity and action-orientation in the produced markdown.
# Commit the result file alongside the prompt change.
```

Cost: roughly $0.06–0.10 per run (12 scenarios × 1 Haiku call each at the default model). Still cheap enough that prompt bumps should always gate on an eval run, never ship without one. The methodology asymmetry on retrofits is documented in `results/v1_vs_v2.md`.

`run_eval.py` does **not** auto-grade specificity or action-orientation — those are intentionally human-judgment to keep the bar honest. It does emit machine-checked PASS/FAIL lines for renewal-prose accuracy and citation form (when extended).
