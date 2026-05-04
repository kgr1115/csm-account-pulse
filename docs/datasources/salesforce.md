# Salesforce DataSource

`SalesforceDataSource` reads accounts, usage events, tickets, and NPS responses from a live Salesforce org via SOQL through the same `DataSource` interface the synthetic fixtures use. All four `DataSource` methods are wired: Accounts (`Account`), Usage Events (default `Task`), Cases (`Case` → tickets), and NPS responses (default `NPS_Response__c`).

## Prerequisites

- A Salesforce org you can authenticate against — Production, Sandbox, or Developer Edition.
- API access enabled for the user account. Most paid editions enable this by default; some restricted editions (e.g. Essentials) do not — verify with your Salesforce admin.
- The user has read access on the `Account`, `Task` (or `Event`), `Case`, and (if present) NPS custom objects, plus the standard and custom fields listed in the field mapping below.
- Python `simple-salesforce>=1.12,<2` installed (already pinned in `requirements.txt`).

## Credential setup

`SalesforceDataSource` authenticates with username + password + security token. OAuth and JWT flows are out of scope for Phase 3a — username+password is the lowest-friction path for a CSM running this locally.

1. **Get your security token.** Salesforce sends the token by email after a "Reset My Security Token" action — there is no UI screen showing the current token. To trigger an email:
   - Open Salesforce in your browser.
   - Click your avatar (top right) → **Settings**.
   - In the left sidebar, navigate to **My Personal Information → Reset My Security Token**.
   - Click **Reset Security Token**. Salesforce emails the token to your account email within a minute. **Resetting invalidates the previous token** — any other tools using the old token will need updating.
2. **Copy `.env.example` to `.env`** and fill in:
   ```
   DATASOURCE=salesforce
   SF_USERNAME=you@yourcompany.com
   SF_PASSWORD=your-salesforce-password
   SF_SECURITY_TOKEN=the-token-from-the-email
   SF_DOMAIN=login
   ```
3. **Set `SF_DOMAIN=test`** if you are connecting to a Sandbox. Production and Developer Edition orgs use `login` (the default).
4. **Run the dashboard.** `python -m streamlit run app.py`. The sidebar caption shows `Data source: salesforce`. If your org doesn't have the default `NPS_Response__c` custom object, the connector logs the miss and the NPS column shows blank — see "NPS Responses" below for overrides.

If any of `SF_USERNAME`, `SF_PASSWORD`, or `SF_SECURITY_TOKEN` is missing or blank, the dashboard falls back to the synthetic fixtures and the sidebar surfaces the miss.

## Field mapping

The defaults target a stock Salesforce org. Orgs with renamed or hidden fields override the defaults at construction time (see "Customizing field names" below).

### Account → `Account` model

SOQL: `SELECT <fields> FROM Account`

| Model field | Default Salesforce field | Notes |
|---|---|---|
| `id` | `Id` | Salesforce 18-character ID. |
| `name` | `Name` | |
| `industry` | `Industry` | Standard picklist. |
| `employee_count` | `NumberOfEmployees` | Standard field; integer. |
| `plan_tier` | `Plan_Tier__c` | Custom field. Must resolve to one of `Starter`, `Pro`, `Enterprise` (the model's enum). **Known limitation:** orgs with different picklist values (e.g. `Gold`, `Basic`, `Free`) will fail Pydantic validation when records are loaded — the user sees a `1 validation error for Account plan_tier ...` message. The `account_fields=` override remaps **field names**, not **values**, so it does not resolve this. Workaround: create a Salesforce formula field that normalizes your tier values to `Starter`/`Pro`/`Enterprise` and override `plan_tier` to point at it. Picklist value-remapping for tier is on the roadmap. |
| `arr_usd` | `ARR__c` | Custom field; integer USD. |
| `contract_start` | `Contract_Start__c` | Custom field; date. |
| `renewal_date` | `Renewal_Date__c` | Custom field; date. |
| `csm_owner` | `CSM_Owner__c` | Custom field; the CSM's display name. |
| `primary_contact_name` | `Primary_Contact_Name__c` | Custom field. |
| `primary_contact_title` | `Primary_Contact_Title__c` | Custom field. |

### Task → `UsageEvent` model

SOQL: `SELECT <fields> FROM Task WHERE AccountId = :account_id [AND CreatedDate >= :since]`

`Task` is the default usage-event source: every org has it, and `CreatedDate` maps cleanly to `UsageEvent.timestamp`. Some orgs store usage telemetry on a custom object (`Usage_Event__c`) or on `Event` (the calendar object) — see "Customizing field names" to point at those instead.

| Model field | Default Salesforce field | Notes |
|---|---|---|
| `account_id` | `AccountId` | |
| `timestamp` | `CreatedDate` | Salesforce returns ISO 8601 with milliseconds + offset; the connector parses both `+0000` and `Z` forms. |
| `event_type` | `Type` | Standard Task picklist. |
| `feature` | `Subject` | Optional; empty Subject becomes `None`. |
| `user_id` | `OwnerId` | The user who logged the Task. |

### Why Task and not Event

Both `Task` and `Event` are standard objects representing user activity, and either could host usage telemetry. `Task` is the default because:

- Most CRMs use `Task` for call logs, emails, and "did this thing" records — closer in spirit to a `UsageEvent`.
- `Event` is calendar-coupled (start/end times, all-day flags) — fields the model does not need.
- Switching to `Event` is a one-line override (`usage_object="Event"` plus a field map adjustment).

### Case → `Ticket` model

SOQL: `SELECT CaseNumber, AccountId, CreatedDate, ClosedDate, Priority, Status, Subject, Type FROM Case WHERE AccountId = :account_id`

| Model field | Default Salesforce field | Notes |
|---|---|---|
| `id` | `CaseNumber` | The user-facing case number (e.g. `00001042`). The internal Case `Id` works too — pass `case_fields={"id": "Id", ...}` to use it. |
| `account_id` | `AccountId` | |
| `created_at` | `CreatedDate` | |
| `resolved_at` | `ClosedDate` | Null on open cases — the connector preserves `None` rather than coercing to a string or raising. |
| `severity` | `Priority` | Mapped to `TicketSeverity` (`low` / `medium` / `high` / `critical`) via the priority map below. |
| `status` | `Status` | Mapped to `TicketStatus` (`open` / `pending` / `resolved`) via the status map below. |
| `subject` | `Subject` | |
| `category` | `Type` | Standard Case picklist. |

**Priority → severity mapping:**

| Salesforce Priority | `TicketSeverity` |
|---|---|
| `Critical` | `critical` |
| `High` | `high` |
| `Medium` | `medium` |
| `Low` | `low` |

Unknown priority values (e.g. `Urgent` from a customized picklist) **log at INFO and floor to `low`** — the dashboard keeps rendering rather than raising. Override via `priority_map=` if your org's picklist values are stable enough to map explicitly:

```python
ds = SalesforceDataSource(
    username=..., password=..., security_token=...,
    priority_map={"P0": "critical", "P1": "high", "P2": "medium", "P3": "low"},
)
```

**Status → ticket-status mapping:**

| Salesforce Status | `TicketStatus` |
|---|---|
| `New` | `open` |
| `Working` | `open` |
| `Escalated` | `open` |
| `On Hold` | `pending` |
| `Closed` | `resolved` |

Unknown status values log at INFO and floor to `open` (the safer default — an unrecognized state is more likely actionable than archived). Override via `status_map=` for orgs with custom Case state machines.

### NPS Responses → `NpsResponse` model

Salesforce ships no stock NPS object — orgs typically add a custom one (commonly `NPS_Response__c`) or use a third-party survey app (Qualtrics, Medallia, etc.) whose schema differs. The connector targets the common case and exposes overrides for the rest.

SOQL: `SELECT Account__c, Created_Date__c, Score__c, Comment__c FROM NPS_Response__c WHERE Account__c = :account_id`

| Model field | Default Salesforce field | Notes |
|---|---|---|
| `account_id` | `Account__c` | Reference field linking the response to an Account. |
| `submitted_at` | `Created_Date__c` | The org's record-creation timestamp; some orgs use a separate `Submitted_At__c` — override via `nps_fields=`. |
| `score` | `Score__c` | Integer 0–10. The field name is configurable via `score_field=` so orgs using `Rating__c`, `NPS_Score__c`, etc. can plug in directly. |
| `comment` | `Comment__c` | Optional free text. Null comments become `None`. |

The configurable constructor arguments cover the common variations:

```python
ds = SalesforceDataSource(
    username=..., password=..., security_token=...,
    # Org uses a Survey app's custom schema instead of NPS_Response__c
    nps_object="Survey_Response__c",
    score_field="Rating__c",
    nps_fields={
        "account_id": "Customer__c",
        "submitted_at": "Submitted_Date__c",
        "comment": "Feedback__c",
    },
)
```

**Soft-fallback when the NPS object is absent:** if the SOQL query returns Salesforce's `INVALID_TYPE` error (object not present in this org), `get_nps_responses()` logs the miss at INFO and returns `[]`. The dashboard still renders — accounts simply have no NPS signal. This is the only error path that's swallowed; every other `SalesforceError` (e.g. `INVALID_FIELD` because a single field is misspelled) surfaces as a `ValueError` so the user can fix the override.

## Customizing field names

Two override paths cover non-standard orgs:

```python
from datasources import SalesforceDataSource

# Override the Account field map for an org that uses non-default custom field names.
ds = SalesforceDataSource(
    username=...,
    password=...,
    security_token=...,
    account_fields={
        "id": "Id",
        "name": "Name",
        "industry": "Industry",
        "employee_count": "NumberOfEmployees",
        "plan_tier": "Subscription_Tier__c",
        "arr_usd": "Annual_Revenue__c",
        "contract_start": "ContractStartDate__c",
        "renewal_date": "Subscription_Renewal__c",
        "csm_owner": "Customer_Success_Owner__c",
        "primary_contact_name": "Main_Contact__c",
        "primary_contact_title": "Main_Contact_Title__c",
    },
)

# Or point usage events at a custom telemetry object.
ds = SalesforceDataSource(
    username=..., password=..., security_token=...,
    usage_object="Usage_Event__c",
    usage_fields={
        "account_id": "Account__c",
        "timestamp": "Event_Timestamp__c",
        "event_type": "Event_Type__c",
        "feature": "Feature__c",
        "user_id": "User__c",
    },
)
```

The same pattern works for `case_fields=`, `priority_map=`, `status_map=`, `nps_object=`, `score_field=`, and `nps_fields=` — see the Case and NPS sections above for examples.

The `app.py` factory does not expose these overrides through env vars. Embed a custom factory in your fork if your org needs overrides; the constructor surface is intentionally configuration-rich so the env-var layer can stay narrow.

## Rate-limit handling

Salesforce enforces a daily REST API call cap per org:

- **Developer Edition:** 15,000 calls / 24 hours.
- **Enterprise Edition:** 100,000 calls / 24 hours base + per-user allocation.
- **Other editions:** check `Setup → Company Information → API Requests, Last 24 Hours`.

A Monday-morning dashboard run for 50 accounts issues roughly:

- 1 SOQL call for `list_accounts()`.
- 50 SOQL calls for `get_usage_events(account_id, since)` (one per account).
- 50 SOQL calls for `get_tickets(account_id)` (one per account).
- 50 SOQL calls for `get_nps_responses(account_id)` (one per account; if the NPS object is absent, the call still hits the API and gets back `INVALID_TYPE`).

That is ~151 calls per page load; well under any real org's daily cap. If you are running this against a Developer Edition org with other tools sharing the budget, the connector logs the `Sforce-Limit-Info` header (`api-usage=N/M`) at INFO level after every SOQL query so consumption is visible in the streamlit logs.

When Salesforce returns `REQUEST_LIMIT_EXCEEDED`, the connector raises a `ValueError` whose message includes the most recent `Sforce-Limit-Info` value. **The connector does not retry automatically** — an infinite loop against a live API is a worse failure mode than a clear error. Restart the dashboard after the daily limit resets (midnight in your org's timezone, or stagger by spreading reads across a longer window).

Other `SalesforceError` codes (e.g. `INVALID_FIELD`, `MALFORMED_QUERY`) also surface as `ValueError` with the error code in the message — most often these point at a field-mapping mismatch you can fix with the override pattern above.

## Privacy

Salesforce credentials in `.env` never leave your machine — `.env` is gitignored. Real customer records pulled from your org are never written to the repo by this code. The dashboard reads; it never writes back to Salesforce.

If you publish or share the dashboard's screenshots, scrub the account names and CSM names — the synthetic fixtures use deliberately fictional names (Globex, Initech, Hooli) precisely so screenshots are safe to share. Real orgs are not.

## Errors you might see

| Message | What it means |
|---|---|
| `Salesforce REQUEST_LIMIT_EXCEEDED: ... Limit info: api-usage=15000/15000.` | Daily REST API cap reached. Wait for the 24-hour reset or use a higher-tier org. |
| `Salesforce SOQL error (INVALID_FIELD): No such column 'Plan_Tier__c'` | Default field map does not match this org's schema. Override `account_fields=` per the section above. |
| `1 validation error for Account plan_tier Input should be 'Starter', 'Pro' or 'Enterprise'` | The org's `Plan_Tier__c` picklist value doesn't match the model's allowed set. Field-name remapping doesn't fix this; normalize via a Salesforce formula field. |
| `Salesforce response missing required field 'Renewal_Date__c'` | The SOQL response is missing a required field — usually because the user lacks read permission on it. Grant access in the user's permission set. |
| `Salesforce SOQL error (INVALID_TYPE): sObject type 'NPS_Response__c' is not supported` (logged at INFO, no error raised) | Your org doesn't have an `NPS_Response__c` custom object. The connector treats this as a soft failure and returns `[]` so the dashboard still renders. Override `nps_object=` and `score_field=` in the constructor if your org uses a different name (e.g. `Survey_Response__c` + `Rating__c`). |
| `Salesforce SOQL error (INVALID_FIELD): No such column 'Score__c' on entity 'NPS_Response__c'` | The NPS object exists but its score field is named differently in your org. Pass `score_field="<your_field>"` to the constructor. |
| `Unknown Case Priority value 'Urgent' — defaulting severity to 'low'.` (INFO log, no error raised) | The Case Priority picklist in your org includes a value not in the default map. The ticket still loads with `severity="low"`. Pass an explicit `priority_map=` to the constructor to map your org's values directly. |
| `Unknown Case Status value 'In Triage' — defaulting status to 'open'.` (INFO log, no error raised) | The Case Status picklist in your org includes a value not in the default map. The ticket still loads with `status="open"`. Pass an explicit `status_map=` to the constructor. |
| `SalesforceDataSource requires SF_USERNAME, SF_PASSWORD, and SF_SECURITY_TOKEN` | Credentials are not set in `.env`. Copy `.env.example` to `.env` and fill them in, or set them in your shell environment.
