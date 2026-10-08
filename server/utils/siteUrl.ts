import type { H3Event } from 'h3'

// This server's public address when it's configured (NUXT_PUBLIC_SITE_URL), without a trailing
// slash; null otherwise. Unlike app/composables/useSiteUrl.ts, never guessed from the request: the
// sitemap and robots.txt must not advertise whatever Host a client sent.
export function configuredSiteUrl(event: H3Event): string | null {
  return useRuntimeConfig(event).public.siteUrl.replace(/\/+$/, '') || null
}
