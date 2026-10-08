import type { ScanHistoryResponse } from '~~/shared/types/scan'

const PAGE_SIZE = 20

export type HistorySort = 'created_at' | 'target' | 'risk_score' | 'verdict' | 'status'
export type SortOrder = 'asc' | 'desc'

/**
 * The history, sorted by the API so paging stays right (newest first by default); with target,
 * only that target's scans (its timeline). "Load more" fetches the next page and appends it.
 */
export function useScanHistory(
  target?: Ref<string | undefined>,
  sort?: Ref<HistorySort>,
  order?: Ref<SortOrder>
) {
  // The first page: a new sort or target fetches it again, and drops the pages loaded after it.
  const { data, status, error } = useFetch<ScanHistoryResponse>('/api/scan', {
    key: 'scan-history',
    query: { limit: PAGE_SIZE, target, sort, order }
  })

  const hasMore = computed(() => (data.value?.items.length ?? 0) < (data.value?.total ?? 0))

  const loadingMore = ref(false)
  const loadMoreError = ref<unknown>(null)
  // Bumped when the first page is fetched again, so a page asked for before then is dropped.
  let generation = 0
  watch([() => target?.value, () => sort?.value, () => order?.value], () => {
    generation++
    loadingMore.value = false
  })

  async function loadMore() {
    if (!data.value || loadingMore.value) return
    const asked = generation
    loadingMore.value = true
    loadMoreError.value = null
    try {
      const page = await $fetch<ScanHistoryResponse>('/api/scan', {
        query: { limit: PAGE_SIZE, offset: data.value.items.length, target: target?.value, sort: sort?.value, order: order?.value }
      })
      if (asked !== generation || !data.value) return
      // A scan started since shifts the pages by one: skip what's already shown.
      const shown = new Set(data.value.items.map(scan => scan.id))
      data.value = { items: [...data.value.items, ...page.items.filter(scan => !shown.has(scan.id))], total: page.total }
    } catch (err) {
      if (asked === generation) loadMoreError.value = err
    } finally {
      if (asked === generation) loadingMore.value = false
    }
  }

  /** Drops a deleted scan from the list, so the pages after it still start at the right offset. */
  function remove(id: string) {
    if (!data.value) return
    const items = data.value.items.filter(scan => scan.id !== id)
    data.value = { items, total: data.value.total - (data.value.items.length - items.length) }
  }

  return { data, status, error, hasMore, loadMore, loadingMore, loadMoreError, remove }
}
