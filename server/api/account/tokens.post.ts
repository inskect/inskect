import type { CreatedApiToken } from '~~/shared/types/auth'

// A new API token: the only response that ever holds the token itself.
export default defineEventHandler(async (event) => {
  const { name, expiresInDays, password } = await readBody<{ name?: string, expiresInDays?: number | null, password?: string }>(event)
  return await backendFetch<CreatedApiToken>(event, '/account/tokens', {
    method: 'POST',
    // The account's password again (backend/app/api/routes/account.py).
    body: {
      name: typeof name === 'string' ? name : '',
      expires_in_days: typeof expiresInDays === 'number' ? expiresInDays : null,
      password: typeof password === 'string' ? password : ''
    },
    fallbackMessage: 'Failed to create the API token'
  })
})
