import type { ScanStatus } from '../../shared/types/scan'

/** A scan's status and result from url (/api/scan/<id>, or /api/shared/<token>), polled until done. */
export function useScanStatus(url: string) {
  const { data: status, error, refresh } = useFetch<ScanStatus>(url, {
    key: url
  })

  // Also while there's no status yet: it failed to load, and the next try may not.
  usePoll(refresh, () => !status.value || status.value.status === 'pending' || status.value.status === 'running')

  return { status, error }
}
