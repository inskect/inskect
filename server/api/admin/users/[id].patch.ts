import type { User, UserRole, UserStatus } from '../../../../shared/types/auth'

export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'Missing user id' })
  }
  const { role, status } = await readBody<{ role?: UserRole, status?: UserStatus }>(event)
  return await backendFetch<User>(event, `/admin/users/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: { role, status },
    fallbackMessage: 'Failed to update the user'
  })
})
