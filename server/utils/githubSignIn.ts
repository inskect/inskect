import type { H3Event } from 'h3'

// Signing in with GitHub (backend/app/auth/github_sign_in.py): the browser that starts it keeps a
// nonce in this httpOnly cookie, and only a callback in that same browser can finish it.
export const GITHUB_NONCE_COOKIE = 'inskect_github_nonce'
const COOKIE_PATH = '/api/auth/github'

export function setGitHubNonce(event: H3Event, nonce: string) {
  setCookie(event, GITHUB_NONCE_COOKIE, nonce, {
    httpOnly: true,
    // Sent on GitHub's redirect back, a top-level navigation.
    sameSite: 'lax',
    path: COOKIE_PATH,
    secure: getRequestProtocol(event, { xForwardedProto: true }) === 'https',
    maxAge: 600
  })
}

/** The nonce, read once: the cookie goes whatever happens next. */
export function takeGitHubNonce(event: H3Event): string | undefined {
  const nonce = getCookie(event, GITHUB_NONCE_COOKIE)
  deleteCookie(event, GITHUB_NONCE_COOKIE, { path: COOKIE_PATH })
  return nonce || undefined
}

/** Back to where the sign-in started, saying why it didn't work. */
export function gitHubFailure(event: H3Event, message: string) {
  const page = getSessionToken(event) ? '/account' : '/login'
  return sendRedirect(event, `${page}?github_error=${encodeURIComponent(message)}`, 302)
}
