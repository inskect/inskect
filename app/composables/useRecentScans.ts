import type { ScanHistoryResponse } from '~~/shared/types/scan'

// Enough to spot a recent scan of the URL being typed; the home page lists the first few.
const RECENT_LIMIT = 20

export function useRecentScans() {
  return useFetch<ScanHistoryResponse>('/api/scan', {
    key: 'recent-scans',
    query: { limit: RECENT_LIMIT }
  })
}
