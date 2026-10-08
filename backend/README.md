# Inskect — scan service

The FastAPI service behind [Inskect](../README.md). It imports
[skillspector](https://github.com/NVIDIA/skillspector) as a library and streams its compiled
LangGraph pipeline (`skillspector.graph.graph`) for each scan — no CLI subprocess, no output
parsing. Scan history and settings are stored in SQLite by default, or in Postgres when
`INSKECT_DATABASE_URL` is set; progress and logs are captured live.

The service is meant to sit on an internal network behind the web app's Nitro proxy
(`server/api/*`), which maps `/api/<path>` to `/<path>` here. Interactive OpenAPI docs are served at
`/docs` on the service itself.

## Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health` | — | Service status, auth mode, skillspector version, and whether the server's Claude login is usable. |
| `GET` | `/auth/session` | — | `{ auth, user, needs_setup, signup_allowed }` for the bearer token, if any. |
| `POST` | `/auth/setup` | accounts | Create the first account, as admin; `409` once any account exists. Returns `{ token, expires_at, user }`. |
| `POST` | `/auth/login` | accounts | Sign in with `{ email, password }`. Returns `{ token, expires_at, user }`. |
| `POST` | `/auth/signup` | accounts | Create an account when sign-up is allowed. |
| `POST` | `/auth/forgot` | accounts | Email a reset link to `{ email }` if it has an active account. Always `202 { accepted: true }`, sent after responding. |
| `POST` | `/auth/reset` | accounts | Set a new password with `{ token, password }` from a reset link; ends the user's other sessions and signs in. |
| `POST` | `/auth/password` | signed in | Change your password with `{ current_password, new_password }`; your other sessions end. |
| `POST` | `/auth/logout` | — | End the bearer token's session. |
| `GET` | `/account/connections` | signed in | `{ github: { available, manage_url, connection } }`: the user's GitHub connection, `{ account_name, connected_at }`, never a token. |
| `GET` | `/account/connections/github/start` | signed in | `{ url }`: GitHub's page to authorize the app, with a state only this user can redeem for 10 minutes. |
| `POST` | `/account/connections/github/callback` | signed in | Redeem GitHub's callback, `{ code, state }`: the tokens are stored encrypted. The web app's `/api/account/connections/github/callback` calls it. |
| `DELETE` | `/account/connections/github` | signed in | Disconnect: the tokens are deleted, and revoked at GitHub. |
| `GET` · `POST` | `/account/tokens` | signed in | Your API tokens (never the tokens themselves), or create one with `{ name, expires_in_days }` (`null`: never expires): the response holds the token, this once. See [API tokens](#api-tokens). |
| `DELETE` | `/account/tokens/{id}` | signed in | Revoke one of your API tokens. |
| `GET` · `PUT` · `DELETE` | `/account/claude` | signed in | Your saved Claude key: status `{ provider, hint, updated_at }` (never the key), connect or replace with `{ api_key }` (checked with Anthropic first), or disconnect. Needs accounts and `SECRET_KEY`. |
| `GET` | `/admin/overview` | admin | User and scan totals (with the last 7 days), sign-up and email status, recent activity, and `health`: the last 24 hours' failures, the last error and where alerts go ([monitoring](../docs/MONITORING.md)). |
| `GET` | `/admin/monitoring` | admin | `?hours=` (24, 168 or 720): the window's counts, each alert rule with where it stands and when it last alerted, and where alerts go (the webhook by its host only). |
| `GET` | `/admin/monitoring/events` | admin | Monitoring's events, newest first: `?kind=` (`all`, `failures`, `lockouts`, `alerts`), `?limit=`, `?offset=`. |
| `POST` | `/admin/alerts/test` | admin | Send a test alert to every channel set up: `{ channels }`; `409` when none is. |
| `GET` | `/admin/activity` | admin | The audit log, newest first: `?limit=` and `?offset=`. Returns `{ items, total }`. |
| `GET` · `POST` | `/admin/users` | admin | The directory (`?query=` searches emails; each user has role, status, scan count, last sign-in), or add a user with `{ email, password, role }`. |
| `GET` · `PATCH` | `/admin/users/{id}` | admin | A user with their recent scans and account history, or change `{ role, status }`. Suspending signs them out. |
| `POST` | `/admin/users/{id}/reset-email` | admin | Email the user a reset link; `409` without SMTP. |
| `POST` | `/admin/users/{id}/reset` | admin | Issue a one-time password reset link, valid 24 hours: `{ path, expires_at }`. Cancels earlier links. |
| `GET` | `/admin/users/{id}/tokens` | admin | A user's API tokens, as they see them. |
| `PUT` | `/admin/users/{id}/quotas` | admin | Give a user their own scan quotas, `{ daily_scan_quota, concurrent_scan_quota }`: a number, `0` for no limit, or `null` to follow the server's. Audited. `GET /admin/users/{id}` has them under `quotas`, with the server's and today's use. |
| `DELETE` | `/admin/users/{id}/tokens/{token_id}` | admin | Revoke a user's API token. |
| `DELETE` | `/admin/users/{id}` | admin | Remove a user and end their sessions; their scans stay. Not yourself, not the last admin. |
| `POST` | `/scan` | token · rate-limited | Queue a scan of a `target`. Returns `{ id, status }`. |
| `POST` | `/scan/upload` | token · rate-limited | Queue a scan of a `.zip` or `.md` sent as the multipart `file`, with the options as JSON in `options`. |
| `GET` | `/scan` | token | Scan history: `?limit=` (1–100, default 20), `?offset=`, `?target=` (one target's scans), `?sort=` (`created_at`, `target`, `risk_score`, `verdict`, `status`) and `?order=` (`asc`, `desc`; newest first by default). Returns `{ items, total }`. |
| `GET` | `/scan/{id}` | token | Status (`pending` · `running` · `done` · `error`), its report number among its owner's (`report_no`, shown as INS-0001), step progress and, once done, the report, with what changed since the target's previous scan (`comparison`). |
| `GET` | `/scan/{id}/export` | token | The finished report as a download: `?format=json` (skillspector's report) or `?format=sarif` (SARIF 2.1.0). |
| `POST` | `/scan/{id}/rescan` | token · rate-limited | Scan the target again as this scan did. |
| `GET` | `/scan/{id}/logs` | token | Captured log lines for a scan (in memory, or in the database with `LOG_STORE=database`). |
| `POST` · `DELETE` | `/scan/{id}/share` | signed in | Share the result at a read-only link (`{ token }`, for `/shared/{token}`), or revoke it. A private repository's scan needs `{ confirm_private: true }` (else `409`). |
| `DELETE` | `/scan/{id}` | signed in | Delete a scan. `204` on success. |
| `POST` · `DELETE` | `/scan/{id}/badge` | signed in | Put the shared result on its target's status badge, or take it off. Refused for an unshared result (`409`), an upload or a scan with a baseline (`422`), and for a private repository's scan without `{ confirm_private: true }` (`409`). Revoking the link takes it off too. |
| `GET` | `/badge` | — | `?target=`: the latest scan of the target on its badge, `{ recommendation, risk_score, scanned_at, share_token }`, all `null` when there's none. The web app renders it as an SVG at `/badge`. |
| `GET` | `/shared/{token}` | — | A shared result, read-only; also `/skills/{index}` and `/export`. |
| `GET` | `/settings` | — | `{ scan_retention_days }` (`null` = keep forever). |
| `PUT` | `/settings` | admin | Update retention; runs a sweep immediately. |
| `POST` | `/admin/claude-login/start` | admin | Start `claude auth login`; returns the URL to open. |
| `POST` | `/admin/claude-login/complete` | admin | Finish the login with `{ code }`. |

**Access** follows `INSKECT_AUTH` (`app/auth/`):

- **`none`:** every request has full access, admin endpoints included, and the `/auth/*` account
  endpoints return `404`.
- **`accounts`:** every scan, settings and admin endpoint needs `Authorization: Bearer <token>`
  from a sign-in (`401` without one). The endpoints marked *token* also take a personal API token
  (see [API tokens](#api-tokens)); every other one refuses it (`403`).
  - Scan endpoints only show a user their own scans, and answer `404` for anyone else's.
  - `admin` endpoints need the admin role (`403`).

The web app keeps the token in an `httpOnly` cookie and adds the header when it proxies a request.
Rate limits answer `429` with a `Retry-After` header and a message saying when to try again:

- `POST /scan`: per signed-in user (`SCAN_RATE_LIMIT`, or per client IP with `AUTH=none`), plus a
  per-IP cap across every account signed in from one address (`SCAN_IP_RATE_LIMIT`).
- Sign-in, setup, sign-up, password reset and password change: per client IP (`LOGIN_RATE_LIMIT`).

The client IP is the `X-Forwarded-For` value the web proxy sets.

### Starting a scan

```http
POST /scan
Content-Type: application/json

{
  "target": "https://github.com/anthropics/skills/blob/main/skills/pdf/SKILL.md",
  "llm": { "provider": "anthropic", "api_key": "sk-ant-…", "model": null, "base_url": null }
}
```

- `target` — an `https://` URL of a repository or file on a host skillspector accepts (GitHub,
  GitLab, Bitbucket, Hugging Face, raw.githubusercontent.com). Local paths are rejected.
- `llm` — optional; omit or `null` for a static scan. `provider` is `anthropic`, `openai`,
  `ollama` or `claude_cli`. `api_key` is required for `anthropic` and `openai`; `claude_cli` uses
  the server's own login. The key is used for this scan only and never stored.

| Status | Meaning |
|---|---|
| `200` | Queued — poll `GET /scan/{id}`. |
| `422` | Invalid body, e.g. a non-http(s) target or a remote AI provider without a key. |
| `429` | Rate limit exceeded for this client. |
| `503` | The queue is full (`INSKECT_MAX_QUEUED_SCANS`). |

The finished report is skillspector's JSON report (`risk_assessment`, `issues`, `metadata`, …).

### API tokens

Scripts and CI jobs authenticate with a personal API token instead of a browser session (with
`AUTH=accounts`; without accounts, no token is needed). Create one on the **Account** page, or with
`POST /account/tokens` from a session: it's shown once, and only its hash is stored. A token:

- acts as the user who made it: the same scans, quotas and rate limits. It stops working when it's
  revoked, when it expires, or when its owner is suspended or deleted: `401`.
- has the `scan` scope: it starts scans, and reads, exports and rescans them (the endpoints marked
  *token* above). Everything else, deleting or sharing a scan included, needs a session (`403`).
- is recorded in the activity log when it's created, revoked, and first used each day. Admins see
  and revoke any user's tokens from the user's page.

Start a scan, then poll it until it's done:

```bash
export INSKECT_TOKEN=sst_…            # from the Account page
API=https://inskect.example.com/api  # the web app proxies /api/* to this service

id=$(curl -fsS -X POST "$API/scan" \
  -H "Authorization: Bearer $INSKECT_TOKEN" -H "Content-Type: application/json" \
  -d '{"target": "https://github.com/anthropics/skills/tree/main/skills/pdf"}' | jq -r .id)

until status=$(curl -fsS "$API/scan/$id" -H "Authorization: Bearer $INSKECT_TOKEN" | jq -r .status);
      [ "$status" = done ] || [ "$status" = error ]; do sleep 5; done

curl -fsS "$API/scan/$id" -H "Authorization: Bearer $INSKECT_TOKEN" \
  | jq '.result.risk_assessment'                      # { score, severity, recommendation }
curl -fsS "$API/scan/$id/export?format=sarif" -H "Authorization: Bearer $INSKECT_TOKEN" -o inskect.sarif
```

The recommendation is `SAFE`, `CAUTION` or `DO_NOT_INSTALL`, so a CI job can fail on, say,
`DO_NOT_INSTALL`; the SARIF file can be uploaded to GitHub code scanning.

## Behaviour worth knowing

- **File links.** skillspector downloads a single-file link as is, so a code host's file view
  (GitHub's `/blob/`) would be scanned as the page's HTML. `POST /scan` rewrites these links to the
  raw file first (`app/targets.py`), and stores the rewritten target:
  - GitHub `/blob/` and `/raw/` become `raw.githubusercontent.com`.
  - GitLab `/-/blob/` becomes `/-/raw/`.
  - Hugging Face `/blob/` becomes `/resolve/`.
- **Storage.** `app/db.py` is the only module the app calls; it delegates to a SQLite or Postgres
  store (`app/storage/`). Each store applies its versioned migrations on startup and records them in
  `schema_migrations`; existing SQLite databases are adopted as they are. Scans aren't copied
  between engines when you switch.
- **Job runner.** `app/jobs/` runs scans as asyncio tasks in the API process (`in_process`, below);
  it calls `scanner.run_job()`, which records the outcome on the scan. The job runner, the scan
  executor and the upload store can each be replaced by a setting ([Extending](../docs/EXTENDING.md)).
- **AI providers.** `INSKECT_AI_PROVIDERS` limits the providers a scan may use (all when
  unset), `INSKECT_ALLOW_CUSTOM_AI_URL=false` refuses a scan's own `base_url`, which this
  server would otherwise call, and `INSKECT_CLAUDE_CLI=false` turns off the server-wide
  Claude Code login. Refused requests get a `422`.
- **Saved Claude keys** (`app/claude_key.py`, `app/secrets_box.py`). A scan request with
  `"llm": { "provider": "anthropic", "use_saved_key": true }` uses the key saved to the user's
  account: it's decrypted when the scan is queued and held in memory for it.
- **Concurrency.** Up to `INSKECT_MAX_CONCURRENT_SCANS` scans run at once, each in a
  worker thread. Scans with AI analysis are additionally serialised, because the provider's
  credentials are passed to skillspector through process environment variables.
- **Restarts.** With the in-process runner the queue lives in the database: a restart or redeploy
  loses no scan (`app/jobs/in_process.py`).
  - A scan stopped mid-run goes back to `pending` (or stays `running`, if the process was killed),
    and its upload is kept. On startup, every pending or running scan is run again, oldest first.
  - Each start counts towards `scans.attempts`; a scan started 3 times without finishing fails with
    "The scan didn't finish after 3 attempts".
  - AI review runs again with what it had: the user's saved key, the server's Claude login, or the
    one-off key and endpoint held encrypted in `scan_secrets` until the scan has run. Holding them
    needs `SECRET_KEY`; without it, only scans with a one-off key fail on restart, saying so.
  - One API process runs the queue: don't run several replicas of the API.
- **Logs.** `INSKECT_LOG_STORE` picks where log lines and step progress go (`app/scan_logs.py`):
  - `memory` (the default with SQLite): the last 500 lines of each of the 50 most recent scans, lost
    on restart.
  - `database` (the default with Postgres): the last 500 lines per scan in `scan_log_lines` and the
    step count on the scan, kept across restarts. Lines are deleted with their scan, including by
    the retention sweep.
  - A scan that runs again (after a restart) starts its log and progress afresh.
- **Rate limits.** `INSKECT_RATE_LIMIT_STORE` picks where hits are counted (`app/rate_limit.py`),
  as sliding windows:
  - `memory` (the default with SQLite): in this process, for the 1000 most recently seen clients.
  - `database` (the default with Postgres): in `rate_limit_hits`, kept across restarts. On
    Postgres each check holds an advisory lock on its key, so concurrent requests can't both take
    the last slot. Expired hits are deleted as new ones come in.
  - A refused request isn't counted, so retrying too early doesn't push the limit further out.
- **Quotas and pausing** (`app/quotas.py`), checked by `POST /scan`:
  - A paused server refuses every new scan with `503`, admins' included.
  - Signed-in users other than admins are limited per rolling 24 hours and in progress at once;
    either refusal is a `429`. The quota check runs last, so a scan refused for another reason
    doesn't count.
  - Daily scans are counted in `rate_limit_hits` whatever the rate-limit store, so the count
    survives restarts and deleting a scan doesn't give it back. The in-progress limit counts the
    user's pending and running scans, checked as the scan is inserted, in one step: a conditional
    insert on SQLite, a per-user advisory lock on Postgres. So simultaneous requests queue exactly the
    limit, and a request refused there doesn't count towards the day's.
  - Each limit is, in order: the user's own (`users.daily_scan_quota`, `concurrent_scan_quota`,
    set with `PUT /admin/users/{id}/quotas`), the server's in `app_settings` once an admin saves
    them (`PUT /settings`), `DAILY_SCAN_QUOTA` and `CONCURRENT_SCAN_QUOTA`, then no
    limit. `0` is no limit; a user's `null` follows the server. An override applies from the
    user's next request: their row is read with their session or token. `GET /account/usage`
    reports the user's own effective limits with their counts.
- **Retention.** The sweep deletes finished scans older than the configured number of days, with
  their log lines and held keys; scans still in progress are never swept. Changing the retention
  sweeps straight away.
  - A background task in the API process sweeps every hour. `INSKECT_RETENTION_LOOP=false`
    turns it off, for when something else calls `retention.sweep_once()` on a schedule.

Configuration options are listed in the [configuration reference](../docs/CONFIGURATION.md).

## Development

```bash
uv sync
uv run uvicorn app.main:app --reload   # http://localhost:8000, docs at /docs
uv run pytest                          # add TEST_DATABASE_URL=postgresql://… to also test Postgres
uv run pytest --random-order           # as CI runs it; --random-order-seed=<seed> replays an order
uv run ruff check .
```

Settings are read from the environment, then `backend/.env.local`, then `backend/.env`.
