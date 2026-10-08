# Security model

Inskect is designed for a trusted audience — yourself, a team, a homelab. What is and
isn't protected:

- **Authentication is your choice.** With `AUTH=none` (the default) there's no
  sign-in: anyone who can reach the UI can run, read and delete every inspection and use the admin page,
  including the server's Claude login. Keep it on a private network or behind your reverse proxy's
  authentication (for example Authentik or Authelia forward-auth). With `AUTH=accounts`:
  - Every page needs a sign-in. Inspections belong to the user who ran them, and a user can't see,
    open or delete anyone else's (the API answers `404`). Admins see every inspection, including ones
    from before accounts were turned on, and manage users, retention and the Claude login.
  - Passwords are hashed with scrypt. Sessions are random tokens stored only as SHA-256 hashes,
    kept in an `httpOnly`, `SameSite=Lax` cookie that page scripts can't read, and expire after
    `SESSION_DAYS`.
  - Sign-in and password-reset attempts are rate-limited per client IP.
  - **Failed sign-ins are limited per account**, wherever they come from: 5 in 15 minutes, 10 in
    an hour, 20 in a day. Past that, sign-ins with that email are refused, even with the right
    password, until the window frees up. Every email gets the same limit and the same answer,
    whether or not it has an account. Hitting the limit raises an alert ([monitoring](./MONITORING.md))
    and appears in the account's activity. The trade-off: someone who knows an email can keep its
    owner from signing in, for up to a day at most.
  - **Sign-up:** with SMTP configured, signing up emails a link that creates the account, valid
    once for 24 hours. The answer and its timing are the same whether or not the address has an
    account: an address that has one is emailed that instead. Without SMTP, accounts are created
    straight away, so signing up with a taken address is refused, which tells that it has an
    account. Set up email, or turn sign-up off (backoffice → Settings), where that matters.
  - **Forgotten passwords:** reset links are one-time, valid for 24 hours, stored only as a hash,
    and cancelled by a newer link. Using one signs the person out everywhere else and revokes the
    account's API tokens: whoever reset it may not be whoever made them.
    - With SMTP configured, "Forgot password?" on the sign-in page emails a link. The answer and
      its timing are the same whether or not the address has an account, and links always use
      `PUBLIC_URL`, never the request's `Host` header.
    - Without SMTP, an admin copies a link from the user's page in the backoffice and passes it on.
    - Anyone signed in can change their password from the Account page. That signs out their other
      sessions, and revokes their API tokens unless they untick it.
    - **Sign out everywhere** (Account page) ends every other session and revokes every API token
      at once, for an account that may have been taken over. The activity log records it.
    - An admin locked out of their own account can print a link on the server:
      `docker exec inskect-api python -m app.auth.reset_link you@example.com` (prefix `python`
      with `uv run` in the development containers).
  - **Backoffice** (`/admin`, admins only):
    - An overview, and a user directory with each user's role, status, inspections and last sign-in.
    - Per-user actions: promote or demote, suspend (which signs them out and blocks sign-in) or
      reactivate, send or copy a reset link, delete. Admins can't demote, suspend or delete
      themselves, and there's always at least one active admin.
    - An activity log of who created, changed, suspended, reset or deleted what, and when.
    - Server settings: sign-up, inspection quotas and pausing, email status, retention and the Claude
      login.
- **The server's Claude login is shared.** When it's signed in, every visitor can run
  Claude-backed inspections on it.
- **Inspection targets are constrained** by skillspector: https only, an allowlist of Git and download
  hosts, private and internal addresses refused, no redirects followed, and size limits on clones,
  archives and downloads. An MCP server inspection reads only the server's entry from the MCP Registry's
  API (`registry.modelcontextprotocol.io`): nothing it points to is downloaded, installed or run.
- **Uploaded skills are kept only while they're inspected.** A `.zip` or `.md` file up to 25 MB, checked
  before it's queued (a valid archive, within skillspector's size and entry limits, no paths leaving
  it), and unpacked by skillspector with its own zip safeguards. It's deleted when the inspection ends,
  whether it succeeded or failed; the history keeps only its file name. Uploads an inspection never got to
  are swept when the API starts.
- **Shared reports are public to whoever has the link.** An inspection's owner (or an admin) can share its
  report at an unguessable link (192 random bits) that anyone can open without signing in, until
  it's revoked; creating and revoking links is in the activity log. A shared page shows the report
  and its target, and leaves out the account's AI token use and its comparison with earlier inspections.
  Each address may open 120 shared pages or downloads a minute.
  - **Links are stored as their SHA-256 hash**, as session and API tokens are: a copy of the
    database opens no shared report. With `SECRET_KEY`, the link is also kept encrypted, so its
    owner can copy it again; without it, it's shown once when it's made, and "New link" replaces
    it. Links from before were hashed when the API first started on this version, and still work.
  - A status badge's report link opens the inspection on the badge by its id (`/shared/badge-<id>`),
    only while it's on the badge: it never reveals the share link.
- **Names that read as something else are flagged.** A skill's name, its file paths and the
  inspected target come from the skill. Wherever the UI shows one, invisible characters and
  bidirectional controls (a right-to-left override) are shown as their code points, a letter from
  another alphabet in a word (a Cyrillic а in `reаd_data`) is marked, and a warning icon lists them.
  Page titles write them as code points.
- **Status badges show only what an owner put on them.** A badge (`/badge?target=…`) shows the
  verdict and date of the latest inspection of a link that its owner shared and then put on the badge, and
  links to that shared report. A private inspection, or one only shared by link, never shows; revoking the
  link takes the inspection off. An inspection with a baseline, uploaded or shipped by the skill, can't be put on
  a badge, since the findings it accepts don't count, nor can an upload. Anyone may put their own genuine inspection of a public link on
  its badge, and the latest one shows. Badges are cached for 5 minutes, so a change can take that
  long to show. They aren't rate limited, so GitHub's image proxy isn't refused: each is one indexed
  lookup, and never starts an inspection.
- **A baseline the skill ships is applied only when asked.** A skill can carry its own
  `.skillspector-baseline.yaml`, which suppresses findings, and its author wrote it. An inspection applies it
  only when the user turns on "Use the baseline the skill ships" for that inspection, and never alongside
  their own baseline file. It's read from the copy of the skill being inspected (at the same ref, so
  the API never fetches the target separately), only at the skill's top,
  never through a symbolic link, and checked like an uploaded one (skillspector must load it, up to
  256 KB). Otherwise it's left unread, and the report says it's there but not applied; when it
  is applied, the page says the findings it suppresses were accepted by the skill's author.
- **Where inspections run.** Targets are fetched and analysed inside the API process.
  - **What contains it** (`docker-compose.yml`): the API runs as an unprivileged user (UID
    10001) with no Linux capabilities and `no-new-privileges`, on a read-only filesystem where only
    its data, its home (the Claude login) and an in-memory `/tmp` can be written, with memory and
    process limits. The web app gets the same, as user `node`. Base images are pinned by digest.
  - **What doesn't:** that process also holds `SECRET_KEY`, the database and the server's Claude
    login, so a flaw in skillspector's handling of a skill would reach them. Inspections don't run in a
    sandbox of their own, and the container still has the network. Run the server for people you
    trust, as above.
- **Custom AI base URLs are allowed by default.** A visitor-supplied Base URL makes the server send
  requests to that address — another reason not to expose the app without authentication.
  `INSKECT_ALLOW_CUSTOM_AI_URL=false` refuses them, and `INSKECT_AI_PROVIDERS`
  limits the providers inspections may use.
- **API keys.**
  - A key pasted for one inspection is held in memory while that inspection runs and, with `SECRET_KEY`, kept
    encrypted until it has run, so a restart can run it again; then it's deleted.
  - A Claude key a user saves to their account (Account → Claude) is checked with Anthropic,
    encrypted with `SECRET_KEY` and bound to that user, and only ever shown back as a hint
    (`…a1b2`). It's decrypted only for that user's own inspections, and deleted on disconnect or
    account deletion.
  - Keys never appear in API responses, including validation errors, nor in logs, the activity
    log or browser storage.
- **Private GitHub repositories.** A user can connect GitHub (Account → GitHub), through the
  server's GitHub App, to inspect their private repositories ([setup](./CONFIGURATION.md#private-github-repositories)).
  - The app's only permission is reading repository contents, in the repositories the user chose.
    Its tokens are the user's own: they read only what both the user and the app's installation
    can, so no one reaches another user's repositories, even with the same link.
  - The tokens, and their refresh token, are encrypted with `SECRET_KEY`, bound to the user, and
    never shown, logged or sent in a response, the activity log or an inspection's
    request. They're refreshed when they expire; disconnecting deletes them here and revokes them
    at GitHub, and so does deleting the account. Connecting and disconnecting are in the activity
    log.
  - When an inspection is queued, a GitHub link is checked with its owner's token: a public repository is
    inspected as before, without it. A private one is marked as such, and the token is fetched from
    the inspection's owner only when it runs. The API clones the repository itself with the token in the clone's own environment, never on its
    command line, in a file or in the API's environment, and inspects the copy, deleted afterwards.
  - A private repository's inspection is its owner's: it isn't shared or put on a badge unless they
    confirm, and only they open its report, logs and downloads. An admin sees that it exists, and
    may delete it or revoke its link.
  - The host allowlist, size limits and private-address rules stay in force.
- **Abuse limits.** Inspections are limited per signed-in user, and per client IP across every account
  signed in from it; sign-in, sign-up and password reset attempts per client IP; failed sign-ins per account. A refused request
  gets a `429` saying when to try again.
  - **Quotas** (off by default) cap each user's inspections per 24 hours and in progress at
    once, and users see their usage on the Account page. Admins have no quota. An admin can give
    one user their own quotas, more or fewer, from that user's page; the change is in the activity
    log.
  - **Pausing:** an admin can pause new inspections for everyone from the backoffice (Settings → Inspections),
    without a redeploy. New inspections then get a `503`, and inspections already running finish.
  - With Postgres, the counts live in the database, so they hold across restarts.
- **Who the API answers, and whose address it counts.** The browser only talks to the web app,
  which calls the API. The per-IP limits count the visitor's address, which the web app passes on in
  its own header (`X-Inskect-Client-IP`).
  - **The proxy secret.** With `INSKECT_PROXY_SECRET` set on both, every call carries it
    and the API refuses any other (`403`), the per-IP limits included. Set it when the API can be
    reached other than through the web app. The address travels in a header of the app's own, which
    the API believes only alongside the secret, since proxies on the way may rewrite
    `X-Forwarded-For`.
  - **Behind a reverse proxy,** set `NUXT_TRUST_PROXY=true` on the web app: otherwise
    every visitor seems to come from the proxy and shares its limits. The web app notices requests
    carrying `X-Forwarded-For` while it's off; both logs warn, and the backoffice's health panel
    says so for a day ([REVERSE_PROXY.md](./REVERSE_PROXY.md)).
- **Requests from other sites.** The session cookie is `SameSite=Lax`, which stops other sites'
  pages from sending it with a `POST`. On top of that, the web app refuses (`403`) any
  state-changing `/api` request a page from another site sends, a sibling subdomain included (it
  counts as the same site for the cookie): it reads `Sec-Fetch-Site`, or else `Origin`. Scripts
  using an API token aren't affected. After signing in, `?redirect=` only ever leads to a path on
  this site.
- **Signing in with GitHub** (with the GitHub App set up) knows a GitHub account by its numeric ID,
  never its login, which can change. The state GitHub sends back is encrypted, expires after 10
  minutes, is redeemed once, and must match a nonce in the browser that started (an httpOnly
  cookie): it can't be completed from another browser. GitHub's token is read for who the user is
  and their verified email, then revoked: signing in gives no access to repositories. A GitHub
  account is never linked to an existing account because the emails match; its owner links it
  after signing in with their password. Suspended accounts are refused, sessions are rotated as
  for a password, the last way to sign in can't be removed, and "Sign out everywhere" and a
  password reset apply as usual. An account made with GitHub has no password: what asks for the
  password again asks it for a sign-in in the last 10 minutes instead.
- **Creating an API token asks for the password again,** since a token outlives the session that
  makes it: a borrowed browser or a stolen cookie isn't enough. Attempts are limited to 5 per
  account per 15 minutes.
- **Security headers.** Every page and API response from the web app carries them
  (`server/middleware/security-headers.ts`):
  - **`Content-Security-Policy`:** scripts only from this server, or inline with a nonce made for
    that response, which Nuxt's own three inline scripts carry. An inspected skill's text that ever
    made it into a page as markup still couldn't run. Styles may be inline (Vue's style bindings),
    connections go to this server only (plus any origin in `NUXT_CSP_CONNECT_SRC`), plugins
    and `<base>` are refused, and forms post only here. Violations are reported to
    `/api/csp-report` and logged ([monitoring](./MONITORING.md#structured-log-events)).
    - `NUXT_CSP_REPORT_ONLY=true` only reports the policy (`Content-Security-Policy-Report-Only`),
      so what enforcing it would block shows in the logs first.
    - The status badge sends a stricter policy of its own.
  - **Framing:** `frame-ancestors 'none'` and `X-Frame-Options: DENY`: no page can be framed, the
    backoffice, account deletion and token creation included.
  - **`Referrer-Policy`:** `same-origin`, so other sites never see a page's address, and
    `no-referrer` on a shared report, whose address is its secret.
  - **`X-Content-Type-Options: nosniff`**, and a **`Permissions-Policy`** turning off the camera,
    microphone, location, payments, USB and Topics.
  - **`Strict-Transport-Security`** (a year, without subdomains) on HTTPS requests. Behind a reverse
    proxy that terminates TLS, set `NUXT_TRUST_PROXY` so its `X-Forwarded-Proto` is believed.
    Static files (`/_nuxt/`) are served without them: they're not pages.

## Analytics

None ships: the app makes no request to any analytics service. `useAnalytics()` (in
`app/composables/`) is a hook a build can wire to one, and does nothing otherwise. Its events carry
no email, target or id (*Sign Up*; *Scan Started*, with the source and whether AI review was on;
*Scan Viewed*, with the status and verdict), and `app/utils/analytics.ts` reduces a page's address to
its route's pattern (`/scan/[id]`), never its path or query string.

Found a vulnerability? Please report it privately — see [SECURITY.md](../SECURITY.md).
