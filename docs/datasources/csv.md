# CSV DataSource

`CsvDataSource` reads account-shaped data from four CSV files in one directory and serves it through the same `DataSource` interface the synthetic fixtures use. Drop your CRM export into a directory, point the dashboard at it, and the same briefing path runs against your data.

## Layout

A CSV directory must contain exactly these four files:

```
<your-dir>/
  accounts.csv
  usage_events.csv
  tickets.csv
  nps_responses.csv
```

The default directory is `data/csv/` at the repo root. That path is gitignored — your real CSVs never land in git. A 5-row synthetic example lives in `data/samples/` (committed); use it as a shape reference.

## How to wire it up

```python
from datasources import CsvDataSource

ds = CsvDataSource("/path/to/your/csv/dir")
accounts = ds.list_accounts()
```

Pass a path with spaces if you need to — the constructor accepts any `Path` or string.

## Column schemas

Required columns must be present (a missing one raises `ValueError` with the column name and the file path). Optional columns may be present with empty cells — those become `None`. Extra columns are silently ignored, so a Salesforce export with dozens of internal fields is safe to drop in unmodified.

### accounts.csv

| Column | Required | Type | Notes |
|---|---|---|---|
| `id` | yes | string | Stable account id, e.g. `ACC-001`. Referenced by every other file. |
| `name` | yes | string | Account display name. |
| `industry` | yes | string | Free-form. |
| `employee_count` | yes | int | Whole number. |
| `plan_tier` | yes | enum | One of `Starter`, `Pro`, `Enterprise`. |
| `arr_usd` | yes | int | Annual recurring revenue, USD, whole dollars. |
| `contract_start` | yes | date | `YYYY-MM-DD`. |
| `renewal_date` | yes | date | `YYYY-MM-DD`. |
| `csm_owner` | yes | string | Name of the CSM who owns the account. |
| `primary_contact_name` | yes | string | |
| `primary_contact_title` | yes | string | |

### usage_events.csv

| Column | Required | Type | Notes |
|---|---|---|---|
| `account_id` | yes | string | FK → `accounts.id`. |
| `timestamp` | yes | datetime | ISO 8601 (`YYYY-MM-DDTHH:MM:SS`) or date-only (`YYYY-MM-DD`). |
| `event_type` | yes | string | E.g. `session_start`, `feature_used`, `export_generated`, `api_call`. |
| `feature` | optional | string | Empty cell allowed. |
| `user_id` | yes | string | A stable per-user identifier within the account. |

### tickets.csv

| Column | Required | Type | Notes |
|---|---|---|---|
| `id` | yes | string | E.g. `T-1042`. |
| `account_id` | yes | string | FK → `accounts.id`. |
| `created_at` | yes | datetime | ISO 8601 or date-only. |
| `resolved_at` | optional | datetime | Empty cell means unresolved. |
| `severity` | yes | enum | One of `low`, `medium`, `high`, `critical`. |
| `status` | yes | enum | One of `open`, `pending`, `resolved`. |
| `subject` | yes | string | One-line ticket subject. |
| `category` | yes | string | Free-form, e.g. `bug`, `question`, `feature_request`. |

### nps_responses.csv

| Column | Required | Type | Notes |
|---|---|---|---|
| `account_id` | yes | string | FK → `accounts.id`. |
| `submitted_at` | yes | datetime | ISO 8601 or date-only. |
| `score` | yes | int | 0 – 10 inclusive. |
| `comment` | optional | string | Empty cell allowed. |

## Date formats

Both date and datetime fields accept:

- ISO 8601 datetime — `2026-04-15T14:00:00`
- Date-only — `2026-04-15` (interpreted as midnight for datetime fields)

Anything else raises `ValueError` naming the row number and field name.

## Worked example

A minimal `accounts.csv` with one row:

```csv
id,name,industry,employee_count,plan_tier,arr_usd,contract_start,renewal_date,csm_owner,primary_contact_name,primary_contact_title
ACC-001,Globex Robotics,Manufacturing,230,Enterprise,480000,2025-06-10,2026-06-23,Marcus Chen,Mira Petrov,VP Engineering
```

Matching `usage_events.csv`:

```csv
account_id,timestamp,event_type,feature,user_id
ACC-001,2026-04-28T09:15:00,session_start,dashboard,u-ACC-001-1
ACC-001,2026-04-28T09:30:00,feature_used,api,u-ACC-001-1
```

Matching `tickets.csv` (one open, one resolved):

```csv
id,account_id,created_at,resolved_at,severity,status,subject,category
T-1000,ACC-001,2026-04-17T12:00:00,,critical,open,API returning 502 on bulk export,bug
T-1001,ACC-001,2026-04-06T14:00:00,2026-04-24T13:00:00,high,resolved,Charge appeared on wrong invoice,access
```

Matching `nps_responses.csv`:

```csv
account_id,submitted_at,score,comment
ACC-001,2026-03-04T14:00:00,8,
ACC-001,2026-04-16T14:00:00,4,API reliability is unacceptable for our scale.
```

Drop those four files into `data/csv/`, switch your `app.py` wiring from `FixtureDataSource` to `CsvDataSource`, and the dashboard renders against your data.

## Errors you might see

| Message | What it means |
|---|---|
| `Missing required column(s) ['renewal_date'] in <path>` | The header row is missing a required column. Add the column or fix the typo. |
| `Malformed date in <path> row N field 'contract_start'` | Cell is not in `YYYY-MM-DD` form. Reformat or trim a stray timestamp. |
| `Malformed datetime in <path> row N field 'timestamp'` | Cell is not ISO 8601 or `YYYY-MM-DD`. Common cause: locale-specific date format (`04/15/2026`). |
| `CSV file not found: <path>` | One of the four required files is missing from the directory. |

Validation runs before any Pydantic parsing, so the error message names the column or the row number — not a deep stack trace into the model layer.

## Privacy

Real customer data lives only on your machine. The default runtime directory `data/csv/` is gitignored, and the samples committed under `data/samples/` are synthetic (`SAMPLE-001` … `SAMPLE-005`). Never commit a real CSV into the repo.
