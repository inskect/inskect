import type { BaselineDownload } from '~~/shared/types/scan'

export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'Missing scan id' })
  }
  const { reason } = getQuery(event)

  return await backendFetch<BaselineDownload>(event, `/scan/${encodeURIComponent(id)}/baseline`, {
    query: typeof reason === 'string' && reason.trim() ? { reason } : undefined,
    fallbackMessage: 'Failed to fetch the baseline'
  })
})
