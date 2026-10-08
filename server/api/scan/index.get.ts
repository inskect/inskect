import type { ScanHistoryResponse } from '~~/shared/types/scan'

export default defineEventHandler(async (event) => {
  // target: only that target's scans, its timeline. sort and order are checked by the API.
  const { limit, offset, target, sort, order } = getQuery<{ limit?: string, offset?: string, target?: string, sort?: string, order?: string }>(event)

  return await backendFetch<ScanHistoryResponse>(event, '/scan', {
    query: { limit, offset, target, sort, order },
    fallbackMessage: 'Failed to fetch scan history'
  })
})
