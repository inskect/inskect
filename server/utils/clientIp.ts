import type { H3Event } from 'h3'

// With NUXT_TRUST_PROXY=true, trust only the right-most X-Forwarded-For entry: the one the
// reverse proxy in front of us appended. Anything to its left was supplied by the client.
// Without a proxy, X-Forwarded-For is entirely client-controlled, so use the socket address.
export function getClientIp(event: H3Event): string {
  const { trustProxy } = useRuntimeConfig(event)
  if (trustProxy) {
    const proxied = getRequestHeader(event, 'x-forwarded-for')
      ?.split(',')
      .map(part => part.trim())
      .filter(Boolean)
      .at(-1)
    if (proxied) return proxied
  }
  return getRequestIP(event) ?? 'unknown'
}

let warned = false

/**
 * Whether the request came through a proxy we don't trust: it carries X-Forwarded-For, but
 * NUXT_TRUST_PROXY is off, so every visitor seems to come from the proxy and shares its rate
 * limits. Logged once here; the API shows it in the backoffice.
 */
export function behindUntrustedProxy(event: H3Event): boolean {
  if (useRuntimeConfig(event).trustProxy || !getRequestHeader(event, 'x-forwarded-for')) return false
  if (!warned) {
    warned = true
    console.warn('Requests arrive with X-Forwarded-For, but NUXT_TRUST_PROXY is off: behind a reverse proxy, every visitor shares the proxy\'s rate limits. Set NUXT_TRUST_PROXY=true (docs/REVERSE_PROXY.md).')
  }
  return true
}
