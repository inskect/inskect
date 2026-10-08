import type { DirectoryUser } from '~~/shared/types/backoffice'

export default defineEventHandler(async (event) => {
  const { query } = getQuery<{ query?: string }>(event)
  return await backendFetch<DirectoryUser[]>(event, '/admin/users', {
    query: query ? { query } : undefined,
    fallbackMessage: 'Failed to load users'
  })
})
