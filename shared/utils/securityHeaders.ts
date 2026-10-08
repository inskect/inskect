// The security headers every response carries (server/middleware/security-headers.ts), and the
// Content-Security-Policy's nonce on the scripts Nuxt writes into each page
// (server/plugins/csp-nonce.ts). docs/SECURITY_MODEL.md describes them.

// Where the browser reports what the policy blocked (server/api/csp-report.post.ts).
export const CSP_REPORT_PATH = '/api/csp-report'

export interface PolicyOptions {
  // This response's nonce: the page's inline scripts carry it.
  nonce: string
  // Origins the browser may also send requests to, besides this server's (NUXT_CSP_CONNECT_SRC).
  connectSources?: string[]
}

/**
 * Scripts only from this server, or inline with this response's nonce: Nuxt writes three into each
 * page (its config, the import map, and the color mode's), and nothing else may run, whatever a
 * scanned skill's text manages to put in a page. Styles may be inline, which Vue's style bindings
 * need. Nothing may frame a page.
 */
export function contentSecurityPolicy({ nonce, connectSources = [] }: PolicyOptions): string {
  const connect = ['\'self\'', ...connectSources]
  return [
    'default-src \'self\'',
    `script-src 'self' 'nonce-${nonce}'`,
    'style-src \'self\' \'unsafe-inline\'',
    'img-src \'self\' data:',
    'font-src \'self\' data:',
    `connect-src ${connect.join(' ')}`,
    'object-src \'none\'',
    'base-uri \'none\'',
    'form-action \'self\'',
    'frame-ancestors \'none\'',
    `report-uri ${CSP_REPORT_PATH}`,
    'report-to csp'
  ].join('; ')
}

export interface HeaderOptions extends PolicyOptions {
  path: string
  https: boolean
  // The policy reported, not enforced: on preview deployments, before it's enforced.
  reportOnly: boolean
}

export function securityHeaders({ path, https, reportOnly, ...policy }: HeaderOptions): Record<string, string> {
  return {
    [reportOnly ? 'Content-Security-Policy-Report-Only' : 'Content-Security-Policy']: contentSecurityPolicy(policy),
    'Reporting-Endpoints': `csp="${CSP_REPORT_PATH}"`,
    // For browsers that don't read frame-ancestors.
    'X-Frame-Options': 'DENY',
    'X-Content-Type-Options': 'nosniff',
    // A shared result's URL is its secret: other sites never see one, and a shared page sends none.
    'Referrer-Policy': path.startsWith('/shared/') ? 'no-referrer' : 'same-origin',
    'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()',
    // Only over HTTPS, where it means something. No includeSubDomains: other sites under the same
    // domain aren't this server's to decide for.
    ...(https ? { 'Strict-Transport-Security': 'max-age=31536000' } : {})
  }
}

/** The page's HTML, its script tags carrying the nonce. */
export function addNonce(html: string, nonce: string): string {
  return html.replace(/<script(?=[\s>])/g, `<script nonce="${nonce}"`)
}

export interface CspViolation {
  directive: string
  // Where the blocked resource came from: its origin only, or `inline`, `eval`…
  blocked: string
  page: string
}

/** What a browser's violation report says, in either format: `report-uri`'s or the Reporting API's. */
export function cspViolations(body: unknown): CspViolation[] {
  const reports = Array.isArray(body) ? body.map(report => report?.body) : [(body as { 'csp-report'?: unknown })?.['csp-report']]
  return reports.filter((report): report is Record<string, unknown> => !!report && typeof report === 'object').map((report) => {
    const value = (key: string, other: string) => String(report[key] ?? report[other] ?? '')
    return {
      directive: value('effectiveDirective', 'effective-directive') || value('violatedDirective', 'violated-directive'),
      blocked: originOf(value('blockedURL', 'blocked-uri')),
      page: pathOf(value('documentURL', 'document-uri'))
    }
  })
}

// Reports come from anyone: keep only where things came from, never a path, which can be a secret
// (a shared result's token).
function originOf(url: string): string {
  try {
    return new URL(url).origin
  } catch {
    return url.slice(0, 40)
  }
}

function pathOf(url: string): string {
  try {
    const { pathname } = new URL(url)
    return pathname.startsWith('/shared/') ? '/shared/…' : pathname
  } catch {
    return ''
  }
}
