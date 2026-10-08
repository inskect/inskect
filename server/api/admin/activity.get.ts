import type { ActivityPage } from '~~/shared/types/backoffice'

export default defineEventHandler(async (event) => {
  const { limit, offset } = getQuery<{ limit?: string, offset?: string }>(event)
  return await backendFetch<ActivityPage>(event, '/admin/activity', {
    query: { limit, offset },
    fallbackMessage: 'Failed to load activity'
  })
})
