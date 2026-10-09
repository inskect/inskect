# Extending

Inskect runs as is with Docker Compose. A deployment that needs something else (inspections in
their own isolated environment, uploads in object storage, extra endpoints) can change it without
forking the code: replace a piece through a setting, wrap the API, or layer the web app.

## Replaceable pieces

Each is a class named by its import path, `module:Class`, made with no arguments when the API
starts. A path that can't be loaded stops the API there, naming the setting.

| Setting (`INSKECT_…`) | Default | What it does |
|---|---|---|
| `JOB_RUNNER` | `app.jobs.in_process:InProcessRunner` | Takes queued inspections and runs them, each through `scanner.run_job()`. |
| `SCAN_EXECUTOR` | `app.scanner:LocalExecutor` | Fetches and analyses an inspection's target, and returns skillspector's report. |
| `UPLOAD_STORE` | `app.uploads:LocalUploadStore` | Holds an uploaded skill from when its inspection is queued until it ends. |

The module must be importable by the API: install it in the API's environment, or put it on
`PYTHONPATH`.

### Job runner

`app/jobs/base.py`'s `JobRunner`:

- `on_startup()`: called once when the API starts, before it takes requests.
- `is_full()`: whether a new inspection should be refused with `503`.
- `check(llm)`: raise `JobRejectedError` for an inspection this runner can't run as asked; its message is
  shown to the user.
- `async submit(job)`: take a freshly created, `pending` inspection. Run it, now or later, with
  `await scanner.run_job(job)`, which records its progress and outcome.

A runner that runs inspections in another process passes on the inspection's id, and rebuilds the `Job` there
from the stored inspection (`db.get_scan()`), as `app/jobs/in_process.py` does after a restart, with the
one-off AI credentials held encrypted for it (`claude_key.held_llm_for_scan()`).

### Scan executor

`app/scanner.py`'s `ScanExecutor`:

- `async run(job, *, token) -> dict`: inspect `job.target`, or the upload `job.upload` (read it with
  `uploads.read()` or `uploads.local_copy()`), and return skillspector's report. Raise to fail the
  inspection: the exception's message is shown. `token` is the owner's GitHub token for a private
  repository (`job.private_source`), `None` otherwise; `repo_connections.auth_headers(token)` gives
  the headers GitHub expects.

`app/scan_runner.py` runs one inspection on its own, with the standard library and skillspector only,
and reports each step, log line and the final report on stdout as tagged JSON lines: copy it to an
isolated environment, run it there, and relay its events with `scan_logs.append()` and
`scan_logs.increment_progress()`. `analysis_settings.skillspector_env()` is the environment it needs.

### Upload store

`app/uploads.py`'s `UploadStore`:

- `kind` and `max_bytes`: its name, which `/health` reports, and the largest file it takes.
- `save(scan_id, name, data) -> str`: keep the file (called in a thread), and return the reference
  stored with the inspection.
- `async read(ref)`, `local_copy(ref, name)` (an async context manager giving a path), and
  `async delete(ref)`.
- `clear(keep)`: on startup, delete the files of every inspection whose id isn't in `keep`.

## Wrapping the API

The API is a FastAPI app, `app.main:app`, in the `inskect-api` package. Install it at a release in
your own project:

```toml
dependencies = [
    "inskect-api @ git+https://github.com/inskect/inskect.git@v1.1.0#subdirectory=backend",
]
```

It reports its version as `INSKECT_VERSION`, which the release's images set: set it too. Then serve
your own module instead, which imports it and adds to it:

```python
from app.main import app
from app.monitoring import Measure, Rule, register_rule

from my_deployment import routes

app.include_router(routes.router)
register_rule(Rule("worker_errors", "Scan workers are failing", "Any worker error",
                   "worker_error", 30 * 60, 60 * 60, measure_worker_errors, label="Worker errors"))
```

- **Routes** that start an inspection go through `app.api.routes.scan.queue_scan()`, which applies the
  same checks as the built-in ones (pause, rate limits, quotas, the runner's limits) and records
  the inspection.
- **Alert rules:** `monitoring.record(kind, message)` stores an event and checks the rules for its
  kind; `register_rule()` adds one, which the Monitoring page then lists. Give the rule a `label`,
  e.g. `label="Worker errors"`, and the health panel counts its events, which the Monitoring page
  can also filter by.
- **Retention on a schedule:** with `INSKECT_RETENTION_LOOP=false`, call
  `retention.sweep_once()` from your own scheduler instead of the hourly task.
- **AI review:** `INSKECT_AI_PROVIDERS`, `ALLOW_CUSTOM_AI_URL` and `CLAUDE_CLI` limit what
  inspections may use ([configuration](./CONFIGURATION.md)).

## Layering the web app

The web app is a Nuxt app, which another one can extend as a
[Nuxt layer](https://nuxt.com/docs/getting-started/layers): add pages, components, server routes
and plugins, or replace one with a file at the same path. Install it at a release, with Nuxt:

```json
"dependencies": {
  "inskect": "github:inskect/inskect#v1.1.0",
  "nuxt": "^4"
}
```

then extend it in `nuxt.config.ts`, with `extends: ['inskect']`. Its install script isn't needed:
with pnpm, deny it in `pnpm-workspace.yaml`'s `allowBuilds` (`inskect: false`).
To typecheck it (`nuxt typecheck`), install `typescript`, `vue-tsc` and `@types/node` too.
Import this app's files by relative path: in the extending app, `~` and `~~` are its own
directories, which the lint rule in `eslint.config.mjs` enforces here. `scripts/check-layer.sh`
builds and typechecks such an app, which CI runs on every change.

- **Pages of its own, public:** list them in `app.config.ts`'s `site.publicPages`, e.g.
  `['/terms', '/privacy']`. Anyone may open them signed out, search engines may index them, and
  the sitemap lists them.
- **Footer links:** `site.footerLinks`, as `[{ label, to }]`.
- **Notices:** `SignupNotice` (above the sign-up button) and `AccountDeletionNotice` (under what
  deleting an account removes) render nothing. A component of the same name in the extending app
  takes their place, e.g. to link its terms or privacy policy.
- **Wording:** `site.privacyLink` (`{ label, to }`) replaces the landing page's link to the security
  model, and `site.costAnswer` the FAQ's answer to what it costs. The landing page describes AI
  review from the providers the API allows (`INSKECT_AI_PROVIDERS`, `ALLOW_CUSTOM_AI_URL`).
- **Analytics:** `useAnalytics()` (`app/composables/`) tracks a few events, and does nothing until
  a plugin provides `$track`. `app/utils/analytics.ts` reduces an address to its route's pattern,
  so no token, id or inspected link leaves the browser.
- **Content-Security-Policy:** `NUXT_CSP_CONNECT_SRC` adds origins the browser may send requests
  to, for a service a layer talks to.
