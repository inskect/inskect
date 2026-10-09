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
# What an extending app adds (docs/EXTENDING.md): a public page, a footer link, and a component of
# its own in place of the layer's.
cat > "$work/app/app/app.config.ts" <<'EOF'
export default defineAppConfig({
  site: {
    publicPages: ['/layer-check'],
    footerLinks: [{ label: 'Layer check link', to: '/layer-check' }]
  }
})
EOF
mkdir -p "$work/app/app/components"
cat > "$work/app/app/components/SignupNotice.vue" <<'EOF'
<template>
  <p>Notice from the extending app</p>
</template>
EOF

cd "$work/app"
pnpm install --reporter=append-only
pnpm exec nuxt typecheck
pnpm exec nuxt build

NUXT_API_BASE=http://127.0.0.1:9 NUXT_PUBLIC_SITE_URL=https://layer.example PORT=$port node .output/server/index.mjs &
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
check / 'Layer check link'
check /signup 'Notice from the extending app'
check /sitemap.xml '<loc>https://layer.example/layer-check</loc>'
indexed() { ! curl -sfI "http://127.0.0.1:$port$1" | grep -qi '^x-robots-tag: noindex'; }
indexed /layer-check || { echo "::error::/layer-check, a public page, says noindex"; exit 1; }
! indexed /history || { echo "::error::/history doesn't say noindex"; exit 1; }
echo "robots: ok"
