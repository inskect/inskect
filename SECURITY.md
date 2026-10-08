# Security policy

Inskect helps people decide whether to trust third-party code, so security reports are
taken seriously.

## Reporting a vulnerability

Please **do not open a public issue**. Report it privately through GitHub:
[**Security → Report a vulnerability**](https://github.com/inskect/inskect/security/advisories/new).

Include what you found, how to reproduce it, and the impact you expect. You'll get an
acknowledgement, and a fix or mitigation will be coordinated with you before anything is
disclosed.

Vulnerabilities in the scanning engine itself belong to
[NVIDIA/skillspector](https://github.com/NVIDIA/skillspector/security). When a flaw in the engine
reaches Inskect (an inspected skill running code on the server, say), report it here too:
the fix may need both.

## Supported versions

Only the latest release receives security fixes.

## What it protects

[docs/SECURITY_MODEL.md](./docs/SECURITY_MODEL.md) describes every boundary in detail. In short,
Inskect runs two ways:

- **Without accounts** (`AUTH=none`, the default): anyone who can reach it has full access, admin
  included. It's meant for a private network or behind your own sign-in.
- **With accounts** (`AUTH=accounts`): users see only their own inspections; admins manage the server
  from the backoffice.

## In scope

Reports that show one of these boundaries giving way, for example:

- **Reaching what belongs to another user:** their inspections, reports, logs or uploads, their saved
  Claude key, API tokens or GitHub connection, or a private repository's report (which even admins
  can't open).
- **Acting as someone else:** signing in as another user, becoming an admin, or getting a session,
  an API token, a reset link or a sign-up link that isn't yours. Using an API token for more than
  starting and reading inspections.
- **Opening a shared report without its link**, or after it was revoked, or getting a share link
  back from a status badge or from the database, where links are stored hashed.
- **Running code on the server** from an inspected skill or an upload, or getting past the
  container's hardening (a non-root user, no capabilities, a read-only filesystem).
- **Inspecting what shouldn't be:** private or internal addresses, hosts off the allowlist, or
  redirects to them.
- **Getting around the limits:** quotas, rate limits (per user, per address, failed sign-ins per
  account), pausing, or the proxy secret that keeps the API reachable only through the web app.
- **Forging a status badge:** one showing a verdict nobody put on it, or an inspection made with a
  baseline.
- **Injecting into what the app shows or sends:** script or markup in a page through a skill's
  content or names (getting past the Content-Security-Policy, or a name that reads as another
  without being flagged), workflow commands or Markdown in the GitHub Action's log and comments, a
  cross-site request that changes something, or a redirect to another site after signing in.
- **Telling which emails have an account**, through sign-in, password reset, or sign-up when
  email is set up.

## Out of scope

Trade-offs the [security model](./docs/SECURITY_MODEL.md) documents on purpose:

- Full access for anyone who can reach an `AUTH=none` install.
- Every visitor of a server sharing its Claude login, when it's signed in.
- Custom AI base URLs, which make the server send requests to any address
  (`INSKECT_ALLOW_CUSTOM_AI_URL=false` turns them off).
- Inspections running in the API process, which also holds its secrets: a flaw in the engine
  reaching them is the engine's (see above), the sharing of the process isn't.
- Sign-up telling that an email is taken when the server sends no email.
- Locking an account out of signing in for up to a day by failing to sign in with its email, the
  price of slowing password guessing.
- Shared reports and badged inspections being public: that's what sharing is.

And, as usual: denial of service by volume, social engineering, attacks that need a compromised
device or browser, reports from automated scanners without a demonstrated impact, and the
third-party services it talks to (GitHub, AI providers), which have their own programs. Hardening suggestions without an exploit are welcome as ordinary issues.

## Testing

Test against your own install. On a server someone else runs, use only accounts of your own, don't
touch anyone else's data, and don't degrade the service for others.
