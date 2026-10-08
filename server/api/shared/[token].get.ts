import type { ScanStatus } from '~~/shared/types/scan'

// A shared result, for anyone with its link (backend/app/api/routes/shared.py).
export default defineEventHandler(async (event) => {
  const token = getRouterParam(event, 'token')
  if (!token) {
    throw createError({ statusCode: 400, statusMessage: 'Missing link' })
  }
  return await backendFetch<ScanStatus>(event, `/shared/${encodeURIComponent(token)}`, {
    fallbackMessage: 'Failed to fetch the shared result'
  })
})
