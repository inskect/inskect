import type { UserDetail } from '~~/shared/types/backoffice'

export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'Missing user id' })
  }
  return await backendFetch<UserDetail>(event, `/admin/users/${encodeURIComponent(id)}`, {
    fallbackMessage: 'Failed to load the user'
  })
})
