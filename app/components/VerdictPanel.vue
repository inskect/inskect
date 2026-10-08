<script setup lang="ts">
import type { ScanReport, Severity } from '~~/shared/types/scan'

const props = defineProps<{
  report: ScanReport
  // For a repository of several skills, whose own report lists no findings.
  summary?: string
  findingCount?: number
  // Its number among its owner's reports (INS-0001), when it has one.
  reportNo?: number | null
}>()

const findingTotal = computed(() => props.findingCount ?? props.report.issues.length)

const recommendation = computed(() => props.report.risk_assessment.recommendation)
const score = computed(() => props.report.risk_assessment.score)
const severity = computed(() => props.report.risk_assessment.severity)

const counts = computed(() => {
  const result: Record<Severity, number> = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 }
  for (const issue of props.report.issues) result[issue.severity]++
  return SEVERITIES.map(level => ({ severity: level, count: result[level] })).filter(({ count }) => count > 0)
})

const topFinding = computed(() =>
  [...props.report.issues].sort((a, b) =>
    SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] || b.confidence - a.confidence)[0]
)

const summaryLine = computed(() => {
  if (props.summary) return props.summary
  const top = topFinding.value
  if (!top) {
    return props.report.mcp_server
      ? 'None of the checks of its registry entry flagged anything.'
      : 'None of the analyzers flagged anything in this skill.'
  }
  const title = findingTitle(top)
  const explanation = top.explanation?.trim()
  if (!explanation || explanation === title) return `Top finding: ${title}.`
  return `Top finding: ${title}. ${/[.!?]$/.test(explanation) ? explanation : `${explanation}.`}`
})
</script>

<template>
  <section
    aria-labelledby="verdict-heading"
    class="surface border-2 border-inverted"
  >
    <div class="flex flex-wrap justify-between gap-x-10 gap-y-6 p-5 sm:p-7">
      <div class="flex min-w-0 flex-[1_1_28rem] flex-col gap-2.5">
        <span class="eyebrow text-muted">
          Inspection report<template v-if="reportLabel(reportNo)"> · {{ reportLabel(reportNo) }}</template>
        </span>
        <slot />
      </div>
      <div class="flex flex-col items-start justify-center gap-4 sm:items-end">
        <h1
          id="verdict-heading"
          class="m-0"
        >
          <span class="sr-only">Verdict: </span>
          <VerdictStamp
            :recommendation="recommendation"
            size="lg"
            tilt
            class="my-1"
          />
        </h1>
        <p
          class="m-0 font-mono text-sm text-muted"
          role="meter"
          aria-label="Risk score"
          aria-valuemin="0"
          aria-valuemax="100"
          :aria-valuenow="score"
        >
          Risk <b class="text-3xl font-medium text-highlighted tabular-nums">{{ score }}</b> / 100 · {{ SEVERITY_LABEL[severity] }}
        </p>
      </div>
    </div>

    <div class="flex flex-wrap gap-x-10 gap-y-4 border-t border-default px-5 py-4 sm:px-7">
      <div class="flex min-w-0 flex-[2_1_24rem] flex-col gap-1">
        <span class="eyebrow text-muted">{{ RECOMMENDATION_MEANING[recommendation] }}</span>
        <p class="m-0 text-[15px] text-highlighted text-pretty">
          {{ summaryLine }}
        </p>
      </div>
      <div class="flex min-w-0 flex-[1_1_16rem] flex-col gap-2">
        <span class="eyebrow text-muted">
          {{ findingTotal }} finding{{ findingTotal === 1 ? '' : 's' }}
        </span>
        <template v-if="counts.length">
          <div
            aria-hidden="true"
            class="flex h-2.5"
          >
            <span
              v-for="{ severity: level, count } in counts"
              :key="level"
              :class="SEVERITY_CLASSES[level].dot"
              :style="{ flexGrow: count }"
            />
          </div>
          <p class="m-0 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[13px] text-muted">
            <span
              v-for="{ severity: level, count } in counts"
              :key="level"
              :class="SEVERITY_CLASSES[level].ink"
            >{{ count }} {{ SEVERITY_LABEL[level].toLowerCase() }}</span>
          </p>
        </template>
        <p
          v-else
          class="m-0 text-sm text-muted"
        >
          Nothing to review.
        </p>
      </div>
    </div>
  </section>
</template>
