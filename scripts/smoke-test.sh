#!/usr/bin/env bash
# The self-hosted install from a fresh clone, as the README gives it: production images with Docker
# Compose, nothing configured but backend/.env.example, then one scan of an uploaded skill.
# CI runs it on every pull request; it leaves nothing behind.
#
#   scripts/smoke-test.sh
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:3005}"
compose=(docker compose -p inskect-smoke -f docker-compose.yml)
work="$(mktemp -d)"
copied=false
cleanup() {
  status=$?
  [ "$status" -eq 0 ] || "${compose[@]}" logs --tail 50 >&2 || true
  "${compose[@]}" down -v >/dev/null 2>&1 || true
  if $copied; then rm -f backend/.env.local; fi
  rm -rf "$work"
  exit "$status"
}
trap cleanup EXIT

# A fresh clone has no settings file: start from the example, as the README says.
if [ ! -e backend/.env.local ]; then cp backend/.env.example backend/.env.local; copied=true; fi
"${compose[@]}" up -d --build --wait --wait-timeout 300

# Through the web app, past its few seconds of cache: the API answers it.
for attempt in $(seq 1 30); do
  health=$(curl -fsS "$BASE_URL/api/health?fresh=1" || true)
  [[ "$health" == *'"status":"ok"'* ]] && break
  [ "$attempt" -lt 30 ] || { echo "Unhealthy: $health" >&2; exit 1; }
  sleep 2
done

printf -- '---\nname: smoke\ndescription: A harmless skill.\n---\n\nSay hello.\n' > "$work/SKILL.md"
id=$(curl -fsS -F "file=@$work/SKILL.md;filename=SKILL.md" -F 'options={}' "$BASE_URL/api/scan/upload" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')
[ -n "$id" ] || { echo "The scan wasn't queued" >&2; exit 1; }

for _ in $(seq 1 90); do
  scan=$(curl -fsS "$BASE_URL/api/scan/$id")
  case "$scan" in
    *'"status":"done"'*) echo "Scanned: $(echo "$scan" | grep -o '"recommendation":"[A-Z_]*"')"; exit 0 ;;
    *'"status":"error"'*) echo "The scan failed: $scan" >&2; exit 1 ;;
  esac
  sleep 2
done
echo "The scan didn't finish in 3 minutes" >&2
exit 1
