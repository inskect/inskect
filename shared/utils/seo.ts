// What search engines may index (app/app.vue, server/middleware/robots.ts, server/routes/robots.txt.ts,
// server/routes/sitemap.xml.ts): the public pages, and nothing else. Signed-in pages, sign-in, password
// resets, shared results and unknown paths all say noindex.

const INDEXABLE_PATHS = new Set(['/', '/signup'])

export function isIndexable(path: string): boolean {
  return INDEXABLE_PATHS.has(path === '/' ? path : path.replace(/\/+$/, ''))
}

// Kept out of crawlers' way in robots.txt; noindex covers the rest.
export const ROBOTS_DISALLOW = ['/admin', '/account', '/history', '/scan/', '/api/']

export const NOINDEX = 'noindex, nofollow'

export interface SitemapInput {
  siteUrl: string
  // Whether visitors can create an account here, so /signup is worth listing.
  signupOpen: boolean
}

export function sitemapPaths({ signupOpen }: Omit<SitemapInput, 'siteUrl'>): string[] {
  return ['/', ...(signupOpen ? ['/signup'] : [])]
}

function escapeXml(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&apos;')
}

export function sitemapXml(input: SitemapInput): string {
  const urls = sitemapPaths(input).map(path => `  <url><loc>${escapeXml(`${input.siteUrl}${path}`)}</loc></url>`)
  return ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">', ...urls, '</urlset>', ''].join('\n')
}

// The sitemap is advertised only once the server knows its public address (NUXT_PUBLIC_SITE_URL):
// a self-hosted install doesn't invite crawlers by default.
export function robotsTxt(siteUrl: string | null): string {
  return [
    'User-agent: *',
    ...ROBOTS_DISALLOW.map(path => `Disallow: ${path}`),
    ...(siteUrl ? ['', `Sitemap: ${siteUrl}/sitemap.xml`] : []),
    ''
  ].join('\n')
}
