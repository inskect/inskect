# Configuration

Inskect is configured with environment variables. `pnpm setup` writes the common ones to
`backend/.env.local` (see [`backend/.env.example`](../backend/.env.example)). Environment
variables always win over that file.

## Scan service (`api`)

Every variable is prefixed with `INSKECT_` — for example `INSKECT_AUTH`.

| Variable | Default | Description |
|---|---|---|
| `AUTH` | `none` | Who can use the server: `none` (no sign-in, every visitor has full access, admin page included) or `accounts` (sign-in required; the first account becomes the admin, users see only their own inspections, admins see all and manage the server). |
| `AI_PROVIDERS` | *all* | The AI providers inspections may use for AI review, as a JSON list, e.g. `["anthropic"]`: `anthropic`, `openai`, `azure_openai`, `openai_compatible`, `nv_build`, `ollama`, `claude_cli`. The inspection form offers only these. |
| `ALLOW_CUSTOM_AI_URL` | `true` | Whether an inspection may point a provider at an endpoint of its own (a Base URL), which this server then calls. `false` refuses it, and hides the providers that need one. |
| `CLAUDE_CLI` | `true` | Whether admins may sign this server in to Claude Code, for every visitor's "Claude via this server" inspections ([below](#ai-analysis)). `false` turns it off. |
| `ALLOW_SIGNUP` | *unset* | With accounts, whether visitors may create their own account from the landing page. Unset allows it; admins can also turn it on and off in the backoffice, which takes precedence. The very first account is always the admin. |
| `SESSION_DAYS` | `30` | How long a sign-in lasts. |
| `SMTP_HOST`<br>`SMTP_PORT`<br>`SMTP_USERNAME`<br>`SMTP_PASSWORD`<br>`SMTP_SECURITY` | *unset*<br>`587`<br>*unset*<br>*unset*<br>`starttls` | SMTP server for password reset and sign-up emails: any provider works (your own, your mailbox provider's, or a sending service such as Resend). `SMTP_SECURITY` is `starttls` (port 587), `ssl` (465) or `none` (a local relay only). |
| `SECRET_KEY` | *unset* | Encrypts the Claude keys users save to their account (AES-256-GCM), and keeps share links so their owners can copy them again (without it, a link is shown once). Generate one with `uv run python -m app.secrets_box`. Without it, users paste a key per inspection, and an AI inspection with a pasted key can't be run again if the API restarts mid-inspection. Keep it: if it changes, saved keys can't be decrypted and users have to connect again. |
| `MAIL_FROM` | *unset* | Sender of those emails, e.g. `Inskect <noreply@example.com>`. |
| `PUBLIC_URL` | *unset* | This app's public address, e.g. `https://inskect.example.com`, used for links in emails. Email features switch on when `SMTP_HOST`, `MAIL_FROM` and `PUBLIC_URL` are all set. |
| `ALERT_WEBHOOK_URL` | *unset* | Where to POST alerts: a Slack or Discord incoming webhook, or any endpoint taking JSON. See [Monitoring](./MONITORING.md). |
| `ALERT_EMAIL` | *unset* | Addresses to email alerts to, comma-separated. Needs email set up (above). |
| `GITHUB_APP_CLIENT_ID`<br>`GITHUB_APP_CLIENT_SECRET` | *unset* | The GitHub App users connect to inspect their private repositories ([below](#private-github-repositories)). Both set, with accounts, `SECRET_KEY` and `PUBLIC_URL`, switch the feature on. |
| `GITHUB_APP_SLUG` | *unset* | The app's slug (`github.com/apps/<slug>`), for the Account page's link to choose which repositories it reads. |
| `JOB_RUNNER`<br>`SCAN_EXECUTOR`<br>`UPLOAD_STORE` | the built-in ones | The pieces a deployment may replace, each a class as `module:Class`: how inspections are queued, where they're fetched and analysed, and where uploads are held. See [Extending](./EXTENDING.md). |
| `LOG_STORE` | *by database* | Where live inspection logs and step progress go: `memory` (lost on restart; the default with SQLite) or `database` (the database, so logs survive restarts; the default with Postgres). The database store writes an inspection's lines in batches, about once a second, rather than one transaction per line. |
| `RATE_LIMIT_STORE` | *by database* | Where rate limits count requests: `memory` (this process only; the default with SQLite) or `database` (the database, so counts survive restarts; the default with Postgres). |
| `MAX_CONCURRENT_SCANS` | `2` | Inspections running at once. Inspections with AI analysis also run one at a time. |
| `MAX_QUEUED_SCANS` | `20` | Running + waiting inspections; beyond this, new inspections get `503`. |
| `TRANSITIVE_MAX_DEPTH` | `2` | How many levels of a skill's external references an inspection may follow ("Follow external references" on the inspection form), up to 5; `0` turns the option off. skillspector only follows Git repositories and raw files on the code hosts it can fetch from, never `/blob/` or `/tree/` web pages. Inspections that follow references run through skillspector's CLI, and don't offer a baseline download. |
| `TRANSITIVE_ALLOW_PREFIXES`<br>`TRANSITIVE_DENY_PREFIXES` | *empty* | JSON lists of URL prefixes, e.g. `["https://github.com/acme"]`: only follow references matching one of the first, and never those matching the second. An invalid prefix stops the API from starting. |
| `SCAN_RATE_LIMIT`<br>`SCAN_RATE_LIMIT_WINDOW_SECONDS` | `5`<br>`60` | Inspections allowed per signed-in user (per client IP with `AUTH=none`) within the window. |
| `SCAN_IP_RATE_LIMIT` | `20` | Inspections allowed per client IP within the same window, however many accounts sign in from it. |
| `DAILY_SCAN_QUOTA`<br>`CONCURRENT_SCAN_QUOTA` | *unset* | With accounts, how many inspections each user other than an admin may start per rolling 24 hours, and have in progress at once. `0` or unset means no limit. Admins change both from the backoffice, which takes precedence, and can pause new inspections there too. A user's own quotas, set on their page in the backoffice, take precedence over all of these. |
| `LOGIN_RATE_LIMIT`<br>`LOGIN_RATE_LIMIT_WINDOW_SECONDS` | `10`<br>`300` | Sign-in, first-run setup and sign-up attempts allowed per client IP within the window. Failed sign-ins are also limited per account, whatever the IP: 5 in 15 minutes, 10 in an hour, 20 in a day ([security model](./SECURITY_MODEL.md)). |
| `SCAN_RETENTION_DAYS` | *unset* | Retention when the database is first created (unset keeps inspections forever). Change it later from the admin page. |
| `RETENTION_LOOP` | `true` | Whether the API sweeps expired inspections, sessions and activity itself, every hour. `false` turns it off, for when something else calls the sweep on a schedule. |
| `PROXY_SECRET` | *unset* | Shared by the API and the web app, which reads the same `INSKECT_PROXY_SECRET`: set on both, the API answers only the web app. Set it when the API can be reached other than through the web app; the API isn't published by default. Generate one with `openssl rand -hex 32`. |
| `DATABASE_URL` | *unset* | A `postgres://` or `postgresql://` URL stores inspections in Postgres instead of SQLite. The schema is created and migrated on startup. |
| `DB_PATH` | `data/scans.db` | SQLite file, relative to `backend/`, used when `DATABASE_URL` is unset. |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Origins allowed to call the API directly. The UI goes through its own proxy, so this rarely matters. |

## Analysis (skillspector)

These tune skillspector itself, for every inspection. Each sets the skillspector variable named; only these are passed on, never the rest
of the API's environment. Unset keeps skillspector's own default, given here for the pinned
version (2.12.0). They're also prefixed `INSKECT_`, and a value skillspector would refuse
or silently ignore stops the API from starting instead.

| Variable | skillspector variable | skillspector's default | Description |
|---|---|---|---|
| `YARA_RULES_DIR` | `--yara-rules-dir` | *none* | A directory of extra YARA rules (`.yar`, `.yara`, or base64-encoded `.yar.b64` and `.yara.b64`, in subfolders too), loaded alongside skillspector's own. A rule's `category` meta (`malware`, `webshell`, `cryptominer`, `hack_tool`, `exploit`) sets its finding's rule and severity; without one, a match is a medium `YR4`, and a `severity` meta overrides the severity. Relative to `backend/`. The rules are read when the API starts. With Docker Compose, mount the directory into the `api` container. |
| `OUTPUT_LANGUAGE` | `SKILLSPECTOR_OUTPUT_LANGUAGE` | *none*: the model answers its English prompts in English | The language AI review writes its explanations and remediations in, e.g. `French`: up to 64 letters, digits, spaces, `-` or `_`. Rule names, severities and the report's structure stay as they are. |
| `REASONING_EFFORT` | `SKILLSPECTOR_REASONING_EFFORT` | the model's | Reasoning effort for AI review, e.g. `low` or `high`, passed to the provider as is: which values work depends on the provider and model. |
| `TEMPERATURE` | `SKILLSPECTOR_TEMPERATURE` | the model's | Sampling temperature for AI review, from `0` to `1`. |
| `MAX_LLM_CONCURRENCY` | `SKILLSPECTOR_MAX_LLM_CONCURRENCY` | `10` | AI review requests in flight at once, per inspection. Lower it for a provider plan with tight rate limits. |
| `OSV_TIMEOUT_SECONDS` | `SKILLSPECTOR_OSV_TIMEOUT` | `30` | How long to wait for [OSV.dev](https://osv.dev) when checking a skill's dependencies for known vulnerabilities, before falling back to skillspector's built-in list. |
| `MAX_WORKFLOW_SECONDS` | `SKILLSPECTOR_MAX_WORKFLOW_SECONDS` | `600` | How long an inspection's analysis may take before skillspector stops and reports what it inspected so far. A repository holding several skills shares it between them. |
| `MAX_STATIC_ANALYSIS_SECONDS_PER_ARTIFACT` | `SKILLSPECTOR_MAX_STATIC_ANALYSIS_SECONDS_PER_ARTIFACT` | `300` | How long the static analyzers may spend on any one file before moving on and marking it partly inspected. |

## Web app (`web`)

| Variable | Default | Description |
|---|---|---|
| `NUXT_API_BASE` | `http://localhost:8000` | Where the Nitro proxy reaches the API (`http://api:8000` in Compose). |
| `NUXT_TRUST_PROXY` | `false` | Set to `true` behind a reverse proxy so rate limits use the client IP it appends to `X-Forwarded-For`, and HTTPS requests (its `X-Forwarded-Proto`) get `Strict-Transport-Security`. |
| `NUXT_CSP_REPORT_ONLY` | `false` | `true` sends the Content-Security-Policy as `Content-Security-Policy-Report-Only`: violations are logged, nothing is blocked. See [security headers](./SECURITY_MODEL.md). |
| `NUXT_CSP_CONNECT_SRC` | *none* | Origins the browser may send requests to besides this server, as a JSON list, e.g. `["https://files.example"]`: for a storage or analytics service a build adds. |
| `NUXT_PUBLIC_SITE_URL` | *unset* | This server's public address, e.g. `https://inskect.example.com`. Set, it's the canonical URL of the public pages, `robots.txt` points to `/sitemap.xml`, and the sitemap lists the public pages (see [Search engines](#search-engines)). It's also the base of link previews' absolute URLs (`og:image`, `og:url`). Unset, there's no sitemap or canonical URL, and previews use the address each page was requested at: behind a reverse proxy, set it, or set `NUXT_TRUST_PROXY` so the proxy's forwarded host and protocol are used. |
| `NUXT_PUBLIC_SOURCE_URL` | this project's repository | Where every page's footer offers this server's source code, as the AGPL-3.0 requires of a server people use over a network: set it to your own repository if you run a modified version. |
| `NUXT_ALLOWED_HOST` | *unset* | Public hostname allowed by the development server (`nuxt dev`) only. |

## Search engines

Only the public pages can be indexed: the home page and sign-up. Everything else,
including sign-in, password resets, shared reports and unknown paths, sends `noindex, nofollow`, as
an `X-Robots-Tag` header and a `robots` meta tag.

- **`/robots.txt`**, for everyone: it keeps crawlers out of `/admin`, `/account`, `/history`,
  `/scan/` and `/api/`.
- **`/sitemap.xml`**: the home page, and sign-up when visitors can create an account.

A fresh install doesn't invite crawlers by default: until `NUXT_PUBLIC_SITE_URL` is set,
`robots.txt` names no sitemap, `/sitemap.xml` is not found, and pages have no canonical URL.

## Users' data

Users delete their own account from the Account page, with their password: their inspections and reports,
shared links and badges, Claude key, API tokens and GitHub connection go at once (the token is revoked
at GitHub), and the activity log keeps its entries without their email. An admin deleting a user
does the same. The activity log itself is kept 365 days, and expired password reset and sign-up links are
deleted, whatever the inspection retention.

## Private GitHub repositories

Users can connect their GitHub account from the Account page, then inspect private repositories they
have access to, the same way as public links. It needs accounts (`AUTH=accounts`), `SECRET_KEY` (the
tokens are stored encrypted with it) and `PUBLIC_URL`, plus a GitHub App of your own:

1. On GitHub: **Settings → Developer settings → GitHub Apps → New GitHub App**.
2. **Callback URLs:** `<PUBLIC_URL>/api/account/connections/github/callback`, and for signing in
   with GitHub, `<PUBLIC_URL>/api/auth/github/callback`. Turn on **Expire user authorization
   tokens**. Leave **Webhook** off.
3. **Repository permissions:** **Contents: Read-only** (and **Metadata: Read-only**, which GitHub
   adds). **Account permissions:** **Email addresses: Read-only**, for signing up with GitHub.
   Nothing else: the app never writes.
4. **Where can this GitHub App be installed?** "Any account" lets your users install it on their own
   repositories and organizations; "Only on this account" limits it to yours.
5. Create it, generate a **client secret**, and set `INSKECT_GITHUB_APP_CLIENT_ID`,
   `INSKECT_GITHUB_APP_CLIENT_SECRET` and `INSKECT_GITHUB_APP_SLUG` on the API.

A user then connects GitHub, and chooses on GitHub which repositories the app may read (**Choose
repositories**, which installs it). An inspection reads only what both they and the app's installation can.
On the inspection form, choosing **GitHub** as the source lists those, most recently pushed first, to
pick one instead of pasting its link.
GitLab, Bitbucket and Hugging Face follow later, the same way.

The same app lets people **sign in and sign up with GitHub** ("Continue with GitHub" on the
sign-in and sign-up pages), with nothing more to set. Signing in grants no access to repositories:
GitHub's token is used to read who they are and their verified primary email, then revoked.
Signing up needs sign-up open and a verified email no account here uses; an account that already
uses the email links GitHub from its Account page, after signing in with its password. An app
created before needs the second callback URL and the email permission added (accepting the new
permission is then asked of its users).

## AI analysis

Deep analysis is chosen per inspection in the form — no server setup is needed for the bring-your-own-key
providers.

| Provider | What the visitor supplies | Where the skill's content is sent |
|---|---|---|
| Claude via this server | nothing | Anthropic, through the server's `claude` CLI login |
| Anthropic | API key | Anthropic, or the base URL provided |
| OpenAI | API key | OpenAI, or any OpenAI-compatible base URL |
| Ollama | base URL | That Ollama server |

To enable the server's Claude login, sign in once — from the admin page, or from a terminal:

```bash
docker exec -it inskect-api claude auth login
```

The login is stored in the `claude_cli_auth` volume and survives rebuilds. Every visitor's
Claude-backed inspections share it — see the [security model](./SECURITY_MODEL.md).
