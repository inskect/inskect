<script setup lang="ts">
import type { Health } from '../../shared/types/backoffice'

// The backoffice's health panel: the last day's failures, the last error, and where alerts go
// (backend/app/monitoring.py); the monitoring page has the rest.
const props = defineProps<{ health: Health }>()

const RULES: Record<string, string> = {
  failure_rate: 'many inspections failing',
  sign_in_lockouts: 'accounts hitting the sign-in limit'
}

const state = computed(() => {
  const health = props.health
  if (health.failed && health.failed * 2 >= health.finished) return { label: 'Many inspections failing', dot: 'bg-critical' }
  if (health.failed) return { label: 'Some inspections didn’t run', dot: 'bg-medium' }
  return { label: 'No problems', dot: 'bg-safe' }
})

const tiles = computed(() => {
  const health = props.health
  return [
    { label: 'Didn’t run', value: health.failed, note: `of ${health.finished} finished` },
    ...health.events.map(event => ({ label: event.label, value: event.count, note: null }))
  ]
})

const channelText = computed(() => props.health.alert_channels.map(channel => channel === 'webhook' ? 'the webhook' : 'email').join(' and '))
</script>

<template>
  <section
    aria-labelledby="health-heading"
    class="sheet flex flex-col gap-4 p-5 sm:p-6"
  >
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h2
        id="health-heading"
        class="sheet-title text-highlighted"
      >
        Health
        <span class="text-sm font-normal text-muted">· last {{ health.hours }} hours</span>
      </h2>
      <span class="flex items-center gap-2 text-sm font-semibold text-highlighted">
        <span
          class="size-2"
          :class="state.dot"
        />
        {{ state.label }}
      </span>
    </div>

    <UAlert
      v-if="health.proxy_warning"
      color="warning"
      variant="subtle"
      icon="i-lucide-network"
      title="Rate limits are shared by every visitor"
      :description="health.proxy_warning"
    />

    <div class="grid grid-cols-2 gap-4 sm:grid-cols-4">
      <div
        v-for="tile in tiles"
        :key="tile.label"
        class="flex flex-col gap-1"
      >
        <span class="text-sm text-muted">{{ tile.label }}</span>
        <span class="font-mono text-2xl font-semibold text-highlighted tabular-nums">{{ tile.value }}</span>
        <span
          v-if="tile.note"
          class="text-xs text-dimmed"
        >{{ tile.note }}</span>
      </div>
    </div>

    <div
      v-if="health.last_error"
      class="flex flex-col gap-1 bg-muted p-3 ring ring-default"
    >
      <span class="flex flex-wrap items-center gap-x-2 text-xs text-muted">
        <span class="font-semibold">Last failed inspection</span>
        <span :title="formatDate(health.last_error.at)">
          <NuxtTime
            :datetime="health.last_error.at * 1000"
            relative
          />
        </span>
        <NuxtLink
          v-if="health.last_error.scan_id"
          :to="`/scan/${health.last_error.scan_id}`"
          class="underline-offset-2 hover:underline"
        >View the report</NuxtLink>
      </span>
      <code class="font-mono text-xs break-words whitespace-pre-wrap text-highlighted">{{ health.last_error.message || 'No message' }}</code>
    </div>

    <div class="flex flex-wrap items-center justify-between gap-3 border-t border-default pt-4">
      <p
        v-if="health.alert_channels.length"
        class="text-sm text-muted"
      >
        Alerts go to {{ channelText }}.
        <template v-if="health.last_alert">
          The last one, {{ RULES[health.last_alert.rule ?? ''] ?? health.last_alert.title ?? health.last_alert.rule }},
          <NuxtTime
            :datetime="health.last_alert.at * 1000"
            relative
          />.
        </template>
      </p>
      <p
        v-else
        class="text-sm text-muted"
      >
        Alerts aren’t set up: set <code class="font-mono text-xs">INSKECT_ALERT_WEBHOOK_URL</code> or
        <code class="font-mono text-xs">INSKECT_ALERT_EMAIL</code> to hear about failures as they happen.
      </p>
      <ULink
        to="/admin/monitoring"
        class="text-sm font-semibold text-brand-ink"
      >
        Monitoring →
      </ULink>
    </div>
  </section>
</template>
