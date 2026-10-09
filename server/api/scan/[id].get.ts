import type { ScanStatus } from '../../../shared/types/scan'

export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'Missing scan id' })
  }

  return await backendFetch<ScanStatus>(event, `/scan/${encodeURIComponent(id)}`, {
    fallbackMessage: 'Failed to fetch scan status'
  })
})
