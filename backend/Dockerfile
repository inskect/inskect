# Base images by digest: a tag can be moved to other contents. Update the digest with the tag.
FROM python:3.13-slim@sha256:3dd7cc108ec1493442514f5c2a871af6af0ec31d768ff6e378a93340c3b3db5f AS base

# git: uv fetches skillspector from GitHub, and skillspector clones Git scan targets.
# Every locked dependency ships prebuilt wheels, so no compiler toolchain is needed.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

ARG CLAUDE_CODE_VERSION=2.1.259
COPY --from=node:24-bookworm-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6 /usr/local/bin/node /usr/local/bin/node
COPY --from=node:24-bookworm-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6 /usr/local/lib/node_modules /usr/local/lib/node_modules
# npm's and uv's caches are cache mounts: kept between builds, never in an image.
RUN --mount=type=cache,target=/root/.npm \
    ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}

COPY --from=ghcr.io/astral-sh/uv:0.12.9@sha256:8b940d3a9d65bed080436972241af2e21c84b5e8c9193f7014ed71479ee795ff /uv /usr/local/bin/uv
# The cache mount is another filesystem, which uv can't hard-link from.
ENV UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
# Without the dev dependencies: the production image is built on this, and they'd stay in its layers.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

FROM base AS development
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

FROM base AS production
# The release, from its Git tag (.github/workflows/release.yml): the API reports it in /health.
ARG VERSION=dev
ENV INSKECT_VERSION=$VERSION
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev
# Scans run untrusted skills' code paths in this process: not as root. Its own home holds the
# Claude CLI's login (the claude_cli_auth volume), and data/ the database and uploads; with
# docker-compose.yml everything else is read-only (docs/SECURITY_MODEL.md).
RUN useradd --uid 10001 --user-group --create-home --home-dir /home/app --shell /usr/sbin/nologin app \
    && mkdir -p /app/data && chown app:app /app/data
ENV HOME=/home/app \
    PATH=/app/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1
USER app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
