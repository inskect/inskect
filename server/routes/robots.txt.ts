// robots.txt, for everyone (shared/utils/seo.ts): served here, outside the pages, so the sign-in
// guard never redirects it.
export default defineEventHandler((event) => {
  setResponseHeaders(event, {
    'Content-Type': 'text/plain; charset=utf-8',
    'Cache-Control': 'public, max-age=3600, s-maxage=3600'
  })
  return robotsTxt(configuredSiteUrl(event))
})
