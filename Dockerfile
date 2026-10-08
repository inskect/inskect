# By digest: a tag can be moved to other contents. Update the digest with the tag.
FROM node:24-bookworm-slim@sha256:0e0ff40c39bc087845bfb27465a0df4ea419520094bc35842ff83dd8cbe6f9b6 AS base
WORKDIR /app
ENV CI=1
RUN corepack enable && corepack prepare pnpm@11.20.0 --activate

FROM base AS dependencies
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

FROM dependencies AS build
COPY --link . .
ENV NODE_ENV=production
RUN pnpm run build

FROM base AS development
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile
COPY --link . .
CMD [ "pnpm", "run", "dev" ]

FROM base AS production
ARG PORT=3000
ENV PORT=$PORT
ENV NODE_ENV=production

COPY --from=build /app/.output /app/.output

USER node
EXPOSE $PORT
CMD ["node", ".output/server/index.mjs"]
