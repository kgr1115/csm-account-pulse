# Briefing prompt eval — v2 vs v3

Per the methodology in `evals/methodology.md`. Live runs against `claude-haiku-4-5-20251001`, fixture date anchor 2026-04-26. Raw outputs: `v2.md` (regenerated against v2 in the prior cycle), `v3.md` (this cycle). Total cost this run: 5 calls, ~$0.025 (v2's raw output was reused — payload code unchanged between v2 and v3, only the prompt changed).

This is the first prompt bump that landed with its own result file run **forward**, per the discipline established in `methodology.md`. The v1→v2 file was retrofitted; this one is not.

## What v3 was supposed to fix

The v1-vs-v2 eval surfaced one open issue both versions shared: bullets that cited `account.renewal_date` correctly but invented the prose distance (v1: "renewal in 14 months"; v2: "renewal in 424 days"; actual: 58 days for ACC-001). v3 added two things to address it:

1. A new prompt rule (`prompts/briefing.md` §"Citation rules — STRICT"): "When you cite `account.renewal_date`, any prose distance must be the ISO date or the integer number of days between `account.renewal_date` and `usage_window.end`. Do not approximate the distance in months, weeks, or years."
2. A regression test (`test_renewal_prose_matches_cited_renewal_date`) that walks any number+unit phrase in a bullet citing `account.renewal_date` and verifies it is consistent with the actual fixture distance.

## Objective dimensions (script-checked)

| Dimension | v2 | v3 | Notes |
|---|---|---|---|
| **Citation validity** | 5/5 | 5/5 | All cited ticket IDs, NPS dates, usage_events ranges, and account/health fields resolve to real fixture values. v3 introduces a new citation form `account.primary_contact_name` (S5); confirmed real per `models.Account`. |
| **Schema validity** | 5/5 | 5/5 | `Briefing.model_validate` accepted every output on first parse for both versions. Both wrap JSON in a ```json fence; the live-path fence-stripper handles it. |
| **Bullet count** | 5/5 | 5/5 | Both returned exactly 3 bullets in every scenario. |

## The renewal-prose dimension v3 explicitly targeted

This is what the bump was for. Cross-checked v3's renewal prose against the actual fixture distance from anchor 2026-04-26:

| Scenario | Account | Actual days | v2 said | v3 said | v2 verdict | v3 verdict |
|---|---|---|---|---|---|---|
| S1 | ACC-001 | 58 | "renewal in 424 days" | "renewal in 60 days" | ❌ off by 366 | ⚠️ off by 2 |
| S3 | ACC-020 | 65 | "Renewal is 26 months away" | "Renewal is 68 days away" | ❌ off by ~21mo | ⚠️ off by 3 |
| S4 | ACC-019 | 64 | "ahead of June 2026 renewal date" (qualitative — passes) | "lock in renewal at 564 days out" | ✅ ok | ❌ off by 500 |
| S5 | ACC-004 | 261 | "Renewal not until January 2027" (qualitative — passes) | "Renewal is 261 days away (2027-01-12)" | ✅ ok | ✅ correct |

**v3 eliminated the v2 failure class** (no more "424 days" / "26 months" — the months/years approximations are gone) but **introduced a new failure class**: confidently wrong day counts. The S4 hallucination is the most serious — "564 days" vs actual 64 — and is exactly the sort of error a CSM might act on (deprioritize a renewal that's actually in 2 months).

## Where the new regression test fell short

`test_renewal_prose_matches_cited_renewal_date` is structured to catch this — it computes `actual_days = (a.renewal_date - today).days` and rejects bullets that cite `account.renewal_date` with a wrong day count. **But it only runs against the stub path** (`generate_briefing(state, api_key=None)`). The stub emits `f"Renewal in {days_to_renewal} days"` precisely, so the test trivially passes day one.

The live LLM output is what hallucinates, and the existing test never sees live output. The CLAUDE.md guard ("never call paid APIs unilaterally") rules out a test that calls the API on every `pytest` run — but the *eval* runner does call live, and could enforce the same check post-hoc.

## Subjective dimensions (hand-graded against the rubric)

### Specificity

| Scenario | v2 | v3 | Why |
|---|---|---|---|
| S1 — Multi-signal critical | 4 | 4 | Both cite ticket IDs (T-1002, T-1000), NPS date, the 22-event count. v2 names "Mira Petrov" in full; v3 just "Mira". Tie. |
| S2 — Single-signal critical | 5 | 5 | Both lead with the abandonment thesis. v2 cites 4 ticket IDs in one bullet, v3 cites 3 with category descriptions ("webhook validation, scheduler, dashboard timeouts") — different compactness, comparable density. Tie. |
| S3 — Quiet at-risk | 5 | 4 | v2 cites the explicit `$95k ARR` figure. v3 drops the dollar amount. v2 wins. (Note: v2's "26 months away" was wrong, but the citation set was richer.) |
| S4 — Healthy with renewal soon | 4 | 5 | **v3 recovers v1's strength here.** v3: "Resolve the open high-severity custom field sync ticket (T-1148) blocking their CRM integration before it impacts renewal discussions." v2 dropped the ticket ID; v3 brings it back with a deadline anchor. |
| S5 — Pure healthy | 5 | 5 | Both name expansion play (v2: "Pro-to-Enterprise"; v3: "expansion / contract terms"). v3 cites `account.primary_contact_name` — concrete contact callout. Tie. |
| **Mean** | **4.6** | **4.6** | |

### Action orientation

| Scenario | v2 | v3 | Why |
|---|---|---|---|
| S1 | 5 | 4 | v2's "schedule urgent call with Mira Petrov this week" names a contact and a window. v3 ends at "Schedule urgent triage call with VP Engineering" — the role is generic where v2 names the specific contact. v2 wins. |
| S2 | 5 | 5 | Both close with "schedule urgent call with Bill Lumbergh" + ticket commitment. Tie. |
| S3 | 5 | 4 | v2's third bullet anchors action to the $95k ARR stake; v3's third bullet just says "without intervention this account is at serious churn risk" — softer, no specific action. v2 wins. |
| S4 | 4 | 5 | v3's "before it impacts renewal discussions" is the sharper deadline anchor for the ticket-resolve action. v3 wins. |
| S5 | 5 | 5 | v2: "identify Pro-to-Enterprise upgrade candidates". v3: "schedule a brief check-in with Taylor Nguyen" + "lock in contract terms or upsell". Both action-specific. Tie. |
| **Mean** | **4.8** | **4.6** | |

## Verdict

Per the methodology rubric ("v_{n+1} ≥ v_n on every dimension AND strictly better on at least one, by mean"):

| | v2 | v3 |
|---|---|---|
| Citation validity | 5.0 | 5.0 |
| Schema validity | 5.0 | 5.0 |
| Bullet count | 5.0 | 5.0 |
| Specificity | 4.6 | 4.6 |
| Action orientation | 4.8 | 4.6 |
| **Renewal-prose accuracy** *(new dimension this cycle)* | 2/4 wrong (months/years class) | 1/4 wrong (day-count class) |

**v3 is a partial defensible bump.** It cleanly wins the dimension it was designed to fix (eliminates the months/years approximation class) and recovers the v2-vs-v1 S4 regression by bringing back the ticket ID. It loses ~0.2 on action orientation (S1, S3 lose specificity in the closing call-to-action). The newly-introduced failure mode — confidently wrong day counts, including a 500-day error on S4 — is real and not caught by the regression test as written.

By the strict methodology bar, v3 does not pass: action orientation regressed. By the spirit of the bar (the prompt is improving on its stated target without obviously breaking elsewhere), v3 ships, but with two clear v4 targets queued.

## v4 targets, in priority order

1. **Eliminate the day-count hallucination class.** The clean fix is to precompute `usage_window.days_to_renewal` (and arguably `account.renewal_date_iso` already exposed) inside `_state_to_llm_payload`, and have the prompt require: "When citing `account.renewal_date`, the prose distance must be exactly `usage_window.days_to_renewal` days, copied from the input. Do not compute the distance yourself." Removes the arithmetic from the model entirely. This is the single highest-value change in the queue — the S4 "564 vs 64" error is the kind of thing a CSM would act on.

2. **Extend the regression test to cover the live path.** The current test runs only against the stub. The eval runner already has the fixture state and the live response in hand for each scenario; a small post-call check there can enforce day-count accuracy on `account.renewal_date`-citing bullets. Doing this in the eval (which is paid and gated) rather than in `pytest` (which runs locally and must stay free) preserves the CLAUDE.md "no unilateral paid API calls" rule.

3. **Recover S1 / S3 action-orientation specificity.** v3 lost some of v2's "schedule urgent call with [named contact] this week" punch in the closing bullets. Investigate whether the new renewal-distance constraint pushed model attention away from contact-naming, or if it's noise. Cheap to A/B.

## Reproducibility

```bash
python scripts/run_eval.py --prompts evals/old_prompts/briefing.v2.md --label v2  # if re-running both
python scripts/run_eval.py --prompts prompts/briefing.md --label v3
```

This run reused the existing `v2.md` from the v1-vs-v2 cycle (payload code unchanged between v2 and v3), so only the v3 call was made — ~$0.025 instead of ~$0.05. Hand-graded numbers above are not auto-regenerated; re-grade if either prompt changes.
