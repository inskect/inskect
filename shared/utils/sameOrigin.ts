// Refusing state-changing requests that another site's page sends (CSRF), beyond what the session
// cookie's SameSite=Lax blocks: a sibling subdomain counts as the same site, and passes it.

export interface RequestFacts {
  method: string
  path: string
  // Scripts use API tokens, sent by them, never by a browser on its own.
  hasApiToken: boolean
  secFetchSite?: string
  origin?: string
  // This server's host, as the request reached it.
  host: string
}

const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS'])
// Changes nothing: browsers report what the Content-Security-Policy blocked, from any page.
const EXEMPT_PATHS = new Set(['/api/csp-report'])

/** Whether to refuse the request as coming from another site. */
export function isCrossSiteRequest({ method, path, hasApiToken, secFetchSite, origin, host }: RequestFacts): boolean {
  if (SAFE_METHODS.has(method.toUpperCase()) || !path.startsWith('/api/') || EXEMPT_PATHS.has(path) || hasApiToken) return false
  // Every current browser says where a request comes from. `none`: typed or bookmarked, by the user.
  if (secFetchSite) return secFetchSite !== 'same-origin' && secFetchSite !== 'none'
  // Older browsers send Origin with every POST. Its host is compared, not its scheme, which a
  // TLS-terminating proxy changes on the way.
  if (origin) {
    try {
      return new URL(origin).host !== host
    } catch {
      // `null` (a sandboxed frame, a redirect across sites) or garbage.
      return true
    }
  }
  // Neither: not a browser, e.g. a script with an API token.
  return false
}
