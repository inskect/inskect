<script setup lang="ts">
import type { ScanSummary } from '~~/shared/types/scan'

const SHOWN = 5

const { data } = useRecentScans()
const scans = computed(() => data.value?.items.slice(0, SHOWN) ?? [])

function isWorking(scan: ScanSummary) {
  return scan.status === 'pending' || scan.status === 'running'
}
</script>

<template>
  <aside
    aria-labelledby="recent-scans-heading"
    class="surface flex flex-col"
  >
    <div class="flex items-baseline justify-between border-b border-inverted px-5 py-3.5">
      <h2
        id="recent-scans-heading"
        class="eyebrow text-highlighted"
      >
        Recent inspections
      </h2>
      <ULink
        to="/history"
        class="text-sm font-semibold text-brand-ink"
      >
        All
      </ULink>
    </div>

    <ul
      v-if="scans.length"
      class="m-0 flex list-none flex-col p-0"
    >
      <li
        v-for="scan in scans"
        :key="scan.id"
        class="not-last:border-b not-last:border-muted"
      >
        <NuxtLink
          :to="`/scan/${scan.id}`"
          class="flex items-center justify-between gap-3 px-5 py-3.5 transition-colors hover:bg-muted"
        >
          <span class="flex min-w-0 flex-col gap-0.5">
            <span
              class="truncate font-mono text-sm text-highlighted"
              :title="scan.target"
            ><UntrustedText :value="splitScanTitle(scan.target).name" /></span>
            <span
              class="truncate text-xs text-muted"
              :title="formatDate(scan.created_at)"
            >
              <template v-if="reportLabel(scan.report_no)">{{ reportLabel(scan.report_no) }} · </template>
              <template v-if="splitScanTitle(scan.target).source"><UntrustedText :value="splitScanTitle(scan.target).source" /> · </template>
              <NuxtTime
                :datetime="scan.created_at * 1000"
                relative
              />
            </span>
          </span>

          <span
            v-if="isWorking(scan)"
            class="flex shrink-0 items-center gap-1.5 font-mono text-xs text-muted tabular-nums"
          >
            <UIcon
              name="i-lucide-loader-circle"
              class="size-3.5 animate-spin"
            />
            {{ scan.status === 'pending' ? 'Queued' : `${scan.completed_steps}/${scan.total_steps}` }}
          </span>
          <VerdictStamp
            v-else
            :recommendation="scan.recommendation"
            failed
            size="sm"
          />
        </NuxtLink>
      </li>
    </ul>

    <p
      v-else
      class="p-5 text-sm text-muted"
    >
      Inspections you run show up here, so you can come back to a report later.
    </p>
  </aside>
</template>
