// A target's public status badge, as an SVG for READMEs: /badge?target=<the scanned link>. Only a
// shared result its owner put on the badge feeds it (backend/app/api/routes/badge.py); otherwise,
// or when the API can't be reached, it reads "unknown". Cached by browsers, GitHub's image proxy
// and any CDN in front, and it never starts a scan.
const MAX_AGE = 300
const ERROR_MAX_AGE = 60

export default defineEventHandler(async (event) => {
  const { target } = getQuery(event)
  let data: Partial<BadgeData> = {}
  let maxAge = MAX_AGE
  if (typeof target === 'string' && target.trim()) {
    data = await fetchBadge(target).catch(() => {
      maxAge = ERROR_MAX_AGE
      return {}
    })
  }
  setResponseHeaders(event, {
    'Content-Type': 'image/svg+xml; charset=utf-8',
    'Cache-Control': `public, max-age=${maxAge}, s-maxage=${maxAge}`,
    'Content-Security-Policy': 'default-src \'none\'; style-src \'unsafe-inline\'',
    'X-Content-Type-Options': 'nosniff'
  })
  return renderBadge(data)
})
