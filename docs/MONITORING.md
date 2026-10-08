# Monitoring

Inskect watches its own inspections. When inspections start failing, or someone may be guessing
passwords, it says so three ways:

- **The backoffice's health panel** (Overview): the last 24 hours' failed inspections, the last error with
  a link to its report, and where alerts go.
- **The Monitoring page** (Backoffice → Monitoring): the same counts over 24 hours, 7 or 30 days;
  each alert rule with what trips it, where it stands now, when it last alerted and how long it
  stays quiet; where alerts go, with a test; and every event kept, filterable by kind.
- **Alerts**, to a webhook (Slack, Discord or anything taking JSON) and/or by email, as it happens.
- **Structured logs**: one JSON line per event on stdout, for `docker compose logs` or a log
  collector feeding your own alerting.

## Setting up alerts

Set one or both, on the API (`api` service):

| Variable | What it does |
|---|---|
| `INSKECT_ALERT_WEBHOOK_URL` | POSTs each alert as JSON. A Slack or Discord incoming webhook works as is. |
| `INSKECT_ALERT_EMAIL` | Emails each alert to these addresses, comma-separated. Needs [email](./CONFIGURATION.md) set up. |

Set `INSKECT_PUBLIC_URL` too, so alerts link to the backoffice. Then open **Backoffice** →
**Monitoring** and use **Send a test alert** to check they arrive.

The webhook's body has `text` (Slack), `content` (Discord), and `title`, `message` and `link` for
anything else.

## What raises an alert

| Alert | When | Then waits |
|---|---|---|
| Many inspections are failing | In the last 30 minutes, at least 3 inspections failed, and at least half of those that finished. | 1 hour |
| Accounts are hitting the failed sign-in limit | An account hit its limit of failed sign-ins (5 in 15 minutes, 10 in an hour or 20 in a day), wherever they came from: someone may be guessing its password. The alert doesn't name the account; the backoffice's activity log does. With accounts on. | 1 hour |

An alert isn't repeated within its wait, however many times it trips.

**What an alert carries:** what went wrong, and counts. Messages are scrubbed of API keys, tokens,
passwords and email addresses, and URLs are cut to their host, so an alert never names an inspection's
target, a user, or a key.

## Structured log events

Each line is a JSON object with `event`, `at` (Unix time) and the fields below. None holds user data.

| `event` | Fields |
|---|---|
| `inskect.scan_started` | `scan_id`, `ai_review` |
| `inskect.scan_finished` | `scan_id`, `duration_seconds`, `recommendation` |
| `inskect.scan_failed` | `scan_id`, `reason` (`scan`, `queue` or `restart`), `message`, `duration_seconds` |
| `inskect.scan_interrupted` | `scan_id`: the API stopped mid-inspection, which runs again on startup |
| `inskect.scans_resumed` | `count`: inspections the API picked back up on startup |
| `inskect.csp_violation` | `directive`, `blocked` (an origin, or `inline`/`eval`) and `page` (its path): what the Content-Security-Policy blocked, or would have, from the web app |
| `inskect.sign_in_locked` | none: an account hit its limit of failed sign-ins |
| `inskect.alert` | `title`, `channels` it reached |

Failures, sign-in lockouts and alerts sent are also stored for the health panel and the Monitoring
page, and kept 30 days.

