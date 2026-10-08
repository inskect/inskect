import { randomBytes } from 'node:crypto'

// Every response's security headers (shared/utils/securityHeaders.ts), with a nonce of its own for
// the page's scripts (server/plugins/csp-nonce.ts). A route may send a stricter policy of its own,
// as the badge does. Not in development: Vite's dev server runs inline and evaluated scripts.
export default defineEventHandler((event) => {
  if (import.meta.dev) return
  const nonce = randomBytes(16).toString('base64')
  event.context.cspNonce = nonce
  const { trustProxy, cspReportOnly, cspConnectSrc } = useRuntimeConfig(event)
  setResponseHeaders(event, securityHeaders({
    nonce,
    connectSources: cspConnectSrc,
    path: event.path.split('?')[0]!,
    https: getRequestProtocol(event, { xForwardedProto: trustProxy }) === 'https',
    reportOnly: cspReportOnly
  }))
})
