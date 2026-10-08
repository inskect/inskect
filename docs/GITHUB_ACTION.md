# GitHub Action

Inspect every skill a pull request changes before it's merged. The action finds the skills the pull
request touches, inspects each one on your Inskect server, and:

- fails the check when a skill's verdict is *Rejected* (or another threshold you set),
- comments on the pull request with each skill's verdict, risk score and a link to its report,
  updating the same comment on every push,
- uploads the findings to GitHub code scanning, so they show up as alerts on the changed lines.

A pull request that touches no skill skips inspecting and passes, without a comment unless you set
`comment: always`.

## Setup

1. On your server, open **Account** → **API tokens** → **New token** and copy the token
   (`sst_…`). Without accounts (`INSKECT_AUTH=none`), skip this step.
2. In the repository, add it as a secret: **Settings** → **Secrets and variables** → **Actions** →
   **New repository secret**, named `INSKECT_TOKEN`.
3. Add the workflow below as `.github/workflows/inskect.yml`, with your server's address and the
   folders that hold your skills.

```yaml
name: Inskect

on:
  pull_request:
  # Scanning the default branch too gives code scanning a baseline to compare pull requests with.
  push:
    branches: [main]

permissions:
  contents: read
  pull-requests: write    # the summary comment
  security-events: write  # the code scanning upload

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: inskect/inskect@v1.2.0
        with:
          server-url: https://inskect.example.com
          token: ${{ secrets.INSKECT_TOKEN }}
          paths: skills
```

The server needs Inskect v1.2.0 or later, with uploads on (they are by default). Pin the
action to a release tag, or to a commit SHA.

## Inputs

| Input | Default | What it does |
|---|---|---|
| `server-url` | (required) | Your server's address, as you open it in a browser. |
| `token` | none | A personal API token. Not needed on a server without accounts. |
| `paths` | `.` | Folders that hold skills, from the repository's root, one per line or comma-separated. A skill is a folder with a `SKILL.md`. |
| `fail-on` | `do-not-install` | The verdict that fails the check: `do-not-install` (*Rejected*), `caution` (*Review first* or worse), or `never`. |
| `max-risk-score` | none | Also fail when a skill's risk score (0–100) is above this. |
| `comment` | `true` | Comment on the pull request: `true` once it changes a skill, `always` also when it changes none (the comment says nothing was inspected), or `false`. |
| `sarif` | `true` | Upload the findings to code scanning. |
| `timeout-minutes` | `20` | How long to wait for all the inspections to finish. |
| `github-token` | `github.token` | The token used to list the changed files and comment. |

A skill that couldn't be inspected (a server error, a timeout, a zip over the server's upload limit)
always fails the check.

## Outputs

| Output | What it holds |
|---|---|
| `scanned` | How many skills were inspected. |
| `failed` | How many failed the check. |
| `results` | Each skill's result as JSON: `skill`, `recommendation`, `risk_score`, `issues`, `report_url`, `failure`, `error`. |
| `sarif-file` | The SARIF file written, with a run per skill. |

## How it works

- **Which skills.** On a pull request, the action lists its changed files (including a renamed
  file's old path) and maps each one to the nearest folder above it with a `SKILL.md`, within
  `paths`. On a push, it compares the push's commits. Any other event (`workflow_dispatch`,
  `schedule`), a branch's first push, or a change of more files than GitHub lists (3,000 for a pull
  request, 300 for a push) inspects every skill under `paths`.
- **What's inspected.** Each skill's folder, as checked out, is zipped and uploaded: the server inspects
  exactly the pull request's files, and private repositories work without giving the server access
  to them. The zip goes with the inspection request. The skills are inspected one at a time, and count towards the token owner's quotas and rate limits.
- **Code scanning.** Each skill gets its own SARIF run and category (`inskect/<folder>/`), with
  paths from the repository's root, so a skill's alerts are replaced only when that skill is inspected
  again. Code scanning is free on public repositories; private ones need GitHub Advanced Security.
  Set `sarif: false` without it.
- **Reports.** The comment links each skill's report on your server, which opens for the token's
  owner and admins. The comment itself carries the verdicts, so reviewers without an account still
  see them.

## Limitations

- A pull request from a fork gets no secrets, so the inspection can't authenticate and fails with a 401.
  Its `GITHUB_TOKEN` is also read-only, so the action can't comment or upload SARIF.
- The inspections are static: AI review isn't offered from the action yet.
- The action runs on Linux and macOS runners, with Node.js 20 or later on the `PATH` (GitHub's
  hosted runners have it).
