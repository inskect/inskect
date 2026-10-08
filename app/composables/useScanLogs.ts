import type { ScanLogsResponse } from '~~/shared/types/scan'

// As many as the API keeps per scan.
const MAX_LINES = 500

/**
 * A scan's log; none without an id (a shared result, whose log isn't shared). Loaded once `wanted`
 * (the log is on show), then, while the scan is `active`, polled for the lines logged since.
 */
export function useScanLogs(id: string | null, active: Ref<boolean>, wanted: Ref<boolean>) {
  const lines = ref<string[]>([])
  const loaded = ref(false)
  const error = ref<unknown>(null)
  let cursor = 0

  async function fetchNew() {
    if (id === null) return
    try {
      const response = await $fetch<ScanLogsResponse>(`/api/scan/${id}/logs`, { query: { after: cursor } })
      cursor = response.cursor
      if (response.lines.length) lines.value = [...lines.value, ...response.lines].slice(-MAX_LINES)
      error.value = null
    } catch (err) {
      error.value = err
    } finally {
      loaded.value = true
    }
  }

  const { start } = usePoll(fetchNew, () => active.value && wanted.value)

  onMounted(() => {
    watch([active, wanted], async ([isActive, isWanted], previous) => {
      if (!isWanted) return
      const [wasActive, wasWanted] = previous ?? [false, false]
      // When it comes on show, and once more when the scan finishes, for its last lines.
      if (!wasWanted || (wasActive && !isActive)) await fetchNew()
      if (isActive) start()
    }, { immediate: true })
  })

  return { lines, loaded, error }
}
