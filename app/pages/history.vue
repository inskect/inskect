<script setup lang="ts">
import type { Recommendation, ScanSummary } from '~~/shared/types/scan'
import type { HistorySort, SortOrder } from '../composables/useScanHistory'
import type { SettingsResponse } from '~~/shared/types/settings'

useSeoMeta({ title: 'Inspection history — Inskect' })

// ?target=… shows one target's inspections, e.g. from a report's "All inspections of this target".
const route = useRoute()
const targetFilter = computed(() => typeof route.query.target === 'string' && route.query.target ? route.query.target : undefined)
// The table's sortable columns, in order, and their width.
const SORTED_COLUMNS: { key: HistorySort, class: string }[] = [
  { key: 'target', class: 'px-4 py-3.5 sm:px-5' },
  { key: 'verdict', class: 'w-36 px-4 py-3.5 sm:w-44 sm:px-5' },
  { key: 'risk_score', class: 'w-52 px-5 py-3.5 max-md:hidden' },
  { key: 'created_at', class: 'w-36 px-5 py-3.5 max-sm:hidden' }
]

// ?sort=…&order=… sorts the whole history (the API does), so a sorted view survives a reload and
// can be linked to. Each column starts in the order most often wanted: riskiest, newest, A to Z.
const SORTS: Record<HistorySort, { label: string, first: SortOrder }> = {
  target: { label: 'Skill', first: 'asc' },
  verdict: { label: 'Verdict', first: 'desc' },
  risk_score: { label: 'Risk score', first: 'desc' },
  created_at: { label: 'Inspected', first: 'desc' },
  status: { label: 'Status', first: 'asc' }
}
const router = useRouter()
const sort = computed<HistorySort>(() => {
  const value = route.query.sort
  return typeof value === 'string' && value in SORTS ? value as HistorySort : 'created_at'
})
const order = computed<SortOrder>(() => {
  const value = route.query.order
  return value === 'asc' || value === 'desc' ? value : SORTS[sort.value].first
})

function sortBy(column: HistorySort) {
  const next = column === sort.value ? (order.value === 'asc' ? 'desc' : 'asc') : SORTS[column].first
  const isDefault = column === 'created_at' && next === 'desc'
  router.replace({ query: { ...route.query, sort: isDefault ? undefined : column, order: isDefault ? undefined : next } })
}

function ariaSort(column: HistorySort): 'ascending' | 'descending' | 'none' {
  if (column !== sort.value) return 'none'
  return order.value === 'asc' ? 'ascending' : 'descending'
}

function sortIcon(column: HistorySort) {
  if (column !== sort.value) return 'i-lucide-chevrons-up-down'
  if (reloading.value) return 'i-lucide-loader-circle'
  return order.value === 'asc' ? 'i-lucide-arrow-up' : 'i-lucide-arrow-down'
}

const { data, status, error, hasMore, loadMore, loadingMore, loadMoreError, remove } = useScanHistory(targetFilter, sort, order)

// A new sort, or another target's timeline, keeps the rows shown until the new ones arrive: dimmed,
// under a progress bar, with a spinner in the sorted column's header. Only once it takes a moment,
// so a quick answer doesn't flash. "Load more" shows its own.
const RELOAD_DELAY_MS = 200
const reloading = ref(false)
let reloadTimer: ReturnType<typeof setTimeout> | undefined
watch([sort, order, targetFilter], () => {
  clearTimeout(reloadTimer)
  reloadTimer = setTimeout(() => {
    if (status.value === 'pending') reloading.value = true
  }, RELOAD_DELAY_MS)
})
watch(status, (value) => {
  if (value === 'pending') return
  clearTimeout(reloadTimer)
  reloading.value = false
})
onUnmounted(() => clearTimeout(reloadTimer))
const { data: settingsData } = await useFetch<SettingsResponse>('/api/settings')

// The register's line: how many inspections, and how long they're kept.
const registerLine = computed(() => {
  const parts = data.value ? [`${data.value.total} inspection${data.value.total === 1 ? '' : 's'}`] : []
  const days = settingsData.value?.scan_retention_days
  parts.push(days ? `kept ${days} day${days === 1 ? '' : 's'}` : 'kept until deleted')
  const line = parts.join(' · ')
  return line.charAt(0).toUpperCase() + line.slice(1)
})

type VerdictFilter = 'all' | Recommendation | 'error'

const VERDICT_FILTERS: { value: VerdictFilter, label: string, dot?: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'DO_NOT_INSTALL', label: RECOMMENDATION_SHORT_LABEL.DO_NOT_INSTALL, dot: RECOMMENDATION_CLASSES.DO_NOT_INSTALL.dot },
  { value: 'CAUTION', label: RECOMMENDATION_SHORT_LABEL.CAUTION, dot: RECOMMENDATION_CLASSES.CAUTION.dot },
  { value: 'SAFE', label: RECOMMENDATION_SHORT_LABEL.SAFE, dot: RECOMMENDATION_CLASSES.SAFE.dot },
  { value: 'error', label: 'Didn’t run' }
]

const verdictFilter = ref<VerdictFilter>('all')
const search = ref('')

function verdictOf(scan: ScanSummary): VerdictFilter | null {
  if (scan.status === 'error') return 'error'
  return scan.recommendation
}

// Filtering runs over the inspections loaded so far, so counts only show once every one is loaded.
const verdictCounts = computed(() => {
  if (hasMore.value) return undefined
  const counts: Partial<Record<VerdictFilter, number>> = { all: data.value?.items.length ?? 0 }
  for (const scan of data.value?.items ?? []) {
    const verdict = verdictOf(scan)
    if (verdict) counts[verdict] = (counts[verdict] ?? 0) + 1
  }
  return counts
})

const visibleScans = computed(() => {
  const query = search.value.trim().toLowerCase()
  return (data.value?.items ?? []).filter((scan) => {
    if (verdictFilter.value !== 'all' && verdictOf(scan) !== verdictFilter.value) return false
    return !query || scan.target.toLowerCase().includes(query)
  })
})

// With ?target=…, that target's inspections loaded so far as a timeline, oldest first, each with
// its risk's change since the inspection before it.
const timeline = computed(() => {
  if (!targetFilter.value) return []
  const scans = [...(data.value?.items ?? [])].sort((a, b) => a.created_at - b.created_at)
  let previous: number | null = null
  return scans.map((scan) => {
    const risk = scan.status === 'done' ? scan.risk_score : null
    const delta = risk !== null && previous !== null ? risk - previous : null
    if (risk !== null) previous = risk
    return { scan, risk, delta }
  })
})

const deleteTarget = ref<ScanSummary | null>(null)
const deleting = ref(false)
const deleteError = ref('')

function openDeleteModal(scan: ScanSummary) {
  deleteTarget.value = scan
  deleteError.value = ''
}

function closeDeleteModal() {
  deleteTarget.value = null
}

// The target again, as that inspection ran; the new report is compared with it.
const rescanningId = ref<string | null>(null)
const rescanError = ref('')
async function rescanScan(scan: ScanSummary) {
  rescanningId.value = scan.id
  rescanError.value = ''
  try {
    const { id } = await $fetch<{ id: string }>(`/api/scan/${scan.id}/rescan`, { method: 'POST' })
    await navigateTo(`/scan/${id}`)
  } catch (err) {
    rescanError.value = apiErrorMessage(err, 'Couldn’t re-inspect')
    rescanningId.value = null
  }
}

async function confirmDelete() {
  if (!deleteTarget.value) return

  deleting.value = true
  deleteError.value = ''

  try {
    const { id } = deleteTarget.value
    await $fetch(`/api/scan/${id}`, { method: 'DELETE' })
    closeDeleteModal()
    remove(id)
  } catch (err) {
    deleteError.value = apiErrorMessage(err, 'Couldn’t delete the inspection')
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <UContainer class="flex flex-col gap-7 py-12 sm:py-14">
    <div class="flex flex-wrap items-end justify-between gap-4 border-b-2 border-inverted pb-5">
      <div class="flex flex-col gap-2">
        <p class="eyebrow text-muted">
          Register
        </p>
        <h1 class="display text-5xl text-highlighted sm:text-6xl">
          Inspection history
        </h1>
        <p class="text-[15px] text-muted">
          <template v-if="targetFilter && data">
            {{ data.total }} inspection{{ data.total === 1 ? '' : 's' }} of
            <span class="font-mono text-sm text-highlighted"><UntrustedText :value="parseScanTarget(targetFilter).title" /></span>.
            <ULink
              to="/history"
              class="font-semibold text-brand-ink"
            >
              Clear the target filter
            </ULink>
          </template>
          <template v-else>
            {{ registerLine }}
          </template>
        </p>
      </div>
      <UButton
        to="/"
        icon="i-lucide-plus"
        color="primary"
        size="lg"
        class="font-semibold"
      >
        New inspection
      </UButton>
    </div>

    <UAlert
      v-if="rescanError"
      color="error"
      variant="subtle"
      icon="i-lucide-circle-alert"
      title="Couldn’t re-inspect"
      :description="rescanError"
    />

    <UAlert
      v-if="error"
      color="error"
      variant="subtle"
      title="Couldn’t load the inspection history"
      :description="apiErrorMessage(error, error.message)"
    />

    <div
      v-else-if="status === 'pending' && !data"
      class="surface overflow-hidden"
      aria-busy="true"
    >
      <p class="sr-only">
        Loading inspections…
      </p>
      <!-- The table as it will be, so nothing moves once the inspections arrive. -->
      <table
        class="w-full table-fixed text-sm"
        aria-hidden="true"
      >
        <thead>
          <tr class="eyebrow border-b border-default text-left text-muted">
            <th class="w-28 px-4 py-3.5 font-medium max-sm:hidden sm:px-5">
              No.
            </th>
            <th
              v-for="column in SORTED_COLUMNS"
              :key="column.key"
              :class="column.class"
              class="font-medium"
            >
              {{ SORTS[column.key].label }}
            </th>
            <th class="w-24 sm:w-28" />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in 5"
            :key="row"
            class="border-b border-muted last:border-b-0"
          >
            <td class="px-4 py-4 max-sm:hidden sm:px-5">
              <USkeleton class="h-3 w-16" />
            </td>
            <td class="px-4 py-4 sm:px-5">
              <USkeleton class="mb-2 h-3.5 w-40 max-w-full" />
              <USkeleton class="h-3 w-24 max-w-full" />
            </td>
            <td class="px-4 py-4 sm:px-5">
              <USkeleton class="h-6 w-24" />
            </td>
            <td class="px-5 py-4 max-md:hidden">
              <USkeleton class="h-1.5 w-24" />
            </td>
            <td class="px-5 py-4 max-sm:hidden">
              <USkeleton class="h-3 w-20" />
            </td>
            <td />
          </tr>
        </tbody>
      </table>
    </div>

    <div
      v-else-if="!data?.items.length"
      class="surface flex flex-col items-start gap-3 p-6"
    >
      <p class="text-lg font-semibold tracking-tight text-highlighted">
        No inspections yet
      </p>
      <p class="text-sm text-muted">
        Each inspection you run is filed here, so you can come back to its report later.
      </p>
    </div>

    <template v-else>
      <section
        v-if="timeline.length"
        aria-labelledby="timeline-heading"
        class="surface"
      >
        <h2
          id="timeline-heading"
          class="eyebrow m-0 border-b border-inverted px-5 py-3.5 text-highlighted sm:px-6"
        >
          Timeline<span class="sr-only"> of this target, oldest first</span>
        </h2>
        <ol class="m-0 flex list-none overflow-x-auto p-0">
          <li
            v-for="(entry, index) in timeline"
            :key="entry.scan.id"
            class="flex-[1_0_11rem] not-last:border-r not-last:border-muted"
          >
            <NuxtLink
              :to="`/scan/${entry.scan.id}`"
              class="flex h-full flex-col items-start gap-2 px-5 py-4 transition-colors hover:bg-muted sm:px-6"
              :class="{ 'bg-brand/8': index === timeline.length - 1 }"
            >
              <span
                class="font-mono text-xs"
                :class="index === timeline.length - 1 ? 'text-brand-ink' : 'text-muted'"
              >
                <template v-if="reportLabel(entry.scan.report_no)">{{ reportLabel(entry.scan.report_no) }} · </template>
                <NuxtTime
                  :datetime="entry.scan.created_at * 1000"
                  day="numeric"
                  month="short"
                />
              </span>
              <VerdictStamp
                :recommendation="entry.scan.recommendation"
                :failed="entry.scan.status === 'error'"
                size="sm"
              />
              <span
                v-if="entry.risk !== null"
                class="font-mono text-[13px] text-highlighted"
              >
                risk {{ entry.risk }}
                <span
                  v-if="entry.delta"
                  :class="entry.delta > 0 ? 'text-critical-ink' : 'text-safe-ink'"
                >{{ entry.delta > 0 ? '+' : '−' }}{{ Math.abs(entry.delta) }}</span>
              </span>
            </NuxtLink>
          </li>
        </ol>
      </section>

      <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div
          role="group"
          aria-label="Filter by verdict"
          class="flex flex-wrap gap-1.5"
        >
          <button
            v-for="filter in VERDICT_FILTERS"
            :key="filter.value"
            type="button"
            :aria-pressed="verdictFilter === filter.value"
            class="flex h-10 cursor-pointer items-center gap-2 border px-3.5 text-sm font-medium transition-colors"
            :class="verdictFilter === filter.value ? 'border-inverted bg-inverted text-inverted' : 'border-default bg-default text-highlighted hover:bg-muted'"
            @click="verdictFilter = filter.value"
          >
            <span
              v-if="filter.dot"
              class="size-2"
              :class="filter.dot"
            />
            <span
              v-else-if="filter.value === 'error'"
              class="size-2 border-2 border-accented"
            />
            {{ filter.label }}
            <span
              v-if="verdictCounts"
              class="font-mono tabular-nums opacity-70"
            >{{ verdictCounts[filter.value] ?? 0 }}</span>
          </button>
        </div>
        <UInput
          v-model="search"
          type="search"
          icon="i-lucide-search"
          placeholder="Filter by skill or repo"
          aria-label="Filter by skill or repo"
          size="lg"
          class="md:w-80"
          :ui="{ base: 'rounded-none' }"
        />
      </div>

      <div
        class="surface relative overflow-hidden"
        :aria-busy="reloading"
      >
        <div
          v-if="reloading"
          class="absolute inset-x-0 top-0 z-10 h-0.5 overflow-hidden bg-brand/15"
          aria-hidden="true"
        >
          <div class="h-full w-1/3 animate-sweep bg-brand motion-reduce:w-full motion-reduce:animate-none motion-reduce:opacity-60" />
        </div>
        <p
          class="sr-only"
          aria-live="polite"
        >
          {{ reloading ? 'Loading inspections' : '' }}
        </p>
        <table class="w-full table-fixed text-sm">
          <thead>
            <tr class="eyebrow border-b border-default text-left text-muted">
              <th
                scope="col"
                class="w-28 px-4 py-3.5 font-medium max-sm:hidden sm:px-5"
              >
                No.
              </th>
              <th
                v-for="column in SORTED_COLUMNS"
                :key="column.key"
                scope="col"
                :class="column.class"
                :aria-sort="ariaSort(column.key)"
              >
                <button
                  type="button"
                  class="group -mx-1 inline-flex cursor-pointer items-center gap-1.5 px-1 py-0.5 font-medium uppercase hover:text-highlighted focus-visible:outline-2 focus-visible:outline-brand"
                  :class="{ 'text-highlighted': column.key === sort }"
                  @click="sortBy(column.key)"
                >
                  {{ SORTS[column.key].label }}
                  <UIcon
                    :name="sortIcon(column.key)"
                    class="size-3.5 shrink-0"
                    :class="column.key !== sort ? 'opacity-40 group-hover:opacity-100' : reloading ? 'animate-spin text-primary' : ''"
                    aria-hidden="true"
                  />
                </button>
              </th>
              <th
                scope="col"
                class="w-24 sm:w-28"
              >
                <span class="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody
            class="transition-opacity"
            :class="{ 'opacity-50': reloading }"
          >
            <tr
              v-for="scan in visibleScans"
              :key="scan.id"
              class="border-b border-muted transition-colors last:border-b-0 hover:bg-muted"
            >
              <td class="px-4 py-3.5 font-mono text-[13px] text-muted max-sm:hidden sm:px-5">
                {{ reportLabel(scan.report_no) ?? '—' }}
              </td>
              <td class="px-4 py-3.5 sm:px-5">
                <NuxtLink
                  :to="`/scan/${scan.id}`"
                  class="flex min-w-0 flex-col gap-0.5"
                  :title="scan.target"
                >
                  <span class="truncate font-semibold text-highlighted"><UntrustedText :value="splitScanTitle(scan.target).name" /></span>
                  <span class="truncate font-mono text-xs text-dimmed">
                    <UntrustedText :value="splitScanTitle(scan.target).source ?? scan.target" />
                  </span>
                  <span
                    class="font-mono text-xs text-dimmed sm:hidden"
                    :title="formatDate(scan.created_at)"
                  >
                    <template v-if="reportLabel(scan.report_no)">{{ reportLabel(scan.report_no) }} · </template>
                    <NuxtTime
                      :datetime="scan.created_at * 1000"
                      relative
                    />
                  </span>
                </NuxtLink>
              </td>
              <td class="px-4 py-3.5 whitespace-nowrap sm:px-5">
                <span
                  v-if="scan.status === 'pending' || scan.status === 'running'"
                  class="inline-flex items-center gap-2 text-highlighted"
                >
                  <UIcon
                    name="i-lucide-loader-circle"
                    class="size-3.5 animate-spin"
                  />
                  {{ scan.status === 'pending' ? 'Queued' : 'Inspecting' }}
                </span>
                <VerdictStamp
                  v-else-if="scan.status === 'error' || !scan.recommendation"
                  :recommendation="null"
                  failed
                  size="sm"
                  :title="scan.error ?? undefined"
                />
                <VerdictStamp
                  v-else
                  :recommendation="scan.recommendation"
                  size="sm"
                />
                <span
                  v-if="scan.status === 'done' && (scan.ai_review === 'failed' || scan.ai_review === 'degraded')"
                  class="ml-2 inline-flex items-center gap-1 align-middle text-xs font-medium text-medium-ink"
                  :title="scan.ai_review === 'failed' ? 'AI review was requested but didn\'t run' : 'AI review was requested but only partly ran'"
                >
                  <UIcon
                    name="i-lucide-bot-off"
                    class="size-3.5"
                  />
                  {{ scan.ai_review === 'failed' ? 'No AI review' : 'Partial AI review' }}
                </span>
              </td>
              <td class="px-5 py-3.5 max-md:hidden">
                <div
                  v-if="scan.status === 'pending' || scan.status === 'running'"
                  class="flex items-center gap-2.5"
                >
                  <UProgress
                    :model-value="scan.completed_steps"
                    :max="scan.total_steps || 1"
                    color="neutral"
                    size="sm"
                    class="w-24"
                  />
                  <span class="font-mono text-xs text-muted tabular-nums">{{ scan.completed_steps }}/{{ scan.total_steps }}</span>
                </div>
                <p
                  v-else-if="scan.status === 'error'"
                  class="line-clamp-1 max-w-56 text-[13px] text-muted"
                  :title="scan.error ?? undefined"
                >
                  {{ scan.error }}
                </p>
                <div
                  v-else-if="scan.risk_score !== null && scan.severity"
                  class="flex items-center gap-2.5"
                >
                  <div class="h-1.5 w-24 overflow-hidden bg-elevated">
                    <div
                      class="h-full"
                      :class="SEVERITY_CLASSES[scan.severity].dot"
                      :style="{ width: `${Math.max(scan.risk_score, 2)}%` }"
                    />
                  </div>
                  <span class="font-mono text-[13px] font-medium text-highlighted tabular-nums">{{ scan.risk_score }}</span>
                </div>
              </td>
              <td
                class="px-5 py-3.5 whitespace-nowrap text-muted max-sm:hidden"
                :title="formatDate(scan.created_at)"
              >
                <NuxtTime
                  :datetime="scan.created_at * 1000"
                  relative
                />
              </td>
              <td class="px-2 py-2 whitespace-nowrap sm:px-3">
                <UButton
                  v-if="scan.rescan"
                  icon="i-lucide-rotate-cw"
                  variant="ghost"
                  color="neutral"
                  aria-label="Re-inspect, and compare with this inspection"
                  title="Re-inspect, and compare with this inspection"
                  class="size-10 justify-center text-dimmed hover:text-highlighted"
                  :loading="rescanningId === scan.id"
                  :disabled="rescanningId !== null"
                  @click="rescanScan(scan)"
                />
                <UButton
                  v-if="scan.status !== 'pending' && scan.status !== 'running'"
                  icon="i-lucide-trash-2"
                  variant="ghost"
                  color="neutral"
                  aria-label="Delete inspection"
                  class="size-10 justify-center text-dimmed hover:text-critical-ink"
                  @click="openDeleteModal(scan)"
                />
              </td>
            </tr>
          </tbody>
        </table>

        <p
          v-if="!visibleScans.length"
          class="px-5 py-6 text-sm text-muted"
        >
          No loaded inspections match.
          <button
            type="button"
            class="cursor-pointer font-medium text-highlighted underline underline-offset-2"
            @click="verdictFilter = 'all'; search = ''"
          >
            Clear filters
          </button>
        </p>
      </div>

      <div class="flex items-center justify-between gap-4 text-sm text-muted">
        <span>Showing {{ visibleScans.length }} of {{ data.total }}</span>
        <div
          v-if="hasMore"
          class="flex items-center gap-3"
        >
          <span
            v-if="loadMoreError"
            class="text-critical-ink"
            role="alert"
          >
            {{ apiErrorMessage(loadMoreError, 'Couldn’t load more inspections') }}
          </span>
          <UButton
            color="neutral"
            variant="outline"
            size="lg"
            :loading="loadingMore"
            @click="loadMore"
          >
            Load more
          </UButton>
        </div>
      </div>
    </template>

    <UModal
      :open="!!deleteTarget"
      title="Delete inspection"
      description="Its report goes too. This can't be undone."
      @update:open="(value) => { if (!value) closeDeleteModal() }"
    >
      <template #body>
        <div class="flex flex-col gap-4">
          <p class="font-mono text-sm break-all text-muted">
            <UntrustedText :value="deleteTarget ? parseScanTarget(deleteTarget.target).title : ''" />
          </p>

          <UAlert
            v-if="deleteError"
            color="error"
            variant="subtle"
            :title="deleteError"
          />
        </div>
      </template>

      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <UButton
            variant="ghost"
            color="neutral"
            :disabled="deleting"
            @click="closeDeleteModal"
          >
            Cancel
          </UButton>
          <UButton
            color="error"
            icon="i-lucide-trash-2"
            :loading="deleting"
            @click="confirmDelete"
          >
            Delete
          </UButton>
        </div>
      </template>
    </UModal>
  </UContainer>
</template>
