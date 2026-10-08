import type { MonitorEventPage } from '../../../../shared/types/backoffice'

// The events monitoring kept, newest first.
export default defineEventHandler(async (event) => {
  const { kind, limit, offset } = getQuery<{ kind?: string, limit?: string, offset?: string }>(event)
  return await backendFetch<MonitorEventPage>(event, '/admin/monitoring/events', {
    query: { kind, limit, offset },
    fallbackMessage: 'Failed to load monitoring events'
  })
})
