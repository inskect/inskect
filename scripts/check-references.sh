#!/usr/bin/env bash
# Fails when the code or the docs mention what this repository mustn't: another deployment's
# platform or private code, or the product's former name. CI runs it on every pull request.
#
#   scripts/check-references.sh
set -euo pipefail

# Each a Perl regex, case-insensitive. "self-hosted" is fine, and so is GitHub's "hosted runners".
FORBIDDEN=(
  'vercel'
  '(?<!self-)\bhosted\b(?! runners)'
  '\bbotid\b'
  'inskect-cloud'
  'skillspector[-_ ]web'
  'skillspector-cloud'
  'x-skillspector-'
  'skillspector_session'
)
# Generated, or a record of the past.
EXCLUDE=(':!pnpm-lock.yaml' ':!backend/uv.lock' ':!CHANGELOG.md' ':!scripts/check-references.sh')

status=0
for pattern in "${FORBIDDEN[@]}"; do
  if git grep -nIiP "$pattern" -- . "${EXCLUDE[@]}"; then
    echo "::error::Forbidden reference matching /$pattern/ (see above)"
    status=1
  fi
done
exit "$status"
