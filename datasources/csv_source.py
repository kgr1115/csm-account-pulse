"""CsvDataSource — read account-shaped data from four CSV files in one directory.

Layout:
    <dir>/accounts.csv
    <dir>/usage_events.csv
    <dir>/tickets.csv
    <dir>/nps_responses.csv

Schema is documented in `docs/datasources/csv.md`. Required-column validation
fires before Pydantic parsing so a missing column produces a user-readable
ValueError naming the column and the file path — not a Pydantic ValidationError
traceback. Extra columns are silently ignored. Empty optional fields become None.

Stdlib only — no new dependency in requirements.txt.
"""

from __future__ import annotations

import csv
from datetime import date, datetime
from functools import cached_property
from pathlib import Path

from datasource import DataSource
from models import Account, NpsResponse, Ticket, UsageEvent


DEFAULT_CSV_DIR = Path(__file__).parent.parent / "data" / "csv"


_ACCOUNT_REQUIRED = (
    "id",
    "name",
    "industry",
    "employee_count",
    "plan_tier",
    "arr_usd",
    "contract_start",
    "renewal_date",
    "csm_owner",
    "primary_contact_name",
    "primary_contact_title",
)
_USAGE_REQUIRED = ("account_id", "timestamp", "event_type", "user_id")
_USAGE_OPTIONAL = ("feature",)
_TICKET_REQUIRED = (
    "id",
    "account_id",
    "created_at",
    "severity",
    "status",
    "subject",
    "category",
)
_TICKET_OPTIONAL = ("resolved_at",)
_NPS_REQUIRED = ("account_id", "submitted_at", "score")
_NPS_OPTIONAL = ("comment",)


def _parse_date(value: str, *, file: Path, row_index: int, field: str) -> date:
    s = value.strip()
    try:
        return date.fromisoformat(s)
    except ValueError as exc:
        raise ValueError(
            f"Malformed date in {file} row {row_index} field '{field}': {value!r} "
            f"(expected YYYY-MM-DD)"
        ) from exc


def _parse_datetime(value: str, *, file: Path, row_index: int, field: str) -> datetime:
    s = value.strip()
    # date.fromisoformat in 3.11+ accepts both date-only and full datetime via
    # datetime.fromisoformat. Accept both YYYY-MM-DD and ISO 8601 datetime forms.
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    try:
        d = date.fromisoformat(s)
        return datetime.combine(d, datetime.min.time())
    except ValueError as exc:
        raise ValueError(
            f"Malformed datetime in {file} row {row_index} field '{field}': {value!r} "
            f"(expected ISO 8601 or YYYY-MM-DD)"
        ) from exc


def _optional(value: str | None) -> str | None:
    """Empty CSV cells become None for optional fields."""
    if value is None:
        return None
    s = value.strip()
    return s if s else None


def _read_csv(path: Path, required: tuple[str, ...]) -> tuple[list[dict[str, str]], Path]:
    """Read a CSV, validating that all required columns are present BEFORE any
    row-level parsing. Returns (rows, path) where rows is a list of dicts.

    Missing required column → ValueError naming the column and path.
    Extra columns → silently kept; the row-builder ignores them.
    """
    if not path.exists():
        raise ValueError(f"CSV file not found: {path}")
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        missing = [c for c in required if c not in fieldnames]
        if missing:
            raise ValueError(
                f"Missing required column(s) {missing} in {path}. "
                f"Found columns: {list(fieldnames)}"
            )
        rows = list(reader)
    return rows, path


class CsvDataSource(DataSource):
    """Read accounts, usage events, tickets, and NPS responses from CSV files.

    The `csv_dir` arg points at a directory containing the four required CSVs.
    Defaults to `<repo>/data/csv/`. The directory itself is gitignored — real
    user CSVs must never land in the repo.
    """

    def __init__(self, csv_dir: Path | str | None = None) -> None:
        self.csv_dir = Path(csv_dir) if csv_dir is not None else DEFAULT_CSV_DIR

    @cached_property
    def _accounts(self) -> list[Account]:
        rows, path = _read_csv(self.csv_dir / "accounts.csv", _ACCOUNT_REQUIRED)
        out: list[Account] = []
        for i, row in enumerate(rows, start=2):  # row 1 is the header
            payload = {
                "id": row["id"],
                "name": row["name"],
                "industry": row["industry"],
                "employee_count": int(row["employee_count"]),
                "plan_tier": row["plan_tier"],
                "arr_usd": int(row["arr_usd"]),
                "contract_start": _parse_date(
                    row["contract_start"], file=path, row_index=i, field="contract_start"
                ),
                "renewal_date": _parse_date(
                    row["renewal_date"], file=path, row_index=i, field="renewal_date"
                ),
                "csm_owner": row["csm_owner"],
                "primary_contact_name": row["primary_contact_name"],
                "primary_contact_title": row["primary_contact_title"],
            }
            out.append(Account.model_validate(payload))
        return out

    @cached_property
    def _usage_events(self) -> dict[str, list[UsageEvent]]:
        rows, path = _read_csv(self.csv_dir / "usage_events.csv", _USAGE_REQUIRED)
        result: dict[str, list[UsageEvent]] = {}
        for i, row in enumerate(rows, start=2):
            payload = {
                "account_id": row["account_id"],
                "timestamp": _parse_datetime(
                    row["timestamp"], file=path, row_index=i, field="timestamp"
                ),
                "event_type": row["event_type"],
                "feature": _optional(row.get("feature")),
                "user_id": row["user_id"],
            }
            event = UsageEvent.model_validate(payload)
            result.setdefault(event.account_id, []).append(event)
        return result

    @cached_property
    def _tickets(self) -> dict[str, list[Ticket]]:
        rows, path = _read_csv(self.csv_dir / "tickets.csv", _TICKET_REQUIRED)
        result: dict[str, list[Ticket]] = {}
        for i, row in enumerate(rows, start=2):
            resolved_raw = _optional(row.get("resolved_at"))
            payload = {
                "id": row["id"],
                "account_id": row["account_id"],
                "created_at": _parse_datetime(
                    row["created_at"], file=path, row_index=i, field="created_at"
                ),
                "resolved_at": (
                    _parse_datetime(resolved_raw, file=path, row_index=i, field="resolved_at")
                    if resolved_raw is not None
                    else None
                ),
                "severity": row["severity"],
                "status": row["status"],
                "subject": row["subject"],
                "category": row["category"],
            }
            ticket = Ticket.model_validate(payload)
            result.setdefault(ticket.account_id, []).append(ticket)
        return result

    @cached_property
    def _nps(self) -> dict[str, list[NpsResponse]]:
        rows, path = _read_csv(self.csv_dir / "nps_responses.csv", _NPS_REQUIRED)
        result: dict[str, list[NpsResponse]] = {}
        for i, row in enumerate(rows, start=2):
            payload = {
                "account_id": row["account_id"],
                "submitted_at": _parse_datetime(
                    row["submitted_at"], file=path, row_index=i, field="submitted_at"
                ),
                "score": int(row["score"]),
                "comment": _optional(row.get("comment")),
            }
            response = NpsResponse.model_validate(payload)
            result.setdefault(response.account_id, []).append(response)
        return result

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
