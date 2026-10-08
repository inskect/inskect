import type { H3Event } from 'h3'
import type { User } from '~~/shared/types/auth'

interface TokenResponse {
  token: string
  expires_at: number
  user: User
}

// Sign-up on a server that sends email: a link to finish was emailed, and there's no session yet.
interface PendingResponse {
  pending: true
}

/** Call an API endpoint that returns a new session, and keep the session in the cookie. */
export async function startSession(event: H3Event, path: string, body: Record<string, unknown>, fallbackMessage: string) {
  const response = await backendFetch<TokenResponse | PendingResponse>(event, path, {
    method: 'POST',
    body,
    fallbackMessage
  })
  if ('pending' in response) return { pending: true }
  setSessionToken(event, response.token, (response.expires_at - Date.now() / 1000) / 86400)
  return { user: response.user }
}

/** Sign in through one of the API's credential endpoints. */
export async function signIn(event: H3Event, path: '/auth/login' | '/auth/setup' | '/auth/signup', fallbackMessage: string) {
  const { email, password } = await readBody<{ email?: string, password?: string }>(event)
  if (!email || !password) {
    throw createError({ statusCode: 400, statusMessage: 'Enter your email and password' })
  }
  return await startSession(event, path, { email, password }, fallbackMessage)
}
