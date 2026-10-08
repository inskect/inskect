import type { AuthSession } from '~~/shared/types/auth'

// The public pages, for search engines (shared/utils/seo.ts). Only once the server knows its public
// address (NUXT_PUBLIC_SITE_URL); until then it's not found, and robots.txt doesn't point to it.
export default defineEventHandler(async (event) => {
  const siteUrl = configuredSiteUrl(event)
  if (!siteUrl) throw createError({ statusCode: 404, statusMessage: 'Not found' })
  const config = useRuntimeConfig(event)
  // As a signed-out visitor sees it, whoever asks: the sitemap is the same for everyone.
  const session = await $fetch<AuthSession>('/auth/session', { baseURL: config.apiBase, headers: apiHeaders() }).catch(() => null)
  setResponseHeaders(event, {
    'Content-Type': 'application/xml; charset=utf-8',
    'Cache-Control': 'public, max-age=3600, s-maxage=3600'
  })
  return sitemapXml({
    siteUrl,
    signupOpen: session?.auth === 'accounts' && session.signup_allowed
  })
})
