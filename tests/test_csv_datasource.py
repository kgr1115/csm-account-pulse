"""CsvDataSource contract tests.

The required matrix from the architect's verdict:
  1.  0-row CSV → empty lists, no raise
  2.  1-row CSV round-trip on all four methods
  3.  5-row committed sample round-trip with field assertions
  4.  Missing required column → ValueError naming the column and file path
  5.  Extra/unknown columns silently ignored
  6.  `since` filter on get_usage_events — two cutoff dates
  7.  Malformed date → ValueError naming row + field
  8.  Path-with-spaces in directory argument
  9.  briefing_render_does_not_raise — full path through stub LLM, no raise
 10.  CsvDataSource subclasses DataSource and returns typed Account list
 11.  Sample CSVs are referentially consistent on account-ids
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from datasource import DataSource
from datasources import CsvDataSource
from models import Account, NpsResponse, Ticket, UsageEvent


SAMPLES_DIR = Path(__file__).parent.parent / "data" / "samples"


# Column headers reused across the synthetic CSV tests.
ACCOUNT_HEADER = (
    "id,name,industry,employee_count,plan_tier,arr_usd,contract_start,"
    "renewal_date,csm_owner,primary_contact_name,primary_contact_title"
)
USAGE_HEADER = "account_id,timestamp,event_type,feature,user_id"
TICKET_HEADER = "id,account_id,created_at,resolved_at,severity,status,subject,category"
NPS_HEADER = "account_id,submitted_at,score,comment"


def _write_four_csvs(
    target: Path,
    *,
    accounts: str,
    usage: str,
    tickets: str,
    nps: str,
) -> None:
    target.mkdir(parents=True, exist_ok=True)
    (target / "accounts.csv").write_text(accounts, encoding="utf-8")
    (target / "usage_events.csv").write_text(usage, encoding="utf-8")
    (target / "tickets.csv").write_text(tickets, encoding="utf-8")
    (target / "nps_responses.csv").write_text(nps, encoding="utf-8")


# --- 1. Zero-row CSV ----------------------------------------------------------


def test_zero_row_csvs_return_empty_lists(tmp_path: Path) -> None:
    _write_four_csvs(
        tmp_path,
        accounts=ACCOUNT_HEADER + "\n",
        usage=USAGE_HEADER + "\n",
        tickets=TICKET_HEADER + "\n",
        nps=NPS_HEADER + "\n",
    )
    ds = CsvDataSource(tmp_path)
    assert ds.list_accounts() == []
    assert ds.get_usage_events("ACC-ANY") == []
    assert ds.get_tickets("ACC-ANY") == []
    assert ds.get_nps_responses("ACC-ANY") == []


# --- 2. One-row round-trip ----------------------------------------------------


def test_one_row_round_trip(tmp_path: Path) -> None:
    accounts = (
        ACCOUNT_HEADER
        + "\n"
        + "ACC-T1,One Co,Tech,42,Pro,84000,2025-01-15,2026-12-01,"
        "Owner,Contact,VP Engineering\n"
    )
    usage = (
        USAGE_HEADER
        + "\n"
        + "ACC-T1,2026-04-20T09:00:00,session_start,dashboard,u-ACC-T1-1\n"
    )
    tickets = (
        TICKET_HEADER
        + "\n"
        + "T-1,ACC-T1,2026-04-21T10:00:00,,high,open,Bulk import 500,bug\n"
    )
    nps = NPS_HEADER + "\n" + "ACC-T1,2026-04-15T14:00:00,9,Great product\n"
    _write_four_csvs(tmp_path, accounts=accounts, usage=usage, tickets=tickets, nps=nps)

    ds = CsvDataSource(tmp_path)

    accs = ds.list_accounts()
    assert len(accs) == 1
    assert accs[0].id == "ACC-T1"
    assert accs[0].name == "One Co"
    assert accs[0].employee_count == 42
    assert accs[0].arr_usd == 84000
    assert accs[0].contract_start == date(2025, 1, 15)
    assert accs[0].renewal_date == date(2026, 12, 1)

    events = ds.get_usage_events("ACC-T1")
    assert len(events) == 1
    assert events[0].event_type == "session_start"
    assert events[0].feature == "dashboard"

    ts = ds.get_tickets("ACC-T1")
    assert len(ts) == 1
    assert ts[0].id == "T-1"
    assert ts[0].severity == "high"
    assert ts[0].resolved_at is None

    nps_list = ds.get_nps_responses("ACC-T1")
    assert len(nps_list) == 1
    assert nps_list[0].score == 9
    assert nps_list[0].comment == "Great product"


# --- 3. Five-row committed sample round-trip ----------------------------------


def test_five_row_samples_round_trip() -> None:
    ds = CsvDataSource(SAMPLES_DIR)

    accs = ds.list_accounts()
    assert len(accs) == 5
    assert all(isinstance(a, Account) for a in accs)
    assert {a.id for a in accs} == {f"SAMPLE-00{i}" for i in range(1, 6)}
    assert all(a.csm_owner for a in accs)  # at least one field non-empty

    for account_id in (f"SAMPLE-00{i}" for i in range(1, 6)):
        events = ds.get_usage_events(account_id)
        assert len(events) == 1
        assert all(isinstance(e, UsageEvent) for e in events)
        assert events[0].account_id == account_id

        tickets = ds.get_tickets(account_id)
        assert len(tickets) == 1
        assert all(isinstance(t, Ticket) for t in tickets)
        assert tickets[0].account_id == account_id

        nps = ds.get_nps_responses(account_id)
        assert len(nps) == 1
        assert all(isinstance(n, NpsResponse) for n in nps)
        assert 0 <= nps[0].score <= 10


# --- 4. Missing required column → ValueError ---------------------------------


def test_missing_required_column_raises_with_path_and_column(tmp_path: Path) -> None:
    bad_header = ACCOUNT_HEADER.replace("renewal_date,", "")
    _write_four_csvs(
        tmp_path,
        accounts=bad_header + "\n",
        usage=USAGE_HEADER + "\n",
        tickets=TICKET_HEADER + "\n",
        nps=NPS_HEADER + "\n",
    )
    ds = CsvDataSource(tmp_path)
    with pytest.raises(ValueError) as exc_info:
        ds.list_accounts()
    msg = str(exc_info.value)
    assert "renewal_date" in msg
    assert "accounts.csv" in msg


# --- 5. Extra/unknown columns silently ignored -------------------------------


def test_extra_columns_are_silently_ignored(tmp_path: Path) -> None:
    accounts = (
        ACCOUNT_HEADER
        + ",internal_notes,sf_id\n"
        + "ACC-X,Xtra Co,Tech,10,Starter,12000,2025-01-01,2026-06-01,"
        "Owner,Contact,VP,ignored_note,001abc\n"
    )
    _write_four_csvs(
        tmp_path,
        accounts=accounts,
        usage=USAGE_HEADER + "\n",
        tickets=TICKET_HEADER + "\n",
        nps=NPS_HEADER + "\n",
    )
    ds = CsvDataSource(tmp_path)
    accs = ds.list_accounts()
    assert len(accs) == 1
    assert accs[0].id == "ACC-X"
    # Confirm the model didn't gain the extra fields.
    assert not hasattr(accs[0], "internal_notes")


# --- 6. since filter — two cutoff dates --------------------------------------


def test_since_filter_with_two_cutoffs(tmp_path: Path) -> None:
    accounts = (
        ACCOUNT_HEADER
        + "\n"
        + "ACC-S,Since Co,Tech,10,Starter,12000,2025-01-01,2026-06-01,"
        "Owner,Contact,VP\n"
    )
    usage = (
        USAGE_HEADER
        + "\n"
        + "ACC-S,2026-01-15T09:00:00,session_start,dashboard,u1\n"
        + "ACC-S,2026-03-15T09:00:00,session_start,dashboard,u1\n"
        + "ACC-S,2026-04-15T09:00:00,session_start,dashboard,u1\n"
    )
    _write_four_csvs(
        tmp_path,
        accounts=accounts,
        usage=usage,
        tickets=TICKET_HEADER + "\n",
        nps=NPS_HEADER + "\n",
    )
    ds = CsvDataSource(tmp_path)

    # Cutoff that includes some events
    filtered_some = ds.get_usage_events("ACC-S", since=date(2026, 3, 1))
    assert len(filtered_some) == 2
    assert all(e.timestamp.date() >= date(2026, 3, 1) for e in filtered_some)

    # Cutoff that excludes everything
    filtered_none = ds.get_usage_events("ACC-S", since=date(2027, 1, 1))
    assert filtered_none == []


# --- 7. Malformed date → ValueError naming row + field ----------------------


def test_malformed_date_raises_with_row_and_field(tmp_path: Path) -> None:
    accounts = (
        ACCOUNT_HEADER
        + "\n"
        + "ACC-BAD,Bad Date Co,Tech,10,Starter,12000,not-a-date,2026-06-01,"
        "Owner,Contact,VP\n"
    )
    _write_four_csvs(
        tmp_path,
        accounts=accounts,
        usage=USAGE_HEADER + "\n",
        tickets=TICKET_HEADER + "\n",
        nps=NPS_HEADER + "\n",
    )
    ds = CsvDataSource(tmp_path)
    with pytest.raises(ValueError) as exc_info:
        ds.list_accounts()
    msg = str(exc_info.value)
    assert "contract_start" in msg
    assert "row 2" in msg


# --- 8. Path with spaces -----------------------------------------------------


def test_path_with_spaces_loads_without_error(tmp_path: Path) -> None:
    spaced = tmp_path / "my crm exports"
    accounts = (
        ACCOUNT_HEADER
        + "\n"
        + "ACC-SP,Space Co,Tech,10,Starter,12000,2025-01-01,2026-06-01,"
        "Owner,Contact,VP\n"
    )
    _write_four_csvs(
        spaced,
        accounts=accounts,
        usage=USAGE_HEADER + "\n",
        tickets=TICKET_HEADER + "\n",
        nps=NPS_HEADER + "\n",
    )
    ds = CsvDataSource(spaced)
    accs = ds.list_accounts()
    assert len(accs) == 1
    assert accs[0].id == "ACC-SP"


# --- 9. Briefing renders end-to-end on the samples (stub path) ---------------


def test_briefing_render_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force the stub path: clear any ANTHROPIC_API_KEY and pass api_key=None.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from briefing import generate_briefing
    from health import compute_health
    from models import AccountState

    today = date(2026, 5, 4)
    ds = CsvDataSource(SAMPLES_DIR)
    for account in ds.list_accounts():
        events = ds.get_usage_events(account.id)
        tickets = ds.get_tickets(account.id)
        nps = ds.get_nps_responses(account.id)
        health = compute_health(account, events, tickets, nps, today)
        state = AccountState(
            account=account,
            health=health,
            recent_usage_events=events,
            tickets=tickets,
            nps_responses=nps,
        )
        briefing = generate_briefing(state, api_key=None)
        assert briefing.account_id == account.id
        assert briefing.generated_by == "stub"
        assert len(briefing.bullets) == 3


# --- 10. Subclass + typed return ---------------------------------------------


def test_csv_datasource_does_not_bypass_interface() -> None:
    assert issubclass(CsvDataSource, DataSource)
    ds = CsvDataSource(SAMPLES_DIR)
    accounts = ds.list_accounts()
    assert isinstance(accounts, list)
    assert all(isinstance(a, Account) for a in accounts)


# --- 11. Sample CSVs are referentially consistent ----------------------------


def test_sample_csvs_referentially_consistent() -> None:
    ds = CsvDataSource(SAMPLES_DIR)
    account_ids = {a.id for a in ds.list_accounts()}
    for account_id in account_ids:
        # Every sample account-id must appear in usage, tickets, and NPS files.
        assert ds.get_usage_events(account_id), f"no usage rows for {account_id}"
        assert ds.get_tickets(account_id), f"no tickets for {account_id}"
        assert ds.get_nps_responses(account_id), f"no NPS rows for {account_id}"
