// Flipped by the `hydrated` plugin. Until then the server's timezone (UTC in Docker) and the
// browser's would disagree, and the two renders wouldn't match.
export const isHydrated = ref(false)

/** The full local date and time, for a `title` tooltip; undefined until the page has hydrated. */
export function formatDate(seconds: number): string | undefined {
  if (!isHydrated.value) return undefined
  return new Date(seconds * 1000).toLocaleString()
}
