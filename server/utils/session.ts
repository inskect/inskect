import type { H3Event } from 'h3'

// The API's session token lives only in this httpOnly cookie: page scripts never see it, and the
// Nitro proxy forwards it to the API as a bearer token.
const SESSION_COOKIE = 'inskect_session'

export function getSessionToken(event: H3Event): string | undefined {
  return getCookie(event, SESSION_COOKIE) || undefined
}

// A script's personal API token (backend/app/auth/api_tokens.py), sent as `Authorization: Bearer
// sst_…`: passed on to the API as it came. Only API tokens: a browser is identified by its cookie.
const API_TOKEN = /^Bearer (sst_[\w-]+)$/

export function getApiToken(event: H3Event): string | undefined {
  return getHeader(event, 'authorization')?.trim().match(API_TOKEN)?.[1]
}

export function setSessionToken(event: H3Event, token: string, maxAgeDays: number) {
  setCookie(event, SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: 'lax',
    path: '/',
    // Over HTTPS (directly or behind a TLS-terminating proxy) the cookie is never sent in clear.
    secure: getRequestProtocol(event, { xForwardedProto: true }) === 'https',
    maxAge: Math.round(maxAgeDays * 86400)
  })
}

export function clearSessionToken(event: H3Event) {
  deleteCookie(event, SESSION_COOKIE, { path: '/' })
}
