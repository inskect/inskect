// The GitHub Action (../action.yml): scans the skills a pull request or push changes on a
// Inskect server, comments on the pull request, and writes the findings as SARIF. Node's
// own modules only, so the action installs nothing.
import { randomUUID } from 'node:crypto'
import { appendFileSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import {
  COMMENT_MARKER, allSkills, changedSkills, failureReason, issueCount, logLine, mergeSarif, parseComment,
  parseRoots, parseThreshold, renderSummary, repositorySarif, riskOf, workflowCommand
} from './lib.mjs'
import { zipDirectory } from './zip.mjs'

const POLL_SECONDS = 5
// GitHub's lists of a pull request's or a comparison's files stop here: past it, scan every skill.
const PULL_FILES_LIMIT = 3000
const COMPARE_FILES_LIMIT = 300

const env = process.env

function input(name, fallback = '') {
  const value = env[`INPUT_${name.toUpperCase().replaceAll('-', '_')}`]
  return value === undefined || value.trim() === '' ? fallback : value.trim()
}

function setOutput(name, value) {
  if (!env.GITHUB_OUTPUT) return
  // A delimiter the value can't hold, as @actions/core does: a line of it would end the value early.
  const delimiter = `ghadelimiter_${randomUUID()}`
  if (String(value).includes(delimiter)) throw new Error(`The ${name} output can't be written`)
  appendFileSync(env.GITHUB_OUTPUT, `${name}<<${delimiter}\n${value}\n${delimiter}\n`)
}

const sleep = seconds => new Promise(resolve => setTimeout(resolve, seconds * 1000))

function message(body, fallback) {
  // FastAPI's `detail`, or a Nitro error's `message`.
  const detail = body?.detail ?? body?.message ?? body?.statusMessage
  if (typeof detail === 'string' && detail) return detail
  if (Array.isArray(detail) && typeof detail[0]?.msg === 'string') return detail[0].msg
  return fallback
}

class InskectServer {
  constructor(serverUrl, token) {
    this.server = serverUrl.replace(/\/+$/, '')
    this.token = token
  }

  get headers() {
    return this.token ? { Authorization: `Bearer ${this.token}` } : {}
  }

  async request(path, { method = 'GET', body, json } = {}) {
    for (let attempt = 1; ; attempt++) {
      const response = await fetch(`${this.server}/api${path}`, {
        method,
        headers: { ...this.headers, ...(json === undefined ? {} : { 'Content-Type': 'application/json' }) },
        body: json === undefined ? body : JSON.stringify(json)
      })
      // Rate limited: the server says when to try again.
      if (response.status === 429 && attempt < 5) {
        const wait = Math.min(Number(response.headers.get('retry-after')) || 30, 120)
        console.log(logLine(`Rate limited by the server: retrying in ${wait}s`))
        await sleep(wait)
        continue
      }
      const text = await response.text()
      let parsed
      try {
        parsed = text ? JSON.parse(text) : null
      } catch {
        parsed = null
      }
      if (!response.ok) {
        let reason = message(parsed, `${response.status} ${response.statusText}`)
        if (response.status === 401 && !this.token) {
          reason += ' — no API token was given (a pull request from a fork gets no secrets)'
        }
        throw new Error(`${method} ${path}: ${reason}`)
      }
      return parsed
    }
  }

  async uploadAndScan(name, zip, health) {
    if (!health.upload_store) throw new Error('This server doesn’t take uploads, so it can’t inspect a repository’s skills')
    const form = new FormData()
    form.append('file', new Blob([zip], { type: 'application/zip' }), name)
    form.append('options', '{}')
    return await this.request('/scan/upload', { method: 'POST', body: form })
  }

  async waitFor(id, deadline) {
    for (;;) {
      const scan = await this.request(`/scan/${encodeURIComponent(id)}`)
      if (scan.status === 'done' || scan.status === 'error') return scan
      if (Date.now() > deadline) throw new Error(`the inspection didn’t finish in time (still ${scan.status})`)
      await sleep(POLL_SECONDS)
    }
  }
}

class GitHub {
  constructor(token) {
    this.token = token
    this.api = env.GITHUB_API_URL || 'https://api.github.com'
    this.repo = env.GITHUB_REPOSITORY
  }

  async request(path, { method = 'GET', json } = {}) {
    const response = await fetch(`${this.api}${path}`, {
      method,
      headers: {
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
        ...(json === undefined ? {} : { 'Content-Type': 'application/json' })
      },
      body: json === undefined ? undefined : JSON.stringify(json)
    })
    if (!response.ok) throw new Error(`GitHub ${method} ${path}: ${response.status} ${message(await response.json().catch(() => null), response.statusText)}`)
    return await response.json()
  }

  async list(path, pick = page => page) {
    const items = []
    for (let page = 1; ; page++) {
      const batch = pick(await this.request(`${path}${path.includes('?') ? '&' : '?'}per_page=100&page=${page}`))
      items.push(...batch)
      if (batch.length < 100) return items
    }
  }
}

// The files this run's event changed, or null when every skill should be scanned.
async function changedFiles(github, event, eventName) {
  const names = files => files.flatMap(file => [file.filename, file.previous_filename].filter(Boolean))
  if (event.pull_request) {
    const files = await github.list(`/repos/${github.repo}/pulls/${event.pull_request.number}/files`)
    return files.length >= PULL_FILES_LIMIT ? null : names(files)
  }
  if (eventName === 'push' && event.before && !/^0+$/.test(event.before) && event.after) {
    const { files = [] } = await github.request(`/repos/${github.repo}/compare/${event.before}...${event.after}`)
    return files.length >= COMPARE_FILES_LIMIT ? null : names(files)
  }
  return null
}

async function upsertComment(github, number, body, { create }) {
  const comments = await github.list(`/repos/${github.repo}/issues/${number}/comments`)
  const existing = comments.find(comment => comment.body?.includes(COMMENT_MARKER))
  if (existing) {
    await github.request(`/repos/${github.repo}/issues/comments/${existing.id}`, { method: 'PATCH', json: { body } })
  } else if (create) {
    await github.request(`/repos/${github.repo}/issues/${number}/comments`, { method: 'POST', json: { body } })
  }
}

function uploadName(skill) {
  const repo = (env.GITHUB_REPOSITORY || 'repository').split('/').pop()
  const name = skill === '.' ? repo : `${repo}-${skill.replaceAll('/', '-')}`
  return `${name.replace(/[^\w.\- ()]+/g, '_').slice(0, 96)}.zip`
}

async function scanSkill(server, health, workspace, skill, deadline) {
  const outcome = { skill }
  try {
    const zip = zipDirectory(join(workspace, skill))
    if (zip.length > health.max_upload_bytes) {
      throw new Error(`its zip is ${(zip.length / 1048576).toFixed(1)} MB, over the server’s ${Math.floor(health.max_upload_bytes / 1048576)} MB`)
    }
    const { id } = await server.uploadAndScan(uploadName(skill), zip, health)
    outcome.reportUrl = `${server.server}/scan/${encodeURIComponent(id)}`
    console.log(logLine(`Scanning ${skill}: ${outcome.reportUrl}`))
    const scan = await server.waitFor(id, deadline)
    if (scan.status === 'error') throw new Error(scan.error || 'the inspection failed')
    outcome.risk = riskOf(scan.result)
    outcome.issues = issueCount(scan.result)
    outcome.sarif = await server.request(`/scan/${encodeURIComponent(id)}/export?format=sarif`)
  } catch (error) {
    outcome.error = error instanceof Error ? error.message : String(error)
  }
  return outcome
}

async function main() {
  const serverUrl = input('server-url')
  if (!serverUrl) throw new Error('server-url is required: the address of your Inskect server')
  const roots = parseRoots(input('paths', '.'))
  const threshold = parseThreshold(input('fail-on', 'do-not-install'), input('max-risk-score'))
  const comment = parseComment(input('comment', 'true'))
  const sarif = input('sarif', 'true') === 'true'
  const timeoutMinutes = Number(input('timeout-minutes', '20')) || 20
  const workspace = env.GITHUB_WORKSPACE || process.cwd()
  const eventName = env.GITHUB_EVENT_NAME || ''
  const event = env.GITHUB_EVENT_PATH ? JSON.parse(readFileSync(env.GITHUB_EVENT_PATH, 'utf8')) : {}

  const github = new GitHub(input('github-token'))
  const files = await changedFiles(github, event, eventName)
  const skills = files === null ? allSkills(roots, workspace) : changedSkills(files, roots, workspace)
  console.log(logLine(files === null
    ? `Scanning every skill under ${roots.join(', ')}: ${skills.length} found`
    : `${files.length} changed file${files.length === 1 ? '' : 's'}, in ${skills.length} skill${skills.length === 1 ? '' : 's'}`))

  const server = new InskectServer(serverUrl, input('token'))
  const outcomes = []
  if (skills.length) {
    const health = await server.request('/health')
    const deadline = Date.now() + timeoutMinutes * 60_000
    // One at a time: the server's rate limits and queue are per user.
    for (const skill of skills) {
      const outcome = await scanSkill(server, health, workspace, skill, deadline)
      outcome.failure = failureReason(outcome, threshold)
      if (outcome.error) console.log(workflowCommand('error', `${skill} couldn’t be inspected: ${outcome.error}`, { title: 'Inskect' }))
      else if (outcome.failure) console.log(workflowCommand('error', `${skill} fails the check: ${outcome.failure}`, { title: 'Inskect' }))
      else console.log(logLine(`${skill}: ${outcome.risk.recommendation}, risk score ${outcome.risk.score}`))
      outcomes.push(outcome)
    }
  }

  const summary = renderSummary(outcomes, { threshold })
  if (env.GITHUB_STEP_SUMMARY) appendFileSync(env.GITHUB_STEP_SUMMARY, `${summary}\n`)
  if (comment !== 'false' && event.pull_request) {
    try {
      // A pull request that touches no skill gets no comment, unless an earlier push left one or
      // comment is `always`.
      await upsertComment(github, event.pull_request.number, summary, { create: outcomes.length > 0 || comment === 'always' })
    } catch (error) {
      console.log(workflowCommand('warning', `Couldn’t comment on the pull request (it needs pull-requests: write): ${error.message}`, { title: 'Inskect' }))
    }
  }

  const logs = outcomes.filter(outcome => outcome.sarif).map(outcome => repositorySarif(outcome.sarif, outcome.skill))
  if (sarif && logs.length) {
    const folder = join(env.RUNNER_TEMP || workspace, 'inskect-sarif')
    mkdirSync(folder, { recursive: true })
    const file = join(folder, 'inskect.sarif')
    writeFileSync(file, JSON.stringify(mergeSarif(logs), null, 2))
    setOutput('sarif-file', file)
  }

  const failed = outcomes.filter(outcome => outcome.failure)
  setOutput('scanned', String(outcomes.length))
  setOutput('failed', String(failed.length))
  setOutput('results', JSON.stringify(outcomes.map(({ skill, risk, issues, reportUrl, failure, error }) => ({
    skill,
    recommendation: risk?.recommendation ?? null,
    risk_score: risk?.score ?? null,
    issues: issues ?? null,
    report_url: reportUrl ?? null,
    failure: failure ?? null,
    error: error ?? null
  }))))
  if (failed.length) process.exitCode = 1
}

main().catch((error) => {
  console.log(workflowCommand('error', error instanceof Error ? error.message : String(error), { title: 'Inskect' }))
  process.exitCode = 1
})
