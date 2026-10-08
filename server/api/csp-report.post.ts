// What the Content-Security-Policy blocked, as browsers report it: one structured log line each,
// for the logs (docs/MONITORING.md). On preview deployments the policy is only reported, so this
// shows what enforcing it would break. Reports come from anyone: only their directive, the blocked
// resource's origin and the page's path are logged.
const MAX_BYTES = 16 * 1024

export default defineEventHandler(async (event) => {
  const raw = await readRawBody(event)
  if (raw && raw.length <= MAX_BYTES) {
    let body: unknown
    try {
      body = JSON.parse(raw)
    } catch {
      body = null
    }
    for (const violation of cspViolations(body).slice(0, 10)) {
      console.warn(JSON.stringify({ event: 'inskect.csp_violation', at: Date.now() / 1000, ...violation }))
    }
  }
  setResponseStatus(event, 204)
  return null
})
