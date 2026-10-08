// Where a badge links to: the shared result it shows, or the home page when no scan is on it.
export default defineEventHandler(async (event) => {
  const { target } = getQuery(event)
  const data = typeof target === 'string' && target.trim() ? await fetchBadge(target).catch(() => null) : null
  setResponseHeader(event, 'Cache-Control', 'public, max-age=300, s-maxage=300')
  return sendRedirect(event, data?.share_token ? `/shared/${encodeURIComponent(data.share_token)}` : '/', 302)
})
