import type { ScanLogsResponse } from '~~/shared/types/scan'

export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'Missing scan id' })
  }

  // after: only the lines logged since that cursor.
  const { after } = getQuery<{ after?: string }>(event)

  return await backendFetch<ScanLogsResponse>(event, `/scan/${encodeURIComponent(id)}/logs`, {
    query: { after },
    fallbackMessage: 'Failed to fetch scan logs'
  })
})
