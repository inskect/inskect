#!/usr/bin/env node
// The README's screenshots (docs/assets/screenshot-*.png): the home page, a scan result, the Account
// page and the backoffice, in the light and dark themes, all at the same size.
//
//   BASE_URL=http://localhost:3000 node scripts/screenshots.mjs
//
// Point it at a server of its own, with accounts on, sign-up open and an empty database: it creates
// an admin and a user, and the user scans the examples below, so the pictures show realistic results
// and no real user. The backoffice is the admin's; the rest is the user's, whose Account page shows
// their usage when quotas are set (INSKECT_DAILY_SCAN_QUOTA) and the Claude key when
// INSKECT_SECRET_KEY is. Run a production build (`nuxt build`): the dev server adds its own
// overlay. Needs Playwright's Chromium (`npx playwright install
// chromium`), or run it in the mcr.microsoft.com/playwright image of the same version.
import { mkdir } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const BASE_URL = (process.env.BASE_URL || 'http://localhost:3000').replace(/\/+$/, '')
const PASSWORD = process.env.SCREENSHOT_PASSWORD || 'screenshots-only-password'
const ADMIN = { email: 'admin@example.com', password: PASSWORD }
const USER = { email: 'alex@example.com', password: PASSWORD }
const OUT_DIR = join(dirname(dirname(fileURLToPath(import.meta.url))), 'docs', 'assets')

// Inspected in this order, so the report shown ends up on top of the recent inspections.
const FIXTURES = 'https://github.com/NVIDIA/skillspector/blob/main/tests/fixtures'
// The report shown is one whose names are plain: mcp_poisoned_tool's, by design, carries a lookalike
// letter, and its warning mark would draw the eye in a picture meant to show the page.
const RESULT_TARGET = `${FIXTURES}/malicious_skill/SKILL.md`
const TARGETS = [
  'https://github.com/anthropics/skills/blob/main/skills/pdf/SKILL.md',
  `${FIXTURES}/pe3_bare_keyring/SKILL.md`,
  `${FIXTURES}/mcp_poisoned_tool/SKILL.md`,
  RESULT_TARGET
]

// CSS pixels, at twice the density: what the README shows at 860 wide stays sharp.
const VIEWPORT = { width: 960, height: 800 }
const SCAN_TIMEOUT_MS = 10 * 60 * 1000

async function post(request, path, data) {
  const response = await request.post(path, { data })
  if (!response.ok()) throw new Error(`${path} failed: ${response.status()} ${await response.text()}`)
  return response
}

// A signed-in browser context for account, creating the account when it doesn't exist yet.
async function signIn(browser, account) {
  const context = await browser.newContext({ baseURL: BASE_URL })
  const session = await (await context.request.get('/api/auth/session')).json()
  if (session.auth !== 'accounts') throw new Error('Turn accounts on (INSKECT_AUTH=accounts): the screenshots show them.')
  if (session.needs_setup) {
    if (account !== ADMIN) throw new Error('Create the admin first')
    await post(context.request, '/api/auth/setup', account)
  } else {
    const login = await context.request.post('/api/auth/login', { data: account })
    if (!login.ok()) await post(context.request, '/api/auth/signup', account)
  }
  return context
}

// The API stores a GitHub file link as its raw.githubusercontent.com URL.
function storedTarget(target) {
  return target.replace(/^https:\/\/github\.com\/([^/]+)\/([^/]+)\/blob\//, 'https://raw.githubusercontent.com/$1/$2/')
}

async function waitForScan(request, id) {
  const deadline = Date.now() + SCAN_TIMEOUT_MS
  while (Date.now() < deadline) {
    const scan = await (await request.get(`/api/scan/${id}`)).json()
    if (scan.status === 'done') return
    if (scan.status === 'error') throw new Error(`The scan of ${scan.target} failed: ${scan.error}`)
    await new Promise(resolve => setTimeout(resolve, 3000))
  }
  throw new Error(`Scan ${id} didn't finish in time`)
}

// The result to show: the latest finished scan of RESULT_TARGET, after scanning whatever's missing.
async function seedScans(request) {
  const { items } = await (await request.get('/api/scan', { params: { limit: '100' } })).json()
  const done = new Map(items.filter(scan => scan.status === 'done').map(scan => [scan.target, scan.id]))
  for (const target of TARGETS) {
    if (done.has(storedTarget(target))) continue
    console.log(`scanning ${target}`)
    const response = await request.post('/api/scan', { data: { target } })
    if (!response.ok()) throw new Error(`Couldn't scan ${target}: ${response.status()} ${await response.text()}`)
    const { id } = await response.json()
    await waitForScan(request, id)
    done.set(storedTarget(target), id)
  }
  return done.get(storedTarget(RESULT_TARGET))
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true })
  // Headless Chromium's font hinting widens some letters' spacing (a gap after every "t").
  const browser = await chromium.launch({ args: ['--font-render-hinting=none'] })
  try {
    const admin = await signIn(browser, ADMIN)
    const user = await signIn(browser, USER)
    const resultId = await seedScans(user.request)
    const sessions = { admin: await admin.storageState(), user: await user.storageState() }
    await admin.close()
    await user.close()

    const pages = [
      { name: 'home', path: '/', as: 'user' },
      { name: 'result', path: `/scan/${resultId}`, as: 'user' },
      { name: 'account', path: '/account', as: 'user' },
      { name: 'admin', path: '/admin', as: 'admin' }
    ]
    for (const theme of ['light', 'dark']) {
      for (const { name, path, as } of pages) {
        // The site follows the system theme until a visitor picks one.
        const context = await browser.newContext({
          baseURL: BASE_URL,
          storageState: sessions[as],
          viewport: VIEWPORT,
          deviceScaleFactor: 2,
          colorScheme: theme,
          reducedMotion: 'reduce'
        })
        const page = await context.newPage()
        await page.goto(path, { waitUntil: 'networkidle' })
        // Web fonts, then a frame for anything they reflow.
        await page.evaluate(() => document.fonts.ready)
        await page.waitForTimeout(300)
        const file = join(OUT_DIR, `screenshot-${name}-${theme}.png`)
        await page.screenshot({ path: file, animations: 'disabled', caret: 'hide' })
        console.log(`wrote ${file}`)
        await context.close()
      }
    }
  } finally {
    await browser.close()
  }
}

main().catch((error) => {
  console.error(error.message ?? error)
  process.exit(1)
})
