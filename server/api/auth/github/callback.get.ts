import type { User } from '~~/shared/types/auth'

interface CallbackResponse {
  outcome: 'signed_in' | 'signed_up' | 'linked'
  token: string | null
  expires_at: number | null
  user: User | null
}

// GitHub's redirect back: the API checks the state against this browser's nonce, then signs in
// (a session, as a password sign-in gets), signs up, or links GitHub to the signed-in account.
export default defineEventHandler(async (event) => {
  const { code, state, error } = getQuery<{ code?: string, state?: string, error?: string }>(event)
  const nonce = takeGitHubNonce(event)
  if (error || !code || !state) {
    return gitHubFailure(event, error === 'access_denied' ? 'Signing in with GitHub was cancelled' : 'GitHub didn’t finish the sign-in: try again')
  }
  let result: CallbackResponse
  try {
    result = await backendFetch<CallbackResponse>(event, '/auth/github/callback', {
      method: 'POST',
      body: { code, state, nonce: nonce ?? '' },
      fallbackMessage: 'Couldn’t sign in with GitHub'
    })
  } catch (err) {
    return gitHubFailure(event, (err as { statusMessage?: string }).statusMessage || 'Couldn’t sign in with GitHub')
  }
  if (result.outcome === 'linked') return sendRedirect(event, '/account?github=linked', 302)
  setSessionToken(event, result.token!, ((result.expires_at ?? 0) - Date.now() / 1000) / 86400)
  // A new account: its page, which offers to connect repositories, never without asking.
  return sendRedirect(event, result.outcome === 'signed_up' ? '/account?github=signed_up' : '/', 302)
})
