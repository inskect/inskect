// What a page view, an event or a measurement may say, for an analytics plugin a build adds
// (useAnalytics). Only a route's pattern should leave the browser, never its path: a path can hold a
// share link's token (/shared/<token>) or a scan's id, and a query string a scanned link (/?target=…).

/** A route's pattern: /scan/:id() → /scan/[id], /:path(.*)* → /[...path]. */
export function routePattern(matchedPath: string | undefined): string {
  if (!matchedPath) return '/[not-found]'
  return matchedPath
    .replace(/:(\w+)\(\.\*\)\*/g, '[...$1]')
    .replace(/:(\w+)(\(\))?\??/g, '[$1]')
}

/** The URL to report: this site's origin and the route's pattern, without query or hash. */
export function anonymousUrl(url: string, patternOf: (path: string) => string): string {
  try {
    const parsed = new URL(url)
    return `${parsed.origin}${patternOf(parsed.pathname)}`
  } catch {
    return '/'
  }
}

// The events tracked, with what each may carry: never a target, an email or an id.
export interface AnalyticsEvents {
  'Sign Up': undefined
  'Scan Started': { source: 'link' | 'github' | 'upload' | 'mcp', ai_review: boolean }
  'Scan Viewed': { status: 'done' | 'error', verdict: string | null }
}
