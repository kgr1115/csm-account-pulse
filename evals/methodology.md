# Briefing eval methodology

The README claims the prompt is "bumped on any wording change." This file is the receipt: how a bump is graded so the bump can be defended.

## What's being evaluated

The artifact under test is `prompts/briefing.md` — the system prompt sent to the Anthropic API by `_live_briefing` in `briefing.py`. The deterministic stub does **not** read the prompt, so eval is meaningful only against the live model.

## The held-out scenario set

Twelve fixture accounts span the dashboard's full output range. Each one stresses a different facet the prompt has to handle. S1–S5 are drawn from the seed-generated fixture set; S6–S12 are hand-crafted accounts authored to cover shapes the seed didn't produce (see "Scenario expansion policy" below).

| Scenario | Fixture | Bucket | What it stresses |
|---|---|---|---|
| S1 — Multi-signal critical | `ACC-001` (Globex Robotics) | Critical | Renewal in 58 days, 3 open H/C tickets, NPS detractor, deep usage decay. The prompt must prioritize and not enumerate every signal — picking the right 3 is the test. |
| S2 — Single-signal critical | `ACC-002` (Initech Manufacturing) | Critical | Near-zero usage dominates; tickets and NPS are corroborating, not independent. Tests whether the prompt over-weights ticket count when the real story is abandonment. |
| S3 — Quiet at-risk | `ACC-020` (procedural at-risk) | At-Risk | At-risk by health score but with no obvious five-alarm signal — Watch-bordering. Tests whether the prompt finds a defensible angle without inventing one. |
| S4 — Healthy with renewal soon | the first Healthy account whose renewal is within 90 days | Healthy | Tests that "healthy" briefings don't invent problems; should pivot to expansion / renewal motion language. |
| S5 — Pure healthy | a Healthy account with renewal >180 days out | Healthy | Tests that briefings handle "nothing to do" gracefully without padding the bullets with platitudes. |
| S6 — No NPS data at all | `ACC-051` (Cyberdyne Trust) | Healthy | Zero NPS responses on the account. Tests whether the prompt hallucinates NPS signals or grounds the briefing only in usage and tickets. |
| S7 — High ticket volume, zero usage decay | `ACC-052` (Tyrell Health Networks) | Healthy | Eight tickets in 30 days but flat usage and the lone open ticket is medium severity. Tests whether the prompt over-weights ticket count when usage and NPS are fine. |
| S8 — Long renewal horizon, all green | `ACC-053` (Stark Renewables) | Healthy | Renewal 18+ months out, NPS promoter, no tickets, growing usage. Tests whether the prompt invents urgency or stays genuinely quiet. |
| S9 — Renewal in 7 days, healthy | `ACC-054` (Wonka Confections) | Healthy | Imminent renewal but otherwise quiet. Pressure-tests the renewal-prose accuracy rules — surfaces "renewal is imminent" without fabricating risk. |
| S10 — Mixed severity, none open H/C | `ACC-055` (Soylent Foods Group) | Healthy | Five tickets in 30 days spanning low/medium/high severity, all resolved. Tests whether `ticket_volume_30d` gets over-weighted vs. `open_high_severity_tickets`. |
| S11 — Single NPS detractor | `ACC-056` (Aperture Field Services) | Watch | One NPS score of 2, otherwise quiet. Tests whether a single detractor alone is enough to surface as a bullet without inventing supporting signals. |
| S12 — New account, thin window | `ACC-057` (Pied Piper Compression) | Healthy | Contract started ~3 weeks ago; thin usage window, no NPS yet, one resolved ticket. Tests whether the prompt hallucinates baseline data or cites the thin window explicitly. |

The twelve accounts are pinned in `evals/scenarios.json`. S1–S5 are deterministic from the fixture seed; if the seed-generator is rerun the IDs may shift and the scenarios file should be regenerated. S6–S12 are hand-crafted, live in the reserved ACC-051..ACC-070 range, and do not move when the seed regenerates.

## Scenario expansion policy

The original five scenarios were drawn from the seed-generated fixture set (`scripts/generate_fixtures.py` SEED=26042026, accounts ACC-001..ACC-050). That set is uniform — the seed produces a particular distribution of usage, tickets, and NPS shapes — so several real-world account shapes were missing from coverage: accounts with no NPS responses, accounts with high ticket volume but no usage decay, accounts on long renewal horizons with all signals green, accounts with imminent renewals on healthy footing, accounts with mixed-severity-but-resolved tickets, accounts with a single NPS detractor as the only signal, and brand-new accounts with thin usage windows. Hand-crafting fixture accounts to cover those shapes is the only way to test prompt behavior against them.

To keep the seed-generated set reproducible while admitting hand-crafted additions, the account ID range is partitioned:

- `ACC-001`..`ACC-050` — seed-generated. Reproducible by running `scripts/generate_fixtures.py` against the pinned seed.
- `ACC-051`..`ACC-070` — **reserved for hand-crafted eval scenarios**. Do not reuse these IDs in the seed generator; do not renumber existing seed-generated accounts into this range. New eval scenarios that need a fixture shape the seed doesn't produce go here.

When adding a new scenario, append a fixture account in the reserved range, append the scenario entry to `evals/scenarios.json` with the next `S<n>` ID, and document the archetype in the table above. Bumping the prompt against the expanded set is no different from bumping against the original five — same rubric, same defensibility test (ties on every dimension and wins on at least one).

## Grading rubric

Each (scenario, prompt-version) pair gets graded across five dimensions on a 1–5 scale. The first three are objective (a script can check them); the last two require human judgment.

| Dimension | Objective? | What 5/5 looks like | What 1/5 looks like |
|---|---|---|---|
| **Citation validity** | yes | Every citation resolves to a real fixture field (passes `test_every_citation_resolves_to_a_real_fixture_field`). | Cites `tickets[T-9999]` or invents a date. |
| **Schema validity** | yes | Returns valid JSON parseable into `Briefing` on first try. | Code-fenced, missing fields, malformed. |
| **Bullet count** | yes | Exactly 3 bullets, each ≥ 1 citation. | Wrong count or uncited bullet. |
| **Specificity** | no | Bullets reference specific tickets, dates, percentages, days-to-renewal. | "This account needs attention" — generic. |
| **Action orientation** | no | The CSM knows what to do this week — call X, resolve Y, send Z. | Describes the situation without telling the CSM what to do. |

A prompt version's score is the per-dimension mean across the twelve scenarios. A bump from v_n to v_{n+1} is defensible if v_{n+1} ≥ v_n on every dimension AND strictly better on at least one.

## v1-vs-v2 numbers — already on disk

The v1 → v2 bump shipped before the eval discipline existed; the comparison was retrofitted afterward and lives at `evals/results/v1_vs_v2.md` (raw outputs: `v1.md`, `v2.md`). v2 is defensible per the rubric (ties on the three objective dimensions, +0.4 specificity, +0.6 action-orientation), with an honest "where v2 still loses" callout for the S4 healthy-with-renewal-soon regression.

That retrofit is the floor. The next bump (v2 → v3) should land with its own result file in this directory, run forward — not retrofitted. The test added in `test_renewal_prose_matches_cited_renewal_date` is the regression guardrail closing the renewal-distance hallucination both prior versions surfaced.

## How to run a comparison

```bash
# 1. Set ANTHROPIC_API_KEY in .env or your shell.
# 2. Run the eval script. It walks the scenarios in evals/scenarios.json,
#    calls the live model for each (scenario, prompt) pair, and writes a
#    structured result file to evals/results/.
python scripts/run_eval.py --prompts prompts/briefing.md --label v2
python scripts/run_eval.py --prompts evals/old_prompts/briefing.v1.md --label v1
# 3. Hand-grade specificity and action-orientation in the produced markdown.
# 4. Commit the result file alongside the prompt change.
```

`run_eval.py` does **not** auto-grade specificity or action-orientation — those are intentionally human-judgment to keep the bar honest.

## Cost note

A full run is 12 scenarios × N prompts × 1 Haiku call ≈ 12N calls, currently $0.06–0.10 per run with the default model (`claude-haiku-4-5-20251001`). Running the eval is still cheap enough that there's no excuse not to gate prompt bumps on it.

## Honesty about this artifact's current state

This file describes the methodology and the runner; `evals/results/v1_vs_v2.md` is the first result file, written against the live model with hand-graded subjective dimensions. The retrofit is documented in that file's "Methodology asymmetry" section so the asymmetry is visible rather than hidden. The discipline now runs forward: a v3 bump should ship with its own result file written before merge, not after.
