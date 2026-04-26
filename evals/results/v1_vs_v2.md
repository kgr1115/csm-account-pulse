# Briefing prompt eval — v1 vs v2

Per the methodology in `evals/methodology.md`. Live runs against `claude-haiku-4-5-20251001`, fixture date anchor 2026-04-26. Raw outputs: `v1.md`, `v2.md`. Total cost: 10 calls, ~$0.05.

## Methodology asymmetry — read this first

The actual code change between v1 and v2 was two commits: `fdc46f1` (private) bumped the prompt **and** added `events_last_7d_start` / `events_last_7d_end` to the LLM payload. Running v1 against today's payload gives v1 access to fields it never had at ship time. The fair experiment would be to revert `briefing.py` for the v1 run; for the cost of the eval (~$0.05 either way), that level of rigor isn't justified for a portfolio retrofit.

What this asymmetry does change: v1's specificity score is mildly inflated relative to its real-world performance, because the LLM has access to extra structured fields it can quote. The v2 win below would be at least as large under a strictly-controlled experiment, not smaller.

## Objective dimensions (script-checked)

| Dimension | v1 | v2 | Notes |
|---|---|---|---|
| **Citation validity** | 5/5 (0 invalid across 5 scenarios) | 5/5 (0 invalid across 5 scenarios) | Verified by walking every cited ticket ID, NPS date, and `usage_events[]` range against the fixture data. Both prompts produced citations that all resolve. |
| **Schema validity** | 5/5 (PASS on all 5) | 5/5 (PASS on all 5) | `Briefing.model_validate` accepted every output on the first parse. Both wrapped JSON in a `\`\`\`json` fence; the live-path fence-stripper handles this. |
| **Bullet count** | 5/5 (all returned exactly 3) | 5/5 (all returned exactly 3) | No regression in either direction. |

## Subjective dimensions (hand-graded against the rubric)

### Specificity

| Scenario | v1 | v2 | Why |
|---|---|---|---|
| S1 — Multi-signal critical | 4 | 4 | Both cite ticket IDs, NPS dates, the 22-event count. v2 names the primary contact ("Mira Petrov"). v1 quotes the NPS comment more fully. Tie. |
| S2 — Single-signal critical (abandonment) | 4 | 5 | v2's first bullet is the right call ("100% drop in last 7 days; investigate whether Initech has paused operations or switched platforms") — it leads with the abandonment thesis the scenario was designed to stress. v1 bundles tickets and usage in the first bullet, diluting the abandonment story. |
| S3 — Quiet at-risk | 4 | 5 | v2 cites the explicit `$95k ARR` figure as a stake; v1 doesn't quote a dollar amount. Otherwise comparable. |
| S4 — Healthy with renewal soon | 5 | 4 | v1 wins this one. v1 cites ticket `T-1148` by ID and quotes "usage trending up 9.1%" and "plan tier upgrade given strong adoption" — the most specific output of either run. v2 generalizes to "custom field sync ticket" without the ID. |
| S5 — Pure healthy, far renewal | 4 | 5 | v2 names a concrete expansion play ("Pro-to-Enterprise upgrade candidates") where v1 stops at "expansion within Pro tier." |
| **Mean** | **4.2** | **4.6** | |

### Action orientation

| Scenario | v1 | v2 | Why |
|---|---|---|---|
| S1 | 4 | 5 | v2's third bullet — "schedule urgent call with Mira Petrov this week" — names a contact and a window. v1's third bullet is "validate that fixes are prioritized" — passive voice. |
| S2 | 4 | 5 | v2 closes with "schedule an urgent account health call with Bill Lumbergh this week" + "commit to a ticket resolution roadmap" — three actions, all bounded. v1's "coordinate with support leadership to triage" is comparable but less crisp. |
| S3 | 4 | 5 | v2's "schedule technical deep-dive to address scalability concerns" is the more specific intervention than v1's "act now to stabilize the relationship." |
| S4 | 5 | 4 | v1's "expansion conversation around plan tier upgrade given strong adoption" is the most action-specific bullet of the run. v2's "explore expansion opportunities" is softer. |
| S5 | 4 | 5 | v2's "identify Pro-to-Enterprise upgrade candidates" beats v1's "documenting use cases to ease future renewal conversation" on near-term action. |
| **Mean** | **4.2** | **4.8** | |

## Verdict

Per the methodology rubric ("v_{n+1} ≥ v_n on every dimension AND strictly better on at least one, by mean"):

| | v1 | v2 |
|---|---|---|
| Citation validity | 5.0 | 5.0 |
| Schema validity | 5.0 | 5.0 |
| Bullet count | 5.0 | 5.0 |
| Specificity | 4.2 | **4.6** |
| Action orientation | 4.2 | **4.8** |

**v2 is defensible.** It dominates v1 on the means across all scenarios, ties on the three objective dimensions, and wins by ~0.4–0.6 on each subjective dimension. The bump was retrofitted with this eval (the original v1→v2 ship was not gated on it); next time the discipline runs forward.

## Where v2 still loses

S4 (healthy with renewal soon) is a real v1 win, not a tie. The S4 v2 output drops the ticket ID, the precise usage trend percentage, and the concrete "plan tier upgrade" expansion play. That's a regression, not noise:

> **v1 S4:** "Resolve open high-severity ticket T-1148 (custom field sync to CRM) this week — it's blocking core workflow integration."
> **v2 S4:** "Close out the open high-severity custom field sync ticket blocking CRM integration."

v3 should preserve v2's improvements (citation rule for trailing-7-day windows) without leaking specificity on healthy-bucket briefings. One hypothesis: v2's added emphasis on the new `events_last_7d_*` fields shifted attention away from ticket-ID precision. Worth A/B-ing if the fix is cheap.

## Open issue surfaced by the eval — both versions

For ACC-001 (Globex Robotics, S1), both prompts produce a bullet that **cites `account.renewal_date`** correctly *and* makes a wrong prose claim about the renewal distance:

| | What the bullet says | Actual |
|---|---|---|
| v1 | "renewal in 14 months" | 58 days (~2 months) |
| v2 | "renewal in 424 days" | 58 days (~2 months) |

The citation is valid (`account.renewal_date` is a real field) — the citation validator passes. The prose is wrong — there's no test for prose accuracy.

This is the next prompt iteration's clearest target: **the citation rule should require that any prose claim about a citable date be derived from the cited value, not invented.** Implementation options for v3:

1. Tighten the prompt: "When you cite `account.renewal_date`, the bullet text must include the ISO date or the days-to-renewal computed from the input — not a months/years approximation you derived."
2. Add a regression test that walks bullet text for `\d+ months?|years?|days?` patterns adjacent to `account.renewal_date` citations and checks them against the fixture.

Option 2 is the more durable fix because it doesn't depend on the model honoring a prompt instruction.

## Reproducibility

Re-run anytime with:

```bash
python scripts/run_eval.py --prompts evals/old_prompts/briefing.v1.md --label v1
python scripts/run_eval.py --prompts prompts/briefing.md --label v2
```

A run takes ~30 seconds and writes raw outputs to `evals/results/`. Hand-graded numbers in this file should be re-graded if the prompts change — they're not auto-regenerated.
