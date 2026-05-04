# Eval results — label `v5-12scenarios`

- Prompt: `prompts\briefing.md`
- Model: `claude-haiku-4-5-20251001`
- Fixture date anchor: 2026-04-26
- Mode: live

Hand-grade Specificity and Action-orientation 1-5 for each scenario after the run completes.

## S1 — Multi-signal critical

- Account: `ACC-001` (Globex Robotics)
- Expected bucket: Critical, actual: Critical
- What it stresses: Multiple loud signals at once — renewal soon, open critical tickets, NPS detractor, usage decay. The prompt must prioritize, not enumerate.

### Raw output
```json
```json
{
  "account_id": "ACC-001",
  "headline": "Critical health crisis: usage collapse and API outages",
  "bullets": [
    {
      "text": "Usage has dropped 62% week-over-week with only 22 events in the last 7 days; schedule an urgent call with Mira Petrov to understand if there's a technical blocker or adoption issue.",
      "citations": ["health.signals.usage_decay_pct", "usage_window.events_last_7d"]
    },
    {
      "text": "Three open high/critical tickets including API 502 errors and missing audit log entries are blocking operations; prioritize resolution of T-1002 (audit log) and T-1000 (API bulk export) this week.",
      "citations": ["health.signals.open_high_severity_tickets", "tickets[T-1000]", "tickets[T-1002]"]
    },
    {
      "text": "NPS dropped from 8 to 4 in recent response citing API reliability concerns; renewal in 58 days makes retention risk immediate.",
      "citations": ["nps[2026-04-16]", "usage_window.days_to_renewal"]
    }
  ]
}
```
```

**Schema validity:** PASS
**Bullet count:** 3
**Citations per bullet:** [2, 3, 2]
**Renewal prose check:** N/A (no bullet cites `account.renewal_date` with a numeric distance)

**Specificity (1-5):** _grade me_
**Action-orientation (1-5):** _grade me_

---

## S2 — Single-signal critical (abandonment)

- Account: `ACC-002` (Initech Manufacturing)
- Expected bucket: Critical, actual: Critical
- What it stresses: Near-zero recent usage dominates; the real story is abandonment, not ticket volume. Tests whether the prompt over-weights tickets when usage has cratered.

### Raw output
```json
```json
{
  "account_id": "ACC-002",
  "headline": "Critical: 7 open tickets, zero usage, churn risk",
  "bullets": [
    {
      "text": "Immediate escalation needed: 7 critical/high-severity tickets open including report scheduler failures, webhook validation issues, and dashboard timeouts; schedule emergency triage with Bill Lumbergh this week.",
      "citations": [
        "tickets[T-1011]",
        "tickets[T-1012]",
        "tickets[T-1013]",
        "tickets[T-1014]",
        "health.signals.open_high_severity_tickets"
      ]
    },
    {
      "text": "Usage collapsed to zero in last 7 days and customer satisfaction plummeted to NPS 1; root cause is likely ticket backlog—resolve critical issues to restore platform trust before renewal in 89 days.",
      "citations": [
        "usage_window.events_last_7d",
        "nps[2026-04-16]",
        "usage_window.days_to_renewal"
      ]
    },
    {
      "text": "Customer has already voiced loss of trust and collapsed support confidence; conduct win-back call with Bill Lumbergh to demonstrate resolution progress and rebuild confidence ahead of renewal.",
      "citations": [
        "nps[2026-03-04]",
        "nps[2026-04-16]",
        "health.signals.detractor_count_90d"
      ]
    }
  ]
}
```
```

**Schema validity:** PASS
**Bullet count:** 3
**Citations per bullet:** [5, 3, 3]
**Renewal prose check:** N/A (no bullet cites `account.renewal_date` with a numeric distance)

**Specificity (1-5):** _grade me_
**Action-orientation (1-5):** _grade me_

---

## S3 — Quiet at-risk

- Account: `ACC-020` (InGen Holdings)
- Expected bucket: At-Risk, actual: At-Risk
- What it stresses: At-risk by composite score but no single five-alarm signal. Tests whether the prompt finds a defensible angle without inventing severity.

### Raw output
```json
```json
{
  "account_id": "ACC-020",
  "headline": "Usage collapsed 67%; NPS detractor signals churn risk",
  "bullets": [
    {
      "text": "Usage dropped to just 9 events in the last 7 days—a 67% decay from prior week; schedule an urgent check-in with Alex Morgan to diagnose the drop before renewal in 65 days.",
      "citations": ["health.signals.usage_decay_pct", "usage_window.events_last_7d", "usage_window.days_to_renewal", "account.primary_contact_name"]
    },
    {
      "text": "Latest NPS response (2/10) cites API reliability failures at their scale—investigate the April 16 detractor comment and confirm whether a support ticket or escalation is needed.",
      "citations": ["nps[2026-04-16]", "health.signals.latest_nps_score"]
    },
    {
      "text": "Sentiment swung from promoter (8/10 on March 4) to severe detractor in 6 weeks; prioritize understanding the root cause before renewal conversation kicks off.",
      "citations": ["nps[2026-03-04]", "health.signals.detractor_count_90d"]
    }
  ]
}
```
```

**Schema validity:** PASS
**Bullet count:** 3
**Citations per bullet:** [4, 2, 2]
**Renewal prose check:** N/A (no bullet cites `account.renewal_date` with a numeric distance)

**Specificity (1-5):** _grade me_
**Action-orientation (1-5):** _grade me_

---

## S4 — Healthy with renewal soon

- Account: `ACC-019` (Oscorp Holdings)
- Expected bucket: Healthy, actual: Healthy
- What it stresses: Healthy briefings must not invent problems; should pivot to expansion / multi-year renewal motion.

### Raw output
```json
```json
{
  "account_id": "ACC-019",
  "headline": "Strong health but resolve CRM sync issue before renewal",
  "bullets": [
    {
      "text": "Close out the open high-severity CRM sync ticket (T-1148) with Casey Park—it's been blocking custom field syncing since March and renewal is 64 days away.",
      "citations": ["tickets[T-1148]", "account.primary_contact_name", "usage_window.days_to_renewal"]
    },
    {
      "text": "Usage is up 9% week-over-week (24 events in last 7 days) and latest NPS is 9—reinforce this momentum by highlighting the 'excellent partnership' feedback to Priya.",
      "citations": ["usage_window.events_last_7d", "nps[2026-04-16T14:00:00]"]
    },
    {
      "text": "Plan an expansion conversation with Casey Park around their Starter plan; they're stable at $9k ARR and showing strong engagement in a 12-person healthcare team.",
      "citations": ["account.primary_contact_name", "account.arr_usd", "account.employee_count"]
    }
  ]
}
```
```

**Schema validity:** PASS
**Bullet count:** 3
**Citations per bullet:** [3, 2, 3]
**Renewal prose check:** N/A (no bullet cites `account.renewal_date` with a numeric distance)

**Specificity (1-5):** _grade me_
**Action-orientation (1-5):** _grade me_

---

## S5 — Pure healthy, far renewal

- Account: `ACC-004` (Hooli Industries)
- Expected bucket: Healthy, actual: Healthy
- What it stresses: Tests graceful 'nothing to do' bullets — no padded platitudes, no invented urgency.

### Raw output
```json
```json
{
  "account_id": "ACC-004",
  "headline": "Healthy account with growing engagement—focus on expansion",
  "bullets": [
    {
      "text": "Usage is up 5.6% month-over-month with 57 events in the last 7 days; schedule a business review with Taylor Nguyen to explore upsell opportunities.",
      "citations": ["health.signals.usage_decay_pct", "usage_window.events_last_7d"]
    },
    {
      "text": "NPS improved from 6 to 7 between March and April; document wins and consider Taylor as a reference or case study candidate.",
      "citations": ["nps[2026-03-04]", "nps[2026-04-16]"]
    },
    {
      "text": "Zero open tickets and no detractors this period—prioritize retention and advocacy initiatives to maintain momentum ahead of renewal in 261 days.",
      "citations": ["health.signals.open_high_severity_tickets", "usage_window.days_to_renewal"]
    }
  ]
}
```
```

**Schema validity:** PASS
**Bullet count:** 3
**Citations per bullet:** [2, 2, 2]
**Renewal prose check:** N/A (no bullet cites `account.renewal_date` with a numeric distance)

**Specificity (1-5):** _grade me_
**Action-orientation (1-5):** _grade me_

---

## S6 — No NPS data at all

- Account: `ACC-051` (Cyberdyne Trust)
- Expected bucket: Healthy, actual: Healthy
- What it stresses: Account has zero NPS responses. Tests whether the prompt hallucinates NPS signals or gracefully cites only what's present (usage, tickets).

### Raw output
```json
```json
{
  "account_id": "ACC-051",
  "headline": "Healthy account with solid engagement; focus on expansion",
  "bullets": [
    {
      "text": "No detractors and zero high-severity tickets in 90 days; schedule a business review with Sasha Lin to explore upsell opportunities before renewal in 111 days.",
      "citations": [
        "health.signals.detractor_count_90d",
        "health.signals.open_high_severity_tickets",
        "usage_window.days_to_renewal",
        "account.primary_contact_name"
      ]
    },
    {
      "text": "Usage is steady with 6 events in the last 7 days and only 14.3% decay; confirm feature adoption is meeting their operational goals.",
      "citations": [
        "usage_window.events_last_7d",
        "health.signals.usage_decay_pct"
      ]
    },
    {
      "text": "Both recent tickets (MFA reset and CSV export) resolved quickly; document these common friction points to inform product feedback or training.",
      "citations": [
        "tickets[T-2051]",
        "tickets[T-2052]"
      ]
    }
  ]
}
```
```

**Schema validity:** PASS
**Bullet count:** 3
**Citations per bullet:** [4, 2, 2]
**Renewal prose check:** N/A (no bullet cites `account.renewal_date` with a numeric distance)

**Specificity (1-5):** _grade me_
**Action-orientation (1-5):** _grade me_

---

## S7 — High ticket volume, zero usage decay

- Account: `ACC-052` (Tyrell Health Networks)
- Expected bucket: Healthy, actual: Healthy
- What it stresses: Eight tickets in 30 days but usage is flat (decay = 0%) and the open ticket is medium severity. Tests whether the prompt over-weights ticket count when usage and NPS are fine.

### Raw output
```json
```json
{
  "account_id": "ACC-052",
  "headline": "Healthy account—resolve one open bug, plan expansion",
  "bullets": [
    {
      "text": "Close open ticket T-2067 (audit log filter dropdown) this week to maintain perfect resolved rate.",
      "citations": ["tickets[T-2067]"]
    },
    {
      "text": "Schedule expansion conversation with Devin Park around scaling use cases; NPS of 8 and zero detractors signal strong satisfaction.",
      "citations": ["health.signals.latest_nps_score", "health.signals.detractor_count_90d"]
    },
    {
      "text": "Plan renewal strategy conversation 147 days out; account is healthy with 13 usage events in last 7 days and only 7.1% decay.",
      "citations": ["usage_window.days_to_renewal", "usage_window.events_last_7d", "health.signals.usage_decay_pct"]
    }
  ]
}
```
```

**Schema validity:** PASS
**Bullet count:** 3
**Citations per bullet:** [1, 2, 3]
**Renewal prose check:** N/A (no bullet cites `account.renewal_date` with a numeric distance)

**Specificity (1-5):** _grade me_
**Action-orientation (1-5):** _grade me_

---

## S8 — Long renewal horizon, all signals green

- Account: `ACC-053` (Stark Renewables)
- Expected bucket: Healthy, actual: Healthy
- What it stresses: Renewal 18+ months out, healthy growing usage, no tickets, NPS promoter (10). Tests whether the prompt manufactures urgency or stays genuinely quiet.

### Raw output
```json
```json
{
  "account_id": "ACC-053",
  "headline": "Healthy enterprise account—leverage for expansion",
  "bullets": [
    {
      "text": "Pat Whitaker is a strong advocate with consecutive perfect NPS scores; schedule a reference call or case study opportunity this week.",
      "citations": ["nps[2026-03-04]", "nps[2026-04-16]"]
    },
    {
      "text": "Usage is growing with 14 events in the last 7 days; discuss expansion opportunities aligned with their Enterprise plan.",
      "citations": ["usage_window.events_last_7d"]
    },
    {
      "text": "Zero support tickets and healthy engagement signal strong product fit; focus on upsell and renewal planning with 584 days remaining.",
      "citations": ["health.signals.open_high_severity_tickets", "usage_window.days_to_renewal"]
    }
  ]
}
```
```

**Schema validity:** PASS
**Bullet count:** 3
**Citations per bullet:** [2, 1, 2]
**Renewal prose check:** N/A (no bullet cites `account.renewal_date` with a numeric distance)

**Specificity (1-5):** _grade me_
**Action-orientation (1-5):** _grade me_

---

## S9 — Renewal in 7 days, healthy signals

- Account: `ACC-054` (Wonka Confections)
- Expected bucket: Healthy, actual: Healthy
- What it stresses: Imminent renewal but otherwise quiet (no tickets, NPS=9, flat usage). Pressure-tests the renewal-prose accuracy rules — should surface 'renewal is imminent' without fabricating risk.

### Raw output
```json
```json
{
  "account_id": "ACC-054",
  "headline": "Perfect health—lock in multi-year deal now",
  "bullets": [
    {
      "text": "Riley Okafor signaled openness to multi-year commitment in latest NPS; schedule renewal conversation with them this week before the 15-day window closes.",
      "citations": ["nps[2026-04-16]", "usage_window.days_to_renewal"]
    },
    {
      "text": "Usage remains strong at 14 events in the last 7 days with zero decay, indicating consistent engagement across the Pro tier.",
      "citations": ["usage_window.events_last_7d", "health.signals.usage_decay_pct"]
    },
    {
      "text": "No open tickets and NPS score of 9 confirm satisfaction; position this as an expansion conversation to explore additional seats or modules before renewal.",
      "citations": ["health.signals.open_high_severity_tickets", "health.signals.latest_nps_score"]
    }
  ]
}
```
```

**Schema validity:** PASS
**Bullet count:** 3
**Citations per bullet:** [2, 2, 2]
**Renewal prose check:** N/A (no bullet cites `account.renewal_date` with a numeric distance)

**Specificity (1-5):** _grade me_
**Action-orientation (1-5):** _grade me_

---

## S10 — Mixed severity tickets, no open high/critical

- Account: `ACC-055` (Soylent Foods Group)
- Expected bucket: Healthy, actual: Healthy
- What it stresses: Five tickets in the 30-day window spanning low/medium/high severity, but ALL resolved. Tests whether ticket_volume_30d gets over-weighted vs. open_high_severity_tickets.

### Raw output
```json
```json
{
  "account_id": "ACC-055",
  "headline": "Healthy account—reinforce value and explore expansion",
  "bullets": [
    {
      "text": "Score of 96 with zero detractors and no open high-severity issues; schedule a business review with Harper Singh to discuss H2 priorities and identify expansion opportunities.",
      "citations": [
        "health.score",
        "health.signals.detractor_count_90d",
        "health.signals.open_high_severity_tickets",
        "account.primary_contact_name"
      ]
    },
    {
      "text": "All 5 tickets in the last 30 days resolved promptly (average 2–3 days); highlight this reliability in retention conversation ahead of renewal in 167 days.",
      "citations": [
        "health.signals.ticket_volume_30d",
        "tickets[T-2070]",
        "tickets[T-2071]",
        "tickets[T-2072]",
        "tickets[T-2073]",
        "tickets[T-2074]",
        "usage_window.days_to_renewal"
      ]
    },
    {
      "text": "Steady weekly engagement (7 events in the last 7 days) and NPS of 7 confirm strong product fit; use this momentum to propose advanced features or increased seat commitment.",
      "citations": [
        "usage_window.events_last_7d",
        "health.signals.latest_nps_score"
      ]
    }
  ]
}
```
```

**Schema validity:** PASS
**Bullet count:** 3
**Citations per bullet:** [4, 7, 2]
**Renewal prose check:** N/A (no bullet cites `account.renewal_date` with a numeric distance)

**Specificity (1-5):** _grade me_
**Action-orientation (1-5):** _grade me_

---

## S11 — Single NPS detractor, no other signals

- Account: `ACC-056` (Aperture Field Services)
- Expected bucket: Watch, actual: Watch
- What it stresses: One NPS score of 2, otherwise quiet (healthy usage, no tickets). Tests whether a single NPS detractor alone is enough to surface as a bullet without inventing supporting signals.

### Raw output
```json
```json
{
  "account_id": "ACC-056",
  "headline": "NPS detractor signals onboarding gaps—stabilize now",
  "bullets": [
    {
      "text": "Jamie Cordova rated us a 2 on April 16 citing painful onboarding and ongoing gaps; schedule a recovery call this week to understand what's broken.",
      "citations": ["nps[2026-04-16]"]
    },
    {
      "text": "Usage remains low at 6 events in the last 7 days despite no decay; confirm whether the team is actually adopting the platform or if training is incomplete.",
      "citations": ["usage_window.events_last_7d", "health.signals.usage_decay_pct"]
    },
    {
      "text": "Renewal is 218 days away but the detractor sentiment is a retention risk; prioritize closing the onboarding gaps before next quarter to prevent churn.",
      "citations": ["usage_window.days_to_renewal", "health.signals.detractor_count_90d"]
    }
  ]
}
```
```

**Schema validity:** PASS
**Bullet count:** 3
**Citations per bullet:** [1, 2, 2]
**Renewal prose check:** N/A (no bullet cites `account.renewal_date` with a numeric distance)

**Specificity (1-5):** _grade me_
**Action-orientation (1-5):** _grade me_

---

## S12 — New account, <30 days of data

- Account: `ACC-057` (Pied Piper Compression)
- Expected bucket: Healthy, actual: Healthy
- What it stresses: Contract started ~3 weeks ago; usage window is thin (10 events total), no NPS yet, one resolved ticket. Tests whether the prompt hallucinates baseline data or cites the thin window explicitly.

### Raw output
```json
```json
{
  "account_id": "ACC-057",
  "headline": "Healthy Starter account; plan expansion opportunity",
  "bullets": [
    {
      "text": "Account is performing well with no usage decay and zero high-severity issues; focus on deepening relationship with Avery Bloom to identify expansion needs before renewal in 344 days.",
      "citations": ["health.signals.usage_decay_pct", "health.signals.open_high_severity_tickets", "account.renewal_date"]
    },
    {
      "text": "One resolved onboarding ticket about admin access suggests the team is still ramping; follow up on whether multi-admin workflows are now unblocked and if they need additional user seats.",
      "citations": ["tickets[T-2080]"]
    },
    {
      "text": "Recent activity is steady at 3 events in the last 7 days; schedule a check-in with Avery to explore use cases and validate that Starter tier continues to fit their growth trajectory.",
      "citations": ["usage_window.events_last_7d"]
    }
  ]
}
```
```

**Schema validity:** PASS
**Bullet count:** 3
**Citations per bullet:** [3, 1, 1]
**Renewal prose check:**
  - bullet 1: PASS — `344 days`, actual 344 days

**Specificity (1-5):** _grade me_
**Action-orientation (1-5):** _grade me_

---

## v5 prompt-drift observations

These behaviors surfaced during the baseline run. They are **not regressions in the existing test suite** — all 42 pytest tests pass and all 12 scenarios produced schema-valid output. They seed follow-up prompt-bump proposals; this expansion ships unchanged per the architect's "no prompt changes in this commit" constraint.

### Finding 1 — `_check_renewal_prose` rarely fires under v5

The live-path renewal-prose accuracy check (`scripts/run_eval.py::_check_renewal_prose`) only fires on bullets that cite `account.renewal_date`. In this 12-scenario run, only S12 produced a bullet citing `account.renewal_date` (PASS, 344 days actual = 344 days asserted). The other 11 scenarios cited `usage_window.days_to_renewal` instead, which is the citation form v5 explicitly added in the v4→v5 bump (per `evals/README.md`). The check returns N/A on those bullets because it has no `account.renewal_date` citation to anchor against.

**Implication:** The live-path renewal-prose accuracy guard is effectively dormant under v5. Methodology gap, not a correctness regression — but the guard exists for a reason (defending against the v3-class day-count hallucination), and a v5 prompt that bypasses the guard's trigger weakens it.

**Suggested follow-up:** New proposal that either (a) extends `_check_renewal_prose` to also fire on `usage_window.days_to_renewal` citations, or (b) bumps the prompt to require `account.renewal_date` co-citation when prose includes a numeric day count.

### Finding 2 — S4 cited `nps[2026-04-16T14:00:00]` (timestamp, not date)

The citation validator (`tests/test_briefing.py::test_every_citation_resolves_to_a_real_fixture_field`) expects the form `nps[YYYY-MM-DD]`. The S4 raw output cited `nps[2026-04-16T14:00:00]` — a full ISO-8601 timestamp instead of a date. This citation form is **not** in the allowed grammar in `prompts/briefing.md`.

**Implication:** If the citation validator were extended to live-side output (today it runs against stub-side only), S4 would fail. The drift is a v5 behavior — the prompt does not currently constrain timestamp vs. date precision on `nps` citations.

**Suggested follow-up:** New proposal that tightens the prompt's `nps[<date>]` rule to forbid timestamp components (`T...` suffix) and adds a regression test against the v5 archived prompt.

### Finding 3 — S10 cited `health.score` (not in allowed grammar)

The S10 raw output cited `health.score`. The allowed citation grammar permits `health.signals.<field>` only. `health.score` is a derived value, not a signal field, and is therefore not a valid citation under the v5 grammar.

**Implication:** Same as Finding 2 — the citation validator would FAIL S10 if applied to live output. The drift suggests the v5 prompt's grammar specification needs an explicit prohibition on `health.score` (and any other top-level `health.*` field that isn't `health.signals.<...>`).

**Suggested follow-up:** New proposal that tightens the prompt's `health.signals.<field>` rule to explicitly forbid `health.score`, `health.bucket`, and any other non-`signals` health field.

---

**Aggregate:** 0 regressions. 3 prompt-drift observations queued as follow-up prompt-bump candidates. All three would benefit from extending the citation validator to run against live-side output behind a paid-API flag — but that's a separate scope-of-test-coverage decision (CEng + COO).
