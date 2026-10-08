# Contributing

Thanks for helping improve Inskect. Issues and pull requests are welcome.

## Development setup

```bash
pnpm install
pnpm setup                 # choose "Local processes"

cd backend && uv run uvicorn app.main:app --reload            # API on :8000
NUXT_API_BASE=http://localhost:8000 pnpm dev                  # UI on :3000
```

Requirements: Node.js 22 or later (CI and the images use 24) with pnpm, Python 3.12–3.14 with [uv](https://docs.astral.sh/uv/).

Or in Docker, with hot reload and the checkout bind-mounted (`docker-compose.yml` is the
production install, not this):

```bash
docker compose -f docker-compose.dev.yml up --build   # UI on :3005
```

> [!TIP]
> If you also run the Docker Compose stack from the same checkout, run backend commands inside the
> container (`docker exec inskect-api uv run pytest -n auto`). The dev containers bind-mount the
> repository, so a host-side `uv` or `pnpm install` rewrites the environment the running containers
> depend on.

## Checks

CI runs all of these on every pull request; please run them before pushing.

| Area | Command |
|---|---|
| Frontend lint | `pnpm lint` |
| Frontend types | `pnpm typecheck` |
| Frontend tests | `pnpm test` |
| Frontend build | `pnpm build` |
| Backend lint | `cd backend && uv run ruff check .` |
| Backend tests | `cd backend && uv run pytest -n auto` (on every core) |
| Dependency audits | `pnpm audit --prod --audit-level high` and `cd backend && uv audit --no-dev --frozen` |
| Dependency licenses | `cd backend && uv run --no-dev python ../scripts/check-python-licenses.py`, and the npm check in CI |
| Forbidden references | `scripts/check-references.sh` |
| Secrets | gitleaks, with [`.gitleaks.toml`](./.gitleaks.toml) |
| Self-hosted install | `scripts/smoke-test.sh`: Docker Compose from a fresh checkout, then one inspection |

CI also builds both Docker `production` targets.

A new dependency's license must be one the AGPL-3.0 can include: the license checks fail
otherwise. `scripts/check-references.sh` keeps out mentions of other deployments' platforms and
private code, and the former product name.

## Screenshots

The README's screenshots (`docs/assets/screenshot-*.png`) come from `pnpm screenshots`
([`scripts/screenshots.mjs`](./scripts/screenshots.mjs)): the home page, a report, the Account page
and the backoffice, in both themes. Retake them after a UI change.

Run it against a server of its own, never one with real users: on an empty database it creates
`admin@example.com` and `alex@example.com` and inspects a few public example skills as Alex. Give that
server accounts, quotas (so the Account page shows usage) and a throwaway `SECRET_KEY` (so it shows
the Claude key), and nothing from your `.env.local`:

```bash
# An API on its own database, next to the dev stack (docker compose -f docker-compose.dev.yml up).
docker run -d --name inskect-shots-api --network inskect_internal --network-alias shots-api \
  -v "$PWD/backend:/app" -v /dev/null:/app/.env.local:ro -v inskect-shots-data:/tmp/shots \
  -e INSKECT_AUTH=accounts -e INSKECT_DB_PATH=/tmp/shots/scans.db \
  -e INSKECT_DAILY_SCAN_QUOTA=20 -e INSKECT_CONCURRENT_SCAN_QUOTA=2 \
  -e INSKECT_SECRET_KEY="$(docker exec inskect-api uv run --no-sync python -m app.secrets_box)" \
  inskect-api uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000

# A production build of the web app on it (the dev server adds its own overlay).
pnpm build && NUXT_API_BASE=http://shots-api:8000 PORT=3200 node .output/server/index.mjs  # in the web container

# The screenshots, with Playwright's own browser.
docker run --rm --network inskect_internal --user "$(id -u):$(id -g)" -e HOME=/tmp \
  -e BASE_URL=http://inskect-web:3200 -v "$PWD:/work" -w /work \
  mcr.microsoft.com/playwright:v1.63.0-noble node scripts/screenshots.mjs
```

Running it again reuses the inspections, so their times read "minutes ago" rather than "seconds ago".
Then `docker rm -f inskect-shots-api && docker volume rm inskect-shots-data`.

## Contributor license agreement

Before your first pull request can be merged, you sign the [contributor license agreement](./CLA.md)
once, for all your contributions. Inskect is published under the AGPL-3.0 and its maintainer also
offers services built on it under other terms; the agreement lets your contribution be used in
both. You keep your copyright.

A bot comments on your pull request: reply with the sentence it gives, and the **CLA** check
turns green. Every author of the pull request's commits signs, with a commit email linked to their
GitHub account. Signatures are recorded in `signatures.json` on the `cla-signatures` branch.

## Pull requests

- Keep each pull request to one change, with tests when behaviour changes.
- Use [Conventional Commits](https://www.conventionalcommits.org/) for commit messages and pull
  request titles — `feat:`, `fix:`, `docs:`, `test:`, `build:`, `chore:`, and `!` after the type
  for a breaking change (`feat!:`). Pull requests are squash-merged, and each release's notes are
  generated from these prefixes ([`cliff.toml`](./cliff.toml)).
- Pin a new GitHub Action by commit SHA, with its version in a comment, as the workflows do.
- Match the surrounding code style: the ESLint config (via `@nuxt/eslint`) for the frontend,
  Ruff for the backend.
- API routes are plain `def` unless they await something: FastAPI runs those in its threadpool. An
  `async def` route runs on the event loop, so its database calls and other blocking work go
  through `asyncio.to_thread`, or they stall every other request.

## Releases

Inskect follows GitHub flow: `main` is always releasable, work lands from short-lived `feat/` and
`fix/` branches, and a release is a signed tag on `main`. Nothing is bumped in the code: the
version comes from the tag, stamped into the images when they're built, and the API reports it in
`/health` (`dev` for anything built from a checkout).

```sh
git switch main && git pull
git tag -s v1.2.0 -m v1.2.0   # or v1.2.0-rc.1, -beta.1, -alpha.1 for a pre-release
git push origin v1.2.0
```

The tag must be signed by a key listed in [`.github/allowed_signers`](./.github/allowed_signers):
the workflow checks it, and an unsigned tag, a lightweight one or one signed by another key
publishes nothing. A new maintainer adds their signing key there, in a pull request.

The tag runs [the release workflow](./.github/workflows/release.yml), after CI passes on the
tagged commit:

- **`vX.Y.Z`** publishes `ghcr.io/inskect/inskect-api` and `ghcr.io/inskect/inskect-web` tagged
  `X.Y.Z`, `X.Y`, `X` and `latest`, creates the GitHub Release marked *Latest*, and moves the
  major tag `vX` that the GitHub Action is used by (`inskect/inskect@v1`).
- **`vX.Y.Z-alpha.N`, `-beta.N`, `-rc.N`** publish the images tagged with that version and `beta`,
  and a GitHub Release marked *Pre-release*. `latest`, `X`, `X.Y` and `vX` don't move.
- **Build once, promote.** Tag `vX.Y.Z` on a commit that already has a `vX.Y.Z-rc.N` tag, and the
  release candidate's images are re-tagged rather than rebuilt: the stable images have the same
  digest as the ones you tested.

The release notes list what changed since the previous release: since the previous stable tag
for a stable release, folding in its release candidates, and since the previous tag of any kind
for a pre-release. To see what the next one would say: `git cliff --unreleased --strip all`.
