import type { ScanReport } from '~~/shared/types/scan'

export default defineEventHandler(async (event) => {
  const token = getRouterParam(event, 'token')
  const index = getRouterParam(event, 'index')
  if (!token || !index || !/^\d+$/.test(index)) {
    throw createError({ statusCode: 400, statusMessage: 'Missing link or skill' })
  }
  return await backendFetch<ScanReport>(event, `/shared/${encodeURIComponent(token)}/skills/${index}`, {
    fallbackMessage: 'Failed to fetch the skill’s report'
  })
})
