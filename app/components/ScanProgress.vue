<script setup lang="ts">
import type { ScanStatus } from '~~/shared/types/scan'

const props = defineProps<{
  status: ScanStatus | null | undefined
  title: string
  lines: string[]
}>()

const stages = computed(() => groupCompletedStages(props.lines))
const completed = computed(() => props.status?.completed_steps ?? 0)
const total = computed(() => props.status?.total_steps ?? 0)
const remaining = computed(() => Math.max(0, total.value - completed.value))
const queued = computed(() => props.status?.status === 'pending')
</script>

<template>
  <div class="flex flex-col gap-6">
    <section class="surface border-2 border-inverted">
      <div class="flex flex-wrap items-center justify-between gap-5 border-b border-default p-5 sm:p-7">
        <div class="flex min-w-0 flex-col gap-1.5">
          <span class="eyebrow text-muted">
            Inspection report<template v-if="reportLabel(status?.report_no)"> · {{ reportLabel(status?.report_no) }}</template>
          </span>
          <h1 class="display text-4xl leading-tight break-words text-highlighted sm:text-5xl">
            <UntrustedText :value="title" />
          </h1>
          <p
            v-if="status"
            class="font-mono text-sm break-all text-muted"
          >
            <UntrustedText :value="status.target" />
          </p>
        </div>
        <span class="shrink-0 border-[3px] border-dashed border-accented px-3 py-1 font-display text-2xl font-bold tracking-widest text-muted uppercase">
          {{ queued ? 'Queued' : 'Inspecting…' }}
        </span>
      </div>
      <div class="flex flex-wrap justify-between gap-x-4 gap-y-1 px-5 py-3 text-sm sm:px-7">
        <span class="font-mono text-highlighted tabular-nums">
          <template v-if="total">Checks {{ completed }} / {{ total }}</template>
          <template v-else>Starting…</template>
        </span>
        <span class="text-muted">Static inspections usually take about a minute; with AI review, a few.</span>
      </div>
      <UProgress
        :model-value="completed"
        :max="total || 1"
        color="primary"
        size="sm"
        :ui="{ base: 'rounded-none bg-accented', indicator: 'rounded-none' }"
      />
    </section>

    <div class="flex flex-wrap items-start gap-6">
      <section
        aria-labelledby="stages-heading"
        class="surface flex min-w-0 flex-[1_1_22rem] flex-col"
      >
        <h2
          id="stages-heading"
          class="eyebrow border-b border-inverted px-5 py-3.5 text-highlighted"
        >
          Checklist
        </h2>
        <ul class="m-0 flex list-none flex-col p-0">
          <li
            v-for="stage in stages"
            :key="stage.label"
            class="grid grid-cols-[1.5rem_minmax(0,1fr)_auto] items-center gap-3 border-b border-muted px-5 py-3 text-sm"
          >
            <span class="flex size-[18px] items-center justify-center border-[1.5px] border-inverted font-mono text-xs text-highlighted">✓</span>
            <span class="text-highlighted">{{ stage.label }}</span>
            <span class="font-mono text-xs text-muted tabular-nums">{{ stage.completed }} done</span>
          </li>
          <li class="grid grid-cols-[1.5rem_minmax(0,1fr)_auto] items-center gap-3 bg-insp-50 px-5 py-3 text-sm dark:bg-insp-950/60">
            <UIcon
              name="i-lucide-loader-circle"
              class="size-[18px] animate-spin text-brand-ink"
            />
            <span class="font-semibold text-highlighted">
              {{ queued ? 'Waiting for a free inspection slot' : 'Running the next checks' }}
            </span>
            <span
              v-if="total && !queued"
              class="font-mono text-xs text-brand-ink tabular-nums"
            >{{ remaining }} left</span>
          </li>
        </ul>
        <p class="px-5 py-4 text-sm text-muted">
          You can leave this page: the inspection keeps running, and its report will be in your history.
        </p>
      </section>

      <section
        aria-labelledby="log-heading"
        class="flex min-w-0 flex-[999_1_30rem] flex-col bg-code"
      >
        <div class="flex items-center justify-between border-b border-graphite-800 px-5 py-3.5">
          <h2
            id="log-heading"
            class="eyebrow text-graphite-300"
          >
            Inspector’s log
          </h2>
          <span class="flex items-center gap-1.5 font-mono text-xs text-insp-300">
            <span class="size-1.5 animate-pulse bg-insp-300" />
            live
          </span>
        </div>
        <ScanLogPanel
          v-if="lines.length"
          :lines="lines"
          tall
        />
        <p
          v-else
          class="p-5 font-mono text-xs text-graphite-400"
        >
          Waiting for the first log line…
        </p>
      </section>
    </div>
  </div>
</template>
