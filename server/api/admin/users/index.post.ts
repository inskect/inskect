import type { User, UserRole } from '~~/shared/types/auth'

export default defineEventHandler(async (event) => {
  const { email, password, role } = await readBody<{ email?: string, password?: string, role?: UserRole }>(event)

  return await backendFetch<User>(event, '/admin/users', {
    method: 'POST',
    body: { email, password, role: role ?? 'user' },
    fallbackMessage: 'Failed to add the user'
  })
})
