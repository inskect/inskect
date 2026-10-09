import type { ScanReport } from '../../../../../shared/types/scan'

export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const index = getRouterParam(event, 'index')
  if (!id || !index || !/^\d+$/.test(index)) {
    throw createError({ statusCode: 400, statusMessage: 'Missing scan id or skill' })
  }

  return await backendFetch<ScanReport>(event, `/scan/${encodeURIComponent(id)}/skills/${index}`, {
    fallbackMessage: 'Failed to fetch the skill’s report'
  })
})
