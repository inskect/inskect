#!/usr/bin/env node
// Interactive project setup: `pnpm setup`. Wires up backend/.env.local and,
// depending on the chosen mode, either `uv sync`s the backend or brings up
// docker compose.
import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import * as p from '@clack/prompts'

const rootDir = dirname(dirname(fileURLToPath(import.meta.url)))
const backendDir = join(rootDir, 'backend')
const envExamplePath = join(backendDir, '.env.example')
const envLocalPath = join(backendDir, '.env.local')

function commandExists(cmd) {
  return spawnSync(cmd, ['--version'], { stdio: 'ignore' }).error === undefined
}

function run(label, cmd, args, cwd) {
  const spinner = p.spinner()
  spinner.start(label)
  const result = spawnSync(cmd, args, { cwd, encoding: 'utf8' })
  if (result.status !== 0) {
    spinner.stop(`${label} — failed`, 1)
    p.log.error(result.stderr || result.stdout || `${cmd} exited with ${result.status}`)
    return false
  }
  spinner.stop(label)
  return true
}

function parseEnvExample(path) {
  return readFileSync(path, 'utf8')
    .split('\n')
    .filter(line => line.includes('='))
    .map((line) => {
      const index = line.indexOf('=')
      return [line.slice(0, index), line.slice(index + 1)]
    })
}

async function main() {
  console.clear()
  p.intro('inskect setup')

  const mode = await p.select({
    message: 'How do you want to run this locally?',
    options: [
      { value: 'docker', label: 'Docker Compose (recommended)', hint: 'one command, matches production' },
      { value: 'local', label: 'Local processes', hint: 'uv + pnpm dev, two terminals' }
    ]
  })
  if (p.isCancel(mode)) return p.cancel('Setup cancelled.')

  // --- backend/.env.local -------------------------------------------------
  let writeEnv = true
  if (existsSync(envLocalPath)) {
    const overwrite = await p.confirm({
      message: 'backend/.env.local already exists — overwrite it?',
      initialValue: false
    })
    if (p.isCancel(overwrite)) return p.cancel('Setup cancelled.')
    writeEnv = overwrite
  }

  if (writeEnv) {
    const defaults = Object.fromEntries(parseEnvExample(envExamplePath))

    const corsOrigins = await p.text({
      message: 'Origins allowed to call the API (CORS)',
      initialValue: defaults.INSKECT_CORS_ORIGINS || '["http://localhost:3000"]'
    })
    if (p.isCancel(corsOrigins)) return p.cancel('Setup cancelled.')

    const maxConcurrentScans = await p.text({
      message: 'Max concurrent scans',
      initialValue: defaults.INSKECT_MAX_CONCURRENT_SCANS || '2',
      validate: value => (/^\d+$/.test(value) ? undefined : 'Enter a whole number')
    })
    if (p.isCancel(maxConcurrentScans)) return p.cancel('Setup cancelled.')

    const auth = await p.select({
      message: 'Who can use this server?',
      options: [
        {
          value: 'none',
          label: 'Anyone who can reach it — no sign-in',
          hint: 'including the admin page and Claude login; only for a private network or behind a proxy login'
        },
        {
          value: 'accounts',
          label: 'Only people with an account',
          hint: 'the first visitor creates the admin account; scans are private to their user'
        }
      ],
      initialValue: 'none'
    })
    if (p.isCancel(auth)) return p.cancel('Setup cancelled.')

    const envContents = [
      `INSKECT_CORS_ORIGINS=${corsOrigins}`,
      `INSKECT_MAX_CONCURRENT_SCANS=${maxConcurrentScans}`,
      `INSKECT_AUTH=${auth}`,
      ''
    ].join('\n')
    writeFileSync(envLocalPath, envContents)
    p.log.success('Wrote backend/.env.local')

    if (auth === 'none') {
      p.log.warn('No sign-in: anyone who can reach this server can use every page, including /admin.')
    } else {
      p.note('Open the app and create the admin account: the first account becomes the admin.', 'Accounts')
    }
  } else {
    p.log.info('Keeping existing backend/.env.local')
  }

  // --- mode-specific steps -------------------------------------------------
  if (mode === 'docker') {
    if (!commandExists('docker')) {
      p.log.error('docker was not found on PATH — install Docker, then run `docker compose up -d`.')
    } else {
      const bringUp = await p.confirm({
        message: 'Run `docker compose up -d` now?',
        initialValue: true
      })
      if (!p.isCancel(bringUp) && bringUp) {
        // The published images, or built from this checkout when there are none to pull.
        run('Starting containers', 'docker', ['compose', 'up', '-d'], rootDir)
      }
    }
    p.outro([
      'Frontend: http://localhost:3005',
      'Optional Claude CLI provider login: docker exec -it inskect-api claude auth login'
    ].join('\n'))
    return
  }

  // mode === 'local'
  if (!commandExists('uv')) {
    p.log.error('uv was not found on PATH — install it (https://docs.astral.sh/uv/) and re-run `pnpm setup`.')
  } else {
    run('Installing backend dependencies (uv sync)', 'uv', ['sync'], backendDir)
  }

  p.outro([
    'Start the backend:  cd backend && uv run uvicorn app.main:app --reload',
    'Start the frontend: NUXT_API_BASE=http://localhost:8000 pnpm dev',
    'Then open http://localhost:3000'
  ].join('\n'))
}

main()
