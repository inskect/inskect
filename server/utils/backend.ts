import type { H3Event } from 'h3'
import type { NitroFetchOptions, NitroFetchRequest } from 'nitropack'

type BackendOptions = NitroFetchOptions<NitroFetchRequest> & {
  // Shown when the API gives no message of its own.
  fallbackMessage: string
}

// FastAPI returns `detail` as a string, or as a list of validation errors.
function errorMessage(data: unknown, fallback: string): string {
  const detail = (data as { detail?: unknown } | undefined)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && typeof detail[0]?.msg === 'string') return detail[0].msg
  return fallback
}

/**
 * What every call to the API carries (backend/app/proxy.py): the proxy secret, which the API then
 * requires, so no one else can call it; and, for a visitor's request, their address, in a header of
 * our own, which proxies on the way to the API leave alone (some rewrite X-Forwarded-For).
 */
export function apiHeaders(event?: H3Event): Record<string, string> {
  const secret = process.env.INSKECT_PROXY_SECRET
  const headers: Record<string, string> = secret ? { 'X-Inskect-Proxy-Secret': secret } : {}
  if (event) {
    headers['X-Inskect-Client-IP'] = getClientIp(event)
    if (behindUntrustedProxy(event)) headers['X-Inskect-Untrusted-Forwarded-For'] = '1'
  }
  return headers
}

/**
 * Call the API on behalf of the browser, or of a script: forwards the client IP (for rate limits)
 * and the session cookie, or the script's API token, as a bearer token, and turns API errors into
 * h3 errors with the API's message.
 */
export async function backendFetch<T>(event: H3Event, path: string, options: BackendOptions): Promise<T> {
  const { apiBase } = useRuntimeConfig()
  const { fallbackMessage, headers, ...rest } = options
  const apiToken = getApiToken(event)
  const token = apiToken ?? getSessionToken(event)

  try {
    return await $fetch<T>(path, {
      ...rest,
      baseURL: apiBase,
      headers: {
        ...(headers as Record<string, string> | undefined),
        ...apiHeaders(event),
        ...(token ? { Authorization: `Bearer ${token}` } : {})
      }
    } as NitroFetchOptions<NitroFetchRequest>) as T
  } catch (error) {
    const { response, data } = (error ?? {}) as { response?: { status?: number }, data?: unknown }
    const statusCode = response?.status ?? 502
    // An expired or revoked session: drop the cookie so the next page asks to sign in again.
    if (statusCode === 401 && token && !apiToken) clearSessionToken(event)
    throw createError({ statusCode, statusMessage: errorMessage(data, fallbackMessage) })
  }
}

/**
 * Pass one of the API's downloads (a report export) through to the browser, with its type and
 * file name, as backendFetch would call it.
 */
export async function backendDownload(event: H3Event, path: string, query: Record<string, string>, fallbackMessage: string) {
  const { apiBase } = useRuntimeConfig()
  const token = getApiToken(event) ?? getSessionToken(event)
  try {
    const response = await $fetch.raw<ArrayBuffer>(path, {
      baseURL: apiBase,
      query,
      responseType: 'arrayBuffer',
      headers: {
        ...apiHeaders(event),
        ...(token ? { Authorization: `Bearer ${token}` } : {})
      }
    })
    for (const name of ['content-type', 'content-disposition']) {
      const value = response.headers.get(name)
      if (value) setResponseHeader(event, name, value)
    }
    return Buffer.from(response._data ?? new ArrayBuffer(0))
  } catch (error) {
    const { response, data } = (error ?? {}) as { response?: { status?: number }, data?: unknown }
    // An arrayBuffer error body: decode it for the API's message.
    const body = data instanceof ArrayBuffer ? JSON.parse(new TextDecoder().decode(data) || 'null') : data
    throw createError({ statusCode: response?.status ?? 502, statusMessage: errorMessage(body, fallbackMessage) })
  }
}

/** Whether the request confirms a private repository's scan may be made public
 * (`{ confirm_private: true }`); an empty body confirms nothing. */
export async function confirmedPrivate(event: H3Event): Promise<boolean> {
  const body = await readBody<{ confirm_private?: unknown } | undefined>(event).catch(() => undefined)
  return body?.confirm_private === true
}
