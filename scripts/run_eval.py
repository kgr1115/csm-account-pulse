"""Briefing-prompt eval runner.

Walks the scenarios in evals/scenarios.json, calls the live Anthropic model
once per (scenario, prompt-file) pair, and writes a structured markdown
result file to evals/results/{label}.md for hand-grading.

Usage:
    python scripts/run_eval.py --prompts prompts/briefing.md --label v2
    python scripts/run_eval.py --prompts evals/old_prompts/briefing.v1.md --label v1

Requires ANTHROPIC_API_KEY in the environment (or .env via python-dotenv).
Costs roughly $0.05 per full run with the default Haiku model.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

from briefing import _state_to_llm_payload, _resolve_model, MAX_TOKENS
from datasource import FixtureDataSource
from health import compute_health
from models import AccountState, Briefing


SCENARIOS_PATH = REPO_ROOT / "evals" / "scenarios.json"
RESULTS_DIR = REPO_ROOT / "evals" / "results"
TODAY = date(2026, 4, 26)
USAGE_LOOKBACK_DAYS = 30


def _build_state(account_id: str) -> AccountState:
    ds = FixtureDataSource()
    a = next(x for x in ds.list_accounts() if x.id == account_id)
    events_recent = ds.get_usage_events(a.id, since=TODAY - timedelta(days=USAGE_LOOKBACK_DAYS))
    events_all = ds.get_usage_events(a.id)
    tickets = ds.get_tickets(a.id)
    nps = ds.get_nps_responses(a.id)
    health = compute_health(a, events_all, tickets, nps, TODAY)
    return AccountState(
        account=a,
        health=health,
        recent_usage_events=events_recent,
        tickets=tickets,
        nps_responses=nps,
    )


def _resolve_dynamic_account(scenario: dict, ds: FixtureDataSource) -> str:
    """Resolve scenarios that pick an account at runtime (e.g. 'first healthy with renewal in <90d')."""
    aid = scenario.get("account_id")
    if aid:
        return aid
    if scenario["id"] == "S4":
        for a in ds.list_accounts():
            h = compute_health(a, ds.get_usage_events(a.id), ds.get_tickets(a.id), ds.get_nps_responses(a.id), TODAY)
            if h.bucket.value == "Healthy" and 0 <= (a.renewal_date - TODAY).days <= 90:
                return a.id
    if scenario["id"] == "S5":
        for a in ds.list_accounts():
            h = compute_health(a, ds.get_usage_events(a.id), ds.get_tickets(a.id), ds.get_nps_responses(a.id), TODAY)
            if h.bucket.value == "Healthy" and (a.renewal_date - TODAY).days > 180:
                return a.id
    raise SystemExit(f"Could not resolve dynamic account for scenario {scenario['id']}")


def _call_anthropic(prompt: str, payload: dict, api_key: str) -> tuple[str, dict | None, str | None]:
    """Returns (raw_text, parsed_briefing_dict_or_None, error_or_None)."""
    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)
    resp = client.messages.create(
        model=_resolve_model(),
        max_tokens=MAX_TOKENS,
        system=prompt,
        messages=[{
            "role": "user",
            "content": (
                "Here is the account JSON. Return ONLY the briefing JSON object as specified.\n\n"
                + json.dumps(payload, default=str)
            ),
        }],
    )
    text = "".join(b.text for b in resp.content if hasattr(b, "text")).strip()
    cleaned = text
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.rsplit("```", 1)[0].strip()
    try:
        parsed = json.loads(cleaned)
        Briefing.model_validate({**parsed, "generated_by": "anthropic"})
        return text, parsed, None
    except Exception as e:
        return text, None, f"{type(e).__name__}: {e}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompts", required=True, type=Path, help="Path to the prompt file")
    parser.add_argument("--label", required=True, help="Short label for this run, e.g. 'v2'")
    parser.add_argument("--dry-run", action="store_true", help="Skip the API call; report what would happen")
    args = parser.parse_args()

    load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key and not args.dry_run:
        raise SystemExit("ANTHROPIC_API_KEY not set. Use --dry-run to preview without calling the API.")

    if not args.prompts.exists():
        raise SystemExit(f"Prompt file not found: {args.prompts}")
    prompt = args.prompts.read_text(encoding="utf-8")

    scenarios = json.loads(SCENARIOS_PATH.read_text())["scenarios"]
    ds = FixtureDataSource()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"{args.label}.md"

    lines: list[str] = [
        f"# Eval results — label `{args.label}`",
        "",
        f"- Prompt: `{args.prompts}`",
        f"- Model: `{_resolve_model()}`",
        f"- Fixture date anchor: {TODAY.isoformat()}",
        "- Mode: " + ("dry-run (no API calls)" if args.dry_run else "live"),
        "",
        "Hand-grade Specificity and Action-orientation 1-5 for each scenario after the run completes.",
        "",
    ]

    for scenario in scenarios:
        account_id = _resolve_dynamic_account(scenario, ds)
        state = _build_state(account_id)
        payload = _state_to_llm_payload(state, today=TODAY)

        lines.append(f"## {scenario['id']} — {scenario['label']}")
        lines.append("")
        lines.append(f"- Account: `{account_id}` ({state.account.name})")
        lines.append(f"- Expected bucket: {scenario['expected_bucket']}, actual: {state.health.bucket.value}")
        lines.append(f"- What it stresses: {scenario['what_it_stresses']}")
        lines.append("")

        if args.dry_run:
            lines.append("_(dry-run; no API call made)_")
            lines.append("")
            continue

        raw, parsed, err = _call_anthropic(prompt, payload, api_key)
        lines.append("### Raw output")
        lines.append("```json")
        lines.append(raw)
        lines.append("```")
        lines.append("")

        if err:
            lines.append(f"**Schema validity:** FAIL ({err})")
        else:
            lines.append("**Schema validity:** PASS")
            lines.append(f"**Bullet count:** {len(parsed.get('bullets', []))}")
            cite_counts = [len(b.get("citations", [])) for b in parsed.get("bullets", [])]
            lines.append(f"**Citations per bullet:** {cite_counts}")

        lines.append("")
        lines.append("**Specificity (1-5):** _grade me_")
        lines.append("**Action-orientation (1-5):** _grade me_")
        lines.append("")
        lines.append("---")
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
