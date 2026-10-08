// Everything but the public pages says noindex in its headers too (shared/utils/seo.ts), for
// crawlers that read X-Robots-Tag before, or instead of, the page's own robots meta tag.
export default defineEventHandler((event) => {
  if (!isIndexable(event.path.split('?')[0]!)) setResponseHeader(event, 'X-Robots-Tag', NOINDEX)
})
