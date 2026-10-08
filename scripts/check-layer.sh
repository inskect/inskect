#!/usr/bin/env bash
# Builds and typechecks a small app that extends this one as a Nuxt layer, the way another
# deployment does (docs/EXTENDING.md#layering-the-web-app), and checks it serves both apps' pages. The layer is
# this checkout's tracked files, uncommitted changes included, installed as a package: with its
# dependencies but not its development ones, as from `github:inskect/inskect#vX.Y.Z`.
set -euo pipefail

root=$(git rev-parse --show-toplevel)
work=$(mktemp -d)
port=${LAYER_CHECK_PORT:-3097}
server=
cleanup() {
  [ -n "$server" ] && kill "$server" 2>/dev/null
  rm -rf "$work"
}
trap cleanup EXIT

snapshot=$(git -C "$root" stash create)
git -C "$root" archive --prefix=package/ -o "$work/inskect.tgz" "${snapshot:-HEAD}"

version() { node -p "const p = require('$root/package.json'); p.dependencies['$1'] ?? p.devDependencies['$1']"; }
mkdir -p "$work/app/app/pages"
cat > "$work/app/package.json" <<EOF
{
  "name": "layer-check",
  "private": true,
  "type": "module",
  "dependencies": {
    "inskect": "file:../inskect.tgz",
    "nuxt": "$(version nuxt)"
  },
  "devDependencies": {
    "@types/node": "$(version @types/node)",
    "typescript": "$(version typescript)",
    "vue-tsc": "$(version vue-tsc)"
  }
}
EOF
# Install scripts: none needed; the layer's own (nuxt prepare) is for working on this repository.
cat > "$work/app/pnpm-workspace.yaml" <<'EOF'
allowBuilds:
  '@parcel/watcher': false
  '@tailwindcss/oxide': false
  esbuild: false
  inskect: false
  unrs-resolver: false
  vue-demi: false
EOF
cp "$root/tsconfig.json" "$work/app/"
cat > "$work/app/nuxt.config.ts" <<'EOF'
export default defineNuxtConfig({ extends: ['inskect'] })
EOF
cat > "$work/app/app/pages/layer-check.vue" <<'EOF'
<template>
  <p>Served by the extending app</p>
</template>
EOF

cd "$work/app"
pnpm install --reporter=append-only
pnpm exec nuxt typecheck
pnpm exec nuxt build

NUXT_API_BASE=http://127.0.0.1:9 PORT=$port node .output/server/index.mjs &
server=$!
for _ in $(seq 1 30); do
  curl -sf "http://127.0.0.1:$port/" >/dev/null && break
  sleep 1
done

check() {
  local body
  body=$(curl -sf "http://127.0.0.1:$port$1") || { echo "::error::$1 didn't answer"; exit 1; }
  grep -q "$2" <<<"$body" || { echo "::error::$1 doesn't contain \"$2\""; exit 1; }
  echo "$1: ok"
}
check / '— Inskect</title>'
check /history 'Inspection history'
check /layer-check 'Served by the extending app'
