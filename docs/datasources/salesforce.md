# Salesforce DataSource

`SalesforceDataSource` reads accounts and usage events from a live Salesforce org via SOQL through the same `DataSource` interface the synthetic fixtures use. Phase 3a covers Accounts and Usage Events (Tasks); Cases (tickets) and NPS responses land in Phase 3b and currently return empty lists. The dashboard surfaces a "Phase 3b pending" warning when this source is active so the missing ticket and NPS columns are not mistaken for healthy accounts.

## Prerequisites

- A Salesforce org you can authenticate against — Production, Sandbox, or Developer Edition.
- API access enabled for the user account. Most paid editions enable this by default; some restricted editions (e.g. Essentials) do not — verify with your Salesforce admin.
- The user has read access on the `Account` and `Task` (or `Event`) objects, and on the standard and custom fields listed in the field mapping below.
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
4. **Run the dashboard.** `python -m streamlit run app.py`. The sidebar caption shows `Data source: salesforce` and the warning banner confirms Phase 3a stubs are in effect.

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
| `plan_tier` | `Plan_Tier__c` | Custom field. Must resolve to one of `Starter`, `Pro`, `Enterprise` (the model's enum). **Known Phase 3a limitation:** orgs with different picklist values (e.g. `Gold`, `Basic`, `Free`) will fail Pydantic validation when records are loaded — the user sees a `1 validation error for Account plan_tier ...` message. The `account_fields=` override remaps **field names**, not **values**, so it does not resolve this. Workaround: create a Salesforce formula field that normalizes your tier values to `Starter`/`Pro`/`Enterprise` and override `plan_tier` to point at it, or wait for Phase 3b which will add value-mapping support. |
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

The `app.py` factory does not yet expose these overrides through env vars — Phase 3a uses defaults only. Embed a custom factory in your fork if you need overrides today; broader configurability is a Phase 3b candidate.

## Rate-limit handling

Salesforce enforces a daily REST API call cap per org:

- **Developer Edition:** 15,000 calls / 24 hours.
- **Enterprise Edition:** 100,000 calls / 24 hours base + per-user allocation.
- **Other editions:** check `Setup → Company Information → API Requests, Last 24 Hours`.

A Monday-morning dashboard run for 50 accounts issues roughly:

- 1 SOQL call for `list_accounts()`.
- 50 SOQL calls for `get_usage_events(account_id, since)` (one per account).
- Phase 3a returns `[]` from `get_tickets` and `get_nps_responses` — no calls.

That is ~51 calls per page load; well under any real org's daily cap. If you are running this against a Developer Edition org with other tools sharing the budget, the connector logs the `Sforce-Limit-Info` header (`api-usage=N/M`) at INFO level after every SOQL query so consumption is visible in the streamlit logs.

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
| `1 validation error for Account plan_tier Input should be 'Starter', 'Pro' or 'Enterprise'` | The org's `Plan_Tier__c` picklist value doesn't match the model's allowed set. Phase 3a does not support value-remapping (only field-name remapping). Normalize via a Salesforce formula field, or wait for Phase 3b. |
| `Salesforce response missing required field 'Renewal_Date__c'` | The SOQL response is missing a required field — usually because the user lacks read permission on it. Grant access in the user's permission set. |
| `SalesforceDataSource requires SF_USERNAME, SF_PASSWORD, and SF_SECURITY_TOKEN` | Credentials are not set in `.env`. Copy `.env.example` to `.env` and fill them in, or set them in your shell environment.
