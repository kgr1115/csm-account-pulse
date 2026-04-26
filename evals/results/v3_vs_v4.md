# Briefing prompt eval — v3 vs v4

Per the methodology in `evals/methodology.md`. Live runs against `claude-haiku-4-5-20251001`, fixture date anchor 2026-04-26. Raw outputs: `v3.md`, `v4.md`. Total cost this run: 5 calls, ~$0.025 (v3.md from prior cycle reused).

This bump landed with both the prompt change and the eval result file in the same window — the run-forward discipline `methodology.md` calls for.

## What v4 was supposed to fix

The v2-vs-v3 eval (`v2_vs_v3.md`) surfaced two related failure modes:

1. **Day-count hallucination on `account.renewal_date`** — v3 said "564 days" for ACC-019 (actual 64), "60 days" for ACC-001 (actual 58), "68 days" for ACC-020 (actual 65). The model was doing arithmetic on dates and getting it wrong.
2. **The new regression test only ran against the stub** — `test_renewal_prose_matches_cited_renewal_date` was structurally correct but lived only in `pytest`, where the deterministic stub trivially passes. The hallucinations only appeared against the live model.

v4's two answers:

- **R1**: precompute `usage_window.days_to_renewal` in `_state_to_llm_payload` and update the prompt to require the LLM copy that integer verbatim. Removes model-side arithmetic entirely.
- **R2**: extend `scripts/run_eval.py` with a `_check_renewal_prose` post-processor that walks bullets citing `account.renewal_date` and emits a per-bullet PASS/FAIL line in the result markdown. Observation-only, not a hard gate.

## Renewal-prose accuracy — the dimension v4 explicitly targeted

The new `_check_renewal_prose` machine receipt:

| Scenario | Account | Actual days | v3 said | v4 said | v3 verdict | v4 verdict |
|---|---|---|---|---|---|---|
| S1 | ACC-001 | 58 | "renewal in 60 days" | "renewal in 58 days" | ⚠️ off by 2 | ✅ exact |
| S2 | ACC-002 | 89 | (no numeric) | "renewal in 89 days" | n/a | ✅ exact |
| S3 | ACC-020 | 65 | "Renewal is 68 days away" | (no `account.renewal_date`-cited numeric — see "citation-grammar gap" below) | ⚠️ off by 3 | n/a (test silent) |
| S4 | ACC-019 | 64 | "lock in renewal at 564 days out" | "before renewal in 64 days" | ❌ off by 500 | ✅ exact |
| S5 | ACC-004 | 261 | "Renewal is 261 days away (2027-01-12)" | "Renewal is 261 days away" | ✅ correct | ✅ exact |

**v4 cleanly fixed the day-count hallucination class.** Every bullet that cites `account.renewal_date` and includes a numeric distance now matches the fixture exactly. The `_check_renewal_prose` receipt in `v4.md` confirms 4/4 PASS.

## Objective dimensions (script-checked)

| Dimension | v3 | v4 | Notes |
|---|---|---|---|
| **Citation validity** | 5/5 | 5/5 with caveat | All cited tickets, NPS dates, usage_events ranges, account fields, and health.signals fields resolve to real fixture values across both runs. **Caveat**: v4 introduces a citation form (`usage_window.days_to_renewal`) that isn't in the prompt's formal citation grammar — see "Citation-grammar gap" below. |
| **Schema validity** | 5/5 | 5/5 | `Briefing.model_validate` accepts every output on first parse. Both wrap JSON in a ```json fence; the live-path fence-stripper handles it. |
| **Bullet count** | 5/5 | 5/5 | Both returned exactly 3 bullets per scenario. |
| **Renewal-prose accuracy (live)** | 1/4 (the 261 case only — others off by 2, 3, or 500) | **4/4 exact** | New script-checked dimension introduced by R2 in this cycle. |

## Citation-grammar gap surfaced by this run — needs addressing in v5

The v4 prompt's citation rules (lines 26–34) list five allowed citation forms: `tickets[…]`, `usage_events[…]`, `nps[…]`, `health.signals.<field>`, `account.<field>`. Lines 29, 36, and 42 instruct the LLM to **read** values from `usage_window.*` (specifically `days_to_renewal`, `events_last_7d_start`, `events_last_7d_end`), but those aren't formally permitted as **citation forms**.

The live LLM, reasonably interpreting "use this value from the input", emitted citations like `usage_window.days_to_renewal` in:

- S3 bullet 1 — `["health.signals.usage_decay_pct", "usage_events[…]", "usage_window.days_to_renewal", "account.primary_contact_name"]`
- S3 bullet 3 — `["nps[…]", "health.signals.latest_nps_score", "usage_window.days_to_renewal"]`
- S5 bullet 3 — `["usage_window.days_to_renewal", "account.renewal_date"]`

These citations are *correct in spirit* (the bullets accurately rest on a real precomputed input field) but *out of grammar*. The existing `test_every_citation_resolves_to_a_real_fixture_field` would reject `usage_window.<field>` as "unknown citation form" — but that test only runs against the stub, which doesn't emit that form. So the gap is invisible to current testing.

**Two fix options for v5**:
- **(a)** Extend the citation grammar to formally permit `usage_window.<field>`, and extend the test validator to recognize it. Cleaner — `usage_window.*` are real input fields the LLM is correctly grounding on.
- **(b)** Tighten the prompt to require citing `account.renewal_date` (not `usage_window.days_to_renewal`) for renewal-distance bullets, since the test grammar already permits `account.<field>`. Less work but loses the precision that the bullet rests on the precomputed integer, not the date itself.

Recommendation: **(a)**. The architectural intent is "the LLM cites the field it grounded on"; if we precomputed `days_to_renewal` and the LLM honestly grounds on it, that's a citation worth preserving.

## Subjective dimensions (hand-graded against the rubric)

### Specificity

| Scenario | v3 | v4 | Why |
|---|---|---|---|
| S1 — Multi-signal critical | 4 | 5 | v4 leads with "Schedule immediate call with Mira Petrov" — names the contact (R3 prompt guideline working). v3 ended with "VP Engineering" — generic. v4 also nails the renewal day count exactly. |
| S2 — Single-signal critical | 5 | 5 | Both lead with the abandonment thesis and cite specific tickets. v4 closes by naming Bill Lumbergh + the exact 89-day renewal window. Tie. |
| S3 — Quiet at-risk | 4 | 4 | Both name Alex Morgan. v4 cites `usage_window.days_to_renewal` (out of grammar — see above) but the prose is grounded; v3's "26 months" was outright wrong. Specificity comparable; v4 cleaner on numbers, v3 cleaner on grammar. Tie. |
| S4 — Healthy with renewal soon | 5 | 5 | Both keep `T-1148` cited. v4 names Casey Park (R3 working) where v3 was generic. v4's day-count is correct (64 vs v3's 564). v4 wins on accuracy, v3 ties on density. Tie. |
| S5 — Pure healthy | 5 | 5 | v4 names Taylor Nguyen + an explicit "case study / advocacy" play; v3 had similar concrete expansion language. Tie. |
| **Mean** | **4.6** | **4.8** | |

### Action orientation

| Scenario | v3 | v4 | Why |
|---|---|---|---|
| S1 | 4 | 5 | **v4 recovers the v2 strength here.** "Schedule immediate call with Mira Petrov" leads the briefing — named contact, bounded action. v3's "Schedule urgent triage call with VP Engineering" was generic. |
| S2 | 5 | 5 | Both close with "secure a recovery call with Bill Lumbergh". Tie. |
| S3 | 4 | 5 | v4: "schedule an immediate call with Alex Morgan to understand blockers before renewal in 65 days" — named contact + bounded window. v3 said "contact Alex Morgan immediately" — comparable but v4 is sharper on the deadline. |
| S4 | 5 | 5 | Both anchor the ticket-resolve action to "before renewal". Tie. |
| S5 | 5 | 5 | Both name Taylor Nguyen + a concrete expansion ask. Tie. |
| **Mean** | **4.6** | **5.0** | |

## Verdict

| | v3 | v4 |
|---|---|---|
| Citation validity | 5.0 | 5.0 (with grammar caveat above) |
| Schema validity | 5.0 | 5.0 |
| Bullet count | 5.0 | 5.0 |
| Specificity | 4.6 | **4.8** |
| Action orientation | 4.6 | **5.0** |
| Renewal-prose accuracy | 1/4 exact | **4/4 exact** |

**v4 is a defensible bump on every dimension** — ties on the three structural objective dimensions, gains on both subjective dimensions, and cleanly wins the new live-path renewal-prose dimension R2 introduced this cycle. v4 also recovers the v3 action-orientation regression on S1 and S3 (named-contact preference from R3 doing real work).

The one new gap surfaced by the run — `usage_window.<field>` citation grammar — is real and should be addressed in v5 before another bump, but it's a methodology-rigor issue, not a correctness regression. The bullets that cite that form are accurately grounded on real input fields.

## Where v4 still loses

Honestly, there's no clean v4 loss in this run. The closest thing is the citation-grammar gap above, but that's a methodology slack to tighten in v5, not a v4 regression. v4 is the strongest prompt this project has shipped to date by every dimension graded here.

## v5 targets, in priority order

1. **Close the citation-grammar gap.** Extend the prompt's citation rules to formally permit `usage_window.<field>` (and update `test_every_citation_resolves_to_a_real_fixture_field` to recognize it). Otherwise v4's outputs technically violate the grammar the README points at, even though they're behaviorally correct. Cheap fix.
2. **Promote `_check_renewal_prose` from observation to gate (in eval, not pytest).** Right now it emits PASS/FAIL lines but doesn't change exit code. A `--strict` flag that returns non-zero on any FAIL would make the eval block accidentally-shipped regressions when run pre-commit on a prompt bump. Do not move this into pytest — paid-API rule still applies.
3. **Consider precomputing other distance fields the LLM still computes.** v4 cleaned up `days_to_renewal` but the LLM still does week-over-week percentage math on usage. If the same hallucination class appears there, the same fix applies.

## Reproducibility

```bash
python scripts/run_eval.py --prompts evals/old_prompts/briefing.v3.md --label v3
python scripts/run_eval.py --prompts prompts/briefing.md --label v4
```

This run reused `v3.md` from the prior cycle (payload code change between v3 and v4 is additive — `days_to_renewal` is a new field — so v3 raw outputs are still representative; the prompt is what changed). One paid run this cycle, ~$0.025. Hand-graded numbers above are not auto-regenerated; re-grade if either prompt changes.
