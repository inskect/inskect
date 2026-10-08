import type { Overview } from '~~/shared/types/backoffice'

export default defineEventHandler(async (event) => {
  return await backendFetch<Overview>(event, '/admin/overview', { fallbackMessage: 'Failed to load the overview' })
})
