// State-changing /api requests from another site's page are refused (shared/utils/sameOrigin.ts).
export default defineEventHandler((event) => {
  const { trustProxy } = useRuntimeConfig(event)
  if (isCrossSiteRequest({
    method: event.method,
    path: event.path.split('?')[0]!,
    hasApiToken: !!getApiToken(event),
    secFetchSite: getRequestHeader(event, 'sec-fetch-site'),
    origin: getRequestHeader(event, 'origin'),
    host: getRequestHost(event, { xForwardedHost: trustProxy })
  })) {
    throw createError({ statusCode: 403, statusMessage: 'This request came from another site' })
  }
})
