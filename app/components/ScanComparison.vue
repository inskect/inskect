<script setup lang="ts">
import type { Recommendation, ScanComparison } from '../../shared/types/scan'

const props = defineProps<{
  comparison: ScanComparison
  target: string
  score: number
  recommendation: Recommendation
}>()

const previous = computed(() => props.comparison.previous)
const scoreChange = computed(() => previous.value.risk_score === null ? null : props.score - previous.value.risk_score)
const verdictChanged = computed(() => previous.value.recommendation !== null && previous.value.recommendation !== props.recommendation)
const unchangedReport = computed(() =>
  props.comparison.new_count === 0 && props.comparison.fixed.length === 0 && !scoreChange.value && !verdictChanged.value)
const timeline = computed(() => `/history?target=${encodeURIComponent(props.target)}`)
const fixedOpen = ref(false)
</script>

<template>
  <section
    aria-labelledby="comparison-heading"
    class="surface flex flex-col gap-4 px-4 py-4 sm:px-5"
  >
    <div class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
      <h2
        id="comparison-heading"
        class="font-semibold text-highlighted"
      >
        Since the
        <ULink
          :to="`/scan/${previous.id}`"
          class="underline decoration-dotted underline-offset-4 hover:text-brand-ink"
        >previous inspection</ULink>,
        <NuxtTime
          :datetime="previous.created_at * 1000"
          relative
        />
      </h2>
      <ULink
        :to="timeline"
        class="text-sm font-medium text-primary"
      >
        All inspections of this target →
      </ULink>
    </div>

    <p
      v-if="unchangedReport"
      class="text-sm text-muted"
    >
      Nothing changed: the same findings, the same score and the same verdict.
    </p>
    <template v-else>
      <dl class="flex flex-wrap gap-x-8 gap-y-3 text-sm">
        <div
          v-if="scoreChange !== null"
          class="flex flex-col gap-0.5"
        >
          <dt class="text-muted">
            Risk score
          </dt>
          <dd class="font-mono text-highlighted tabular-nums">
            {{ previous.risk_score }} → {{ score }}
            <span
              v-if="scoreChange"
              :class="scoreChange > 0 ? 'text-critical-ink' : 'text-safe-ink'"
            >({{ scoreChange > 0 ? '+' : '' }}{{ scoreChange }})</span>
          </dd>
        </div>
        <div
          v-if="verdictChanged && previous.recommendation"
          class="flex flex-col gap-0.5"
        >
          <dt class="text-muted">
            Verdict
          </dt>
          <dd class="text-highlighted">
            <span :class="RECOMMENDATION_CLASSES[previous.recommendation].ink">{{ RECOMMENDATION_SHORT_LABEL[previous.recommendation] }}</span>
            →
            <span :class="RECOMMENDATION_CLASSES[recommendation].ink">{{ RECOMMENDATION_SHORT_LABEL[recommendation] }}</span>
          </dd>
        </div>
        <div class="flex flex-col gap-0.5">
          <dt class="text-muted">
            Findings
          </dt>
          <dd class="text-highlighted">
            {{ comparison.new_count }} new · {{ comparison.fixed.length }} fixed · {{ comparison.unchanged_count }} unchanged
          </dd>
        </div>
      </dl>

      <div v-if="comparison.fixed.length">
        <UButton
          color="neutral"
          variant="link"
          size="sm"
          trailing-icon="i-lucide-chevron-down"
          class="px-0"
          :aria-expanded="fixedOpen"
          :ui="{ trailingIcon: fixedOpen ? 'transition-transform rotate-180' : 'transition-transform' }"
          @click="fixedOpen = !fixedOpen"
        >
          {{ fixedOpen ? 'Hide' : 'Show' }} what was fixed
        </UButton>
        <ul
          v-if="fixedOpen"
          class="mt-2 flex flex-col divide-y divide-muted border-t border-muted text-sm"
        >
          <li
            v-for="(finding, index) in comparison.fixed"
            :key="index"
            class="flex flex-wrap items-center gap-x-3 gap-y-1 py-2"
          >
            <SeverityBadge :severity="finding.severity" />
            <span class="font-medium text-highlighted line-through decoration-muted">{{ findingTitle(finding) }}</span>
            <span class="font-mono text-xs text-muted">
              {{ finding.id }} · <UntrustedText :value="`${finding.skill_path ? `${finding.skill_path}/` : ''}${findingLocation(finding)}`" />
            </span>
          </li>
        </ul>
      </div>
    </template>
  </section>
</template>
