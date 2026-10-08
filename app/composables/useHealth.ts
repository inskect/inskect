// Shared by the home page's status pill and the scan form, so the health check runs once.
export function useHealth() {
  return useFetch('/api/health', { key: 'health' })
}
