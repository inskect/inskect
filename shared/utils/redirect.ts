// The placeholder origin `localPath` resolves against: any other origin in the result means the
// target pointed somewhere else.
const HERE = 'https://here.invalid'

/**
 * `target` when it's a path on this site, otherwise null: a `?redirect=` can only ever lead within
 * the app. Refuses what browsers read as another host (`//host`, `/\host`), and backslashes and
 * control characters, which some of them skip or turn into slashes.
 */
export function localPath(target: unknown): string | null {
  if (typeof target !== 'string' || !target.startsWith('/') || target.startsWith('//')) return null
  // eslint-disable-next-line no-control-regex
  if (/[\\\u0000-\u001F\u007F]/.test(target)) return null
  let url: URL
  try {
    url = new URL(target, HERE)
  } catch {
    return null
  }
  return url.origin === HERE ? `${url.pathname}${url.search}${url.hash}` : null
}
