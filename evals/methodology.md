# Briefing eval methodology

The README claims the prompt is "bumped on any wording change." This file is the receipt: how a bump is graded so the bump can be defended.

## What's being evaluated

The artifact under test is `prompts/briefing.md` — the system prompt sent to the Anthropic API by `_live_briefing` in `briefing.py`. The deterministic stub does **not** read the prompt, so eval is meaningful only against the live model.

## The held-out scenario set

Five fixture accounts span the dashboard's full output range. Each one stresses a different facet the prompt has to handle.

| Scenario | Fixture | Bucket | What it stresses |
|---|---|---|---|
| S1 — Multi-signal critical | `ACC-001` (Globex Robotics) | Critical | Renewal in 58 days, 3 open H/C tickets, NPS detractor, deep usage decay. The prompt must prioritize and not enumerate every signal — picking the right 3 is the test. |
| S2 — Single-signal critical | `ACC-002` (Initech Manufacturing) | Critical | Near-zero usage dominates; tickets and NPS are corroborating, not independent. Tests whether the prompt over-weights ticket count when the real story is abandonment. |
| S3 — Quiet at-risk | `ACC-020` (procedural at-risk) | At-Risk | At-risk by health score but with no obvious five-alarm signal — Watch-bordering. Tests whether the prompt finds a defensible angle without inventing one. |
| S4 — Healthy with renewal soon | the first Healthy account whose renewal is within 90 days | Healthy | Tests that "healthy" briefings don't invent problems; should pivot to expansion / renewal motion language. |
| S5 — Pure healthy | a Healthy account with renewal >180 days out | Healthy | Tests that briefings handle "nothing to do" gracefully without padding the bullets with platitudes. |

The five accounts are pinned in `evals/scenarios.json`. The selection is deterministic from the fixture seed; if the fixture generator is rerun, the IDs may shift and the scenarios file should be regenerated.

## Grading rubric

Each (scenario, prompt-version) pair gets graded across five dimensions on a 1–5 scale. The first three are objective (a script can check them); the last two require human judgment.

| Dimension | Objective? | What 5/5 looks like | What 1/5 looks like |
|---|---|---|---|
| **Citation validity** | yes | Every citation resolves to a real fixture field (passes `test_every_citation_resolves_to_a_real_fixture_field`). | Cites `tickets[T-9999]` or invents a date. |
| **Schema validity** | yes | Returns valid JSON parseable into `Briefing` on first try. | Code-fenced, missing fields, malformed. |
| **Bullet count** | yes | Exactly 3 bullets, each ≥ 1 citation. | Wrong count or uncited bullet. |
| **Specificity** | no | Bullets reference specific tickets, dates, percentages, days-to-renewal. | "This account needs attention" — generic. |
| **Action orientation** | no | The CSM knows what to do this week — call X, resolve Y, send Z. | Describes the situation without telling the CSM what to do. |

A prompt version's score is the per-dimension mean across the five scenarios. A bump from v_n to v_{n+1} is defensible if v_{n+1} ≥ v_n on every dimension AND strictly better on at least one.

## Why no v1-vs-v2 numbers in this repo (yet)

The v1 → v2 bump happened during the project's first improvement cycle and was not eval-gated. v2 is the current snapshot; v1 lives in git history (commit `2413eec` in the private fork — the bootstrap). To produce numbers, restore v1 to a separate file and run the eval — see "How to run a comparison" below.

The next bump (v2 → v3) should land alongside an eval result file in this directory.

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

A full run is 5 scenarios × N prompts × 1 Haiku call ≈ 5N calls, currently <$0.05/run with the default model (`claude-haiku-4-5-20251001`). Running the eval is cheap enough that there's no excuse not to gate prompt bumps on it.

## Honesty about this artifact's current state

This file describes the methodology and the runner. As of the commit that introduced this directory, **no live runs have been done** — neither `evals/results/v1.md` nor `evals/results/v2.md` exists yet. That asymmetry is the point: the eval discipline is the artifact a recruiter is looking for, and the first result file is the next prompt change's burden.
