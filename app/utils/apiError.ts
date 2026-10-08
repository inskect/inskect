// The Nitro proxies return the backend's message as `statusMessage` in the JSON body; the
// FetchError's own `message` wraps it as `[POST] "/api/scan": 429 …`, which isn't for humans.
export function apiErrorMessage(err: unknown, fallback: string): string {
  const { data, response } = (err ?? {}) as {
    data?: { statusMessage?: string, message?: string }
    response?: { status?: number }
  }
  const message = typeof data === 'object' ? data?.statusMessage || data?.message : undefined
  if (message) {
    const text = message.replace(/^Value error, /, '')
    return text.charAt(0).toUpperCase() + text.slice(1)
  }
  // A limit hit before the request reached the app (e.g. a firewall rule) has no message of ours.
  if (response?.status === 429) {
    return 'Too many requests — wait a minute and try again.'
  }
  if (err && typeof err === 'object' && 'data' in err && !response) {
    return 'Couldn’t reach the server — check your connection and try again.'
  }
  return fallback
}
