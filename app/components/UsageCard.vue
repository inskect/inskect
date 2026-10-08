<script setup lang="ts">
import type { UsageResponse } from '../../shared/types/settings'

const { data: usage } = await useFetch<UsageResponse>('/api/account/usage')

const limits = computed(() => {
  const value = usage.value
  if (!value?.quotas_apply) return []
  return [
    { label: 'Scans in the last 24 hours', used: value.scans_today, limit: value.daily_scan_quota },
    { label: 'Scans in progress', used: value.active_scans, limit: value.concurrent_scan_quota }
  ].filter(row => row.limit !== null) as { label: string, used: number, limit: number }[]
})

const aiUsage = computed(() => usage.value?.ai_usage.scans ? usage.value.ai_usage : null)
</script>

<template>
  <section
    v-if="usage && (usage.scans_paused || limits.length || aiUsage)"
    aria-labelledby="usage-heading"
    class="flex flex-col gap-3"
  >
    <h2
      id="usage-heading"
      class="eyebrow text-muted"
    >
      Usage
    </h2>
    <UCard>
      <div class="flex flex-col gap-4">
        <p
          v-if="limits.length"
          class="text-sm text-muted"
        >
          How many inspections you can start on this server. Deleting one doesn't give it back.
        </p>

        <UAlert
          v-if="usage.scans_paused"
          color="warning"
          variant="subtle"
          icon="i-lucide-circle-pause"
          title="New inspections are paused on this server"
          description="An admin has paused inspections for everyone. Your history is still here."
        />

        <div
          v-for="row in limits"
          :key="row.label"
          class="flex flex-col gap-1.5"
        >
          <div class="flex items-baseline justify-between gap-3 text-sm">
            <span class="text-default">{{ row.label }}</span>
            <span class="font-mono text-xs text-muted tabular-nums">{{ Math.min(row.used, row.limit) }} of {{ row.limit }}</span>
          </div>
          <UProgress
            :model-value="Math.min(row.used, row.limit)"
            :max="row.limit"
            :color="row.used >= row.limit ? 'warning' : 'neutral'"
            size="sm"
          />
        </div>

        <div
          v-if="aiUsage"
          class="flex flex-col gap-0.5 text-sm"
        >
          <div class="flex items-baseline justify-between gap-3">
            <span class="text-default">AI review tokens, last {{ aiUsage.days }} days</span>
            <span class="font-mono text-xs text-muted tabular-nums">{{ aiUsage.scans }} inspection{{ aiUsage.scans === 1 ? '' : 's' }}</span>
          </div>
          <p class="text-muted">
            {{ formatTokenUsage({ input: aiUsage.input_tokens, output: aiUsage.output_tokens, cached: aiUsage.cached_tokens }) }},
            as your AI provider reported them. Deleted inspections aren't counted.
          </p>
        </div>
      </div>
    </UCard>
  </section>
</template>
