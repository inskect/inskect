// The scan a target's badge shows, from the API. No session or token goes with it: a badge is the
// same for everyone, and cached as such.
export async function fetchBadge(target: string): Promise<Partial<BadgeData>> {
  const { apiBase } = useRuntimeConfig()
  return await $fetch<BadgeData>('/badge', { baseURL: apiBase, headers: apiHeaders(), query: { target: target.slice(0, 2048) } })
}
