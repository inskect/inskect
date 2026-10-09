import type { ApiToken } from '../../../../../shared/types/auth'

export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'Missing user id' })
  }
  return await backendFetch<ApiToken[]>(event, `/admin/users/${encodeURIComponent(id)}/tokens`, { fallbackMessage: 'Failed to fetch the user’s API tokens' })
})
