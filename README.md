# Held-away assets

Demo API and page for a client workspace. NiFi loads the Iceberg tables once a day. The page lists next-best actions for one client, and a button creates or updates the Salesforce record.

## Run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`cel-python` depends on `google-re2`. That package has no wheel for this Mac and the source build needs C++ headers. If that install fails, install CEL without it. The library then uses Python's `re` module:

```bash
.venv/bin/pip install -r requirements.txt --no-deps
.venv/bin/pip install fastapi uvicorn pydantic-settings httpx PyYAML impyla pytest eval_type_backport pendulum lark jmespath
.venv/bin/pip install --no-deps cel-python==0.4.0
```

Copy `.env.example` to `.env`. For a walkthrough before Impala and Salesforce are connected:

```bash
DEMO_MODE=true API_KEY=demo-key .venv/bin/uvicorn app.main:app --port 8000
```

Open http://127.0.0.1:8000, enter the API key, and load client `C123`.

The same entry point is used locally. Without `CDSW_APP_PORT` it listens on port 8000:

```bash
DEMO_MODE=true API_KEY=demo-key .venv/bin/python cml_app.py
```

## Cloudera AI

This runs as a project Application. Cloudera AI sends browser traffic to `127.0.0.1` on `CDSW_APP_PORT`. `cml_app.py` binds that address. `cdsw-build.sh` installs `requirements.txt` when the Application is deployed.

1. Put this repository in a Cloudera AI project.
2. In Project Settings, set `API_KEY` and `IMPALA_HOST` to the Impala coordinator. Leave `DEMO_MODE` unset so account and event reads go to Impala. `CDSW_APP_PORT` is set by the platform. With no `IMPALA_PASSWORD`, the application authenticates with the workload Kerberos ticket (`GSSAPI`). Set `IMPALA_USER` and `IMPALA_PASSWORD` to use LDAP instead. For a Data Warehouse virtual warehouse, also set `IMPALA_PORT=443`, `IMPALA_USE_HTTP_TRANSPORT=true`, and `IMPALA_KRB_HOST` from the JDBC URL. `CLIENT_ID_COLUMN` defaults to `client_id` on transactions and holdings. `DAILY_ID_COLUMN` defaults to `account_id` on the daily table.
3. Create an Application.
   - Name: Held-away assets
   - Script: `python3 cml_app.py`
4. Open the Application URL, enter the API key, and load a client id. In demo mode that id is `C123`.

The page is reached through the project, so only people who can open the project can load it. The API key is still required on `/v1`. Salesforce and Impala credentials stay in the project environment, not in the repository.

## API

All `/v1` routes require `Authorization: Bearer $API_KEY`. Money values are decimal strings.

```bash
curl -s -H "Authorization: Bearer demo-key" http://127.0.0.1:8000/v1/accounts/summary
curl -s -H "Authorization: Bearer demo-key" \
  "http://127.0.0.1:8000/v1/clients/C123/events?matched_only=true"
curl -s -X POST -H "Authorization: Bearer demo-key" \
  http://127.0.0.1:8000/v1/clients/C123/events/HELDAWAY_LIQUIDATION_DETECTED/sfdc
curl -s -H "Authorization: Bearer demo-key" \
  http://127.0.0.1:8000/v1/clients/C123/events/HELDAWAY_LIQUIDATION_DETECTED/sfdc
```

- `GET /health` checks Impala with `SELECT 1`. In demo mode it returns ok without Impala.
- `GET /v1/accounts` lists accounts. Filters: `container`, `account_type`, `account_status`, `provider_name`, `provider_id`, `last_updated_day`. `limit` defaults to 50 and cannot exceed 200.
- `GET /v1/accounts/{account_id}` returns the full row.
- `GET /v1/accounts/summary` returns net worth by currency. Included assets add, included liabilities subtract, and currencies are not combined.
- `GET /v1/clients/{client_id}/events` evaluates the YAML rules. `matched_only=true` drops the rest.
- `POST /v1/clients/{client_id}/events/{event_name}/sfdc` creates or updates the Salesforce Task, Opportunity, or Account. A second call updates the same record. An unmatched event returns 409.
- `GET` on that same path returns the Salesforce record for the page, or 404 before the button has been used.
- `GET /v1/rules` and `PUT /v1/rules` read and replace `rules/actionable_events.yaml`. A CEL expression that does not compile returns 422 and leaves the file unchanged.

Each event object includes `action` from the YAML (`create_task`, `create_opportunity`, or `update_account`), the description, the business opportunity, the next steps, and the CEL expression.

## Data

`held_away_assets_iceberg.ddl` is the latest account picture used by list, detail, and net worth. Iceberg snapshot retention on that table is 7 days. That is storage time travel, not balance history.

These tables are the daily history the rules read. This repo has the DDL only. NiFi loads them.

- `yodlee_account_daily.ddl` — `yodlee_held_away_accounts_daily`, one row per account per `to_date(ingestion_timestamp)`
- `yodlee_transactions.ddl` — Yodlee transactions
- `yodlee_holdings.ddl` — one row per holding per `as_of_date`

`CLIENT_ID_COLUMN` defaults to `client_id` on transactions and holdings. If it is set to `account_id`, the app still filters those tables on `client_id`. `DAILY_ID_COLUMN` defaults to `account_id` on `yodlee_held_away_accounts_daily`. `DEMO_MODE=true` serves sample features for client `C123` and does not query Impala.

Description and category matches in `app/features.py` are demo heuristics. Replace them when the real Yodlee categories are known.

## Salesforce

Set `SFDC_LOGIN_URL` to the org My Domain, for example `https://your-domain.my.salesforce.com`, not the Lightning login page and not a URL that already includes `/services/oauth2/token` twice. `SFDC_CLIENT_ID` and `SFDC_CLIENT_SECRET` are the Connected App consumer key and secret. Enable the client credentials flow on that Connected App. `SFDC_OPPORTUNITY_STAGE` must exist in the org. `SFDC_ACCOUNT_EXTERNAL_ID_FIELD` is the Account field that stores the client id. The account-update button stays off until that field is set.

Without those credentials, demo mode keeps created records in memory so the page can show an opportunity.

## Tests

```bash
.venv/bin/pytest
```
