import type { AuthSession } from '~~/shared/types/auth'

export default defineEventHandler(async (event) => {
  return await backendFetch<AuthSession>(event, '/auth/session', { fallbackMessage: 'Failed to check your session' })
})
