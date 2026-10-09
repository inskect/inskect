import type { Monitoring } from '../../../../shared/types/backoffice'

// The monitoring page's counts, alert rules and channels (backend/app/monitoring.py).
export default defineEventHandler(async (event) => {
  const { hours } = getQuery<{ hours?: string }>(event)
  return await backendFetch<Monitoring>(event, '/admin/monitoring', {
    query: { hours },
    fallbackMessage: 'Failed to load monitoring'
  })
})
