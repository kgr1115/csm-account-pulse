"""DataSource interface — the load-bearing boundary.

Every read of customer-shaped data flows through here. The README's
"What it would take to swap in Salesforce" pitch lives or dies on this
interface remaining the only doorway. Reading raw JSON from data/fixtures/
outside FixtureDataSource invalidates that pitch — see CLAUDE.md.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import date, datetime
from functools import cached_property
from pathlib import Path

from models import Account, NpsResponse, Ticket, UsageEvent


FIXTURES_DIR = Path(__file__).parent / "data" / "fixtures"


class DataSource(ABC):
    @abstractmethod
    def list_accounts(self) -> list[Account]: ...

    @abstractmethod
    def get_usage_events(self, account_id: str, since: date | None = None) -> list[UsageEvent]: ...

    @abstractmethod
    def get_tickets(self, account_id: str) -> list[Ticket]: ...

    @abstractmethod
    def get_nps_responses(self, account_id: str) -> list[NpsResponse]: ...


class FixtureDataSource(DataSource):
    """Reads from data/fixtures/. The only DataSource implementation."""

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self.fixtures_dir = fixtures_dir or FIXTURES_DIR

    @cached_property
    def _accounts(self) -> list[Account]:
        raw = json.loads((self.fixtures_dir / "accounts.json").read_text())
        return [Account.model_validate(a) for a in raw]

    @cached_property
    def _usage_events(self) -> dict[str, list[UsageEvent]]:
        usage_dir = self.fixtures_dir / "usage"
        result: dict[str, list[UsageEvent]] = {}
        for path in sorted(usage_dir.glob("*.jsonl")):
            account_id = path.stem
            events: list[UsageEvent] = []
            for line in path.read_text().splitlines():
                if not line.strip():
                    continue
                e = json.loads(line)
                events.append(UsageEvent.model_validate({**e, "account_id": account_id}))
            result[account_id] = events
        return result

    @cached_property
    def _tickets(self) -> dict[str, list[Ticket]]:
        raw = json.loads((self.fixtures_dir / "tickets.json").read_text())
        return {
            account_id: [Ticket.model_validate(t) for t in tickets]
            for account_id, tickets in raw.items()
        }

    @cached_property
    def _nps(self) -> dict[str, list[NpsResponse]]:
        raw = json.loads((self.fixtures_dir / "nps_responses.json").read_text())
        return {
            account_id: [NpsResponse.model_validate(n) for n in responses]
            for account_id, responses in raw.items()
        }

    def list_accounts(self) -> list[Account]:
        return list(self._accounts)

    def get_usage_events(self, account_id: str, since: date | None = None) -> list[UsageEvent]:
        events = self._usage_events.get(account_id, [])
        if since is None:
            return list(events)
        cutoff = datetime.combine(since, datetime.min.time())
        return [e for e in events if e.timestamp >= cutoff]

    def get_tickets(self, account_id: str) -> list[Ticket]:
        return list(self._tickets.get(account_id, []))

    def get_nps_responses(self, account_id: str) -> list[NpsResponse]:
        return list(self._nps.get(account_id, []))
