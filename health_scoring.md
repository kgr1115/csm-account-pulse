# Health scoring — weights and rationale

The score in `health.py` is intentionally not ML. It's a hand-tuned linear deduction model that a CSM (or a hiring manager) can read top-to-bottom and immediately understand which signal moved the bucket. This file documents the weights so they're defensible design decisions rather than opaque magic numbers.

## The shape

Every account starts at **100** (perfect). Each signal *deducts* points (or, in two cases, adds a small bonus for unusually positive signals). The final score is clipped to `[0, 100]` and bucketed:

| Score | Bucket |
|---|---|
| 80–100 | Healthy |
| 60–79  | Watch |
| 35–59  | At-Risk |
| 0–34   | Critical |

Bucket boundaries are calibrated against the synthetic fixture distribution: with 50 accounts the demo lands at roughly 3 Critical / 6 At-Risk / 7 Watch / 34 Healthy, which gives the dashboard enough variety to be readable without burying the at-risk accounts.

## Signal: usage decay (week-over-week)

```python
if decay >= 70:    score -= 35
elif decay >= 40:  score -= 22
elif decay >= 20:  score -= 12
elif decay <= -20: score += 5
```

| Threshold | Deduction | Rationale |
|---|---|---|
| ≥70% drop | −35 | A near-zero week is the strongest leading churn indicator we have. By itself this is enough to put a Healthy account into At-Risk. |
| ≥40% drop | −22 | A consistent halving of usage indicates a workflow has stopped. Combined with one open critical ticket this lands Critical. |
| ≥20% drop | −12 | Soft dip; alone it lands in Watch. |
| ≤−20% (growth) | +5 | Acknowledges accounts trending up — small bonus, not a license to ignore other risks. |

**What changing these would do:** raising the 70% threshold to 80% would be too forgiving — week-over-week is already the most volatile signal and cliff-style drops should not have to be perfect zeroes to trigger. Lowering 20% to 10% would over-flag accounts on a holiday week.

## Signal: ticket pressure

```python
score -= min(40, open_high * 12)
if total_30d >= 6:    score -= 8
elif total_30d >= 3:  score -= 4
```

| Component | Deduction | Rationale |
|---|---|---|
| Open high+critical tickets | −12 each, capped at −40 | Each unresolved high/critical signals an active source of friction the customer is feeling now. The cap prevents one runaway integration mess from drowning every other signal. |
| ≥6 tickets in last 30d | −8 | Volume signal independent of severity — a flood of low/medium tickets indicates support-call cost. |
| ≥3 tickets in last 30d | −4 | Soft volume signal. |

**What changing these would do:** raising the per-ticket weight above 12 makes any single high-severity ticket dominate the score. Lowering it under 8 would let an account with 4+ open criticals stay in Watch, which a CSM would reject.

## Signal: NPS

```python
if latest_nps <= 3:    score -= 25
elif latest_nps <= 6:  score -= 12
elif latest_nps >= 9:  score += 4
if detractor_count_90d >= 2:  score -= 8
```

| Threshold | Deduction | Rationale |
|---|---|---|
| Latest score ≤3 | −25 | Strong detractor — they've told you they're unhappy. The CSM should never be surprised. |
| Latest score 4–6 | −12 | Passive/soft-detractor. Worth a discovery call, not yet a fire drill. |
| Latest score ≥9 | +4 | Promoter — small bonus matches the symmetric usage-growth bonus. |
| ≥2 detractors in last 90d | −8 | Trend signal beyond the latest score; if multiple contacts on the account are detracting, one good-mood survey doesn't undo it. |

**What changing these would do:** removing the `latest_nps <= 3 → −25` rule entirely would let an account with 100% usage but a 0 NPS land Healthy, which is a known anti-pattern.

## Why this composition over a multiplicative or learned model

A CSM reads the rationale, not the score. The model is additive deduction so:

- **Each signal contributes a quantity that is human-explainable** ("we deducted 22 because usage halved week-over-week"). A multiplicative score doesn't decompose this way.
- **The bucket boundaries are interpretable.** A Critical account is one where the deductions sum past 65; the dashboard's "Why" line lists the deductions in plain English.
- **Calibration is local.** Changing one weight changes one bucket boundary, not the whole distribution. With ML, you'd retrain on every fixture change.

The trade-off is that this can't model interaction effects (e.g. usage decay × low NPS being worse than the sum). For real customer data, the calibration pass mentioned in the README's Salesforce-swap section would either:
1. Re-fit these constants empirically against churn-vs-renewal outcomes, OR
2. Replace the deductions with a learned model and serve the rationale via SHAP-style attribution to keep explainability.

Either is a calibration question. The interface stays the same.

## Where the constants live

All weights are constants inside `compute_health` in `health.py`. They are deliberately not externalized to a config file — moving them out of code makes them easier to tweak silently and harder to review in a PR. If a real CRM integration needs different weights per market or product line, the right pattern is a `HealthScorePolicy` injected into `compute_health`, not a config file.
