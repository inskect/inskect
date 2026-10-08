<script setup lang="ts">
import type { MonitorEventFilter, MonitorEventKind, MonitorEventPage, Monitoring } from '~~/shared/types/backoffice'

// How scans are doing, what raises an alert and where it goes, and every event monitoring kept
// (backend/app/monitoring.py).
useSeoMeta({ title: 'Monitoring — Backoffice — Inskect' })

const WINDOWS = [
  { label: 'Last 24 hours', value: 24 },
  { label: 'Last 7 days', value: 168 },
  { label: 'Last 30 days', value: 720 }
]
const hours = ref(24)
const { data, error, refresh } = await useFetch<Monitoring>('/api/admin/monitoring', {
  key: 'admin-monitoring',
  query: { hours }
})

const FILTERS: { label: string, value: MonitorEventFilter }[] = [
  { label: 'Every event', value: 'all' },
  { label: 'Failed inspections', value: 'failures' },
  { label: 'Sign-in lockouts', value: 'lockouts' },
  { label: 'Alerts sent', value: 'alerts' }
]
const PAGE = 50
const filter = ref<MonitorEventFilter>('all')
const limit = ref(PAGE)
watch(filter, () => {
  limit.value = PAGE
})
const { data: events, error: eventsError, status: eventsStatus, refresh: refreshEvents } = await useFetch<MonitorEventPage>('/api/admin/monitoring/events', {
  key: 'admin-monitoring-events',
  query: { kind: filter, limit }
})
const hasMore = computed(() => (events.value?.items.length ?? 0) < (events.value?.total ?? 0))

const KINDS: Record<MonitorEventKind, { label: string, icon: string, tone: string }> = {
  scan_failed: { label: 'Inspection didn’t run', icon: 'i-lucide-circle-x', tone: 'text-medium-ink' },
  sign_in_locked: { label: 'Sign-in locked', icon: 'i-lucide-lock', tone: 'text-medium-ink' },
  alert_sent: { label: 'Alert sent', icon: 'i-lucide-bell-ring', tone: 'text-brand-ink' }
}

const ruleTitles = computed(() => Object.fromEntries((data.value?.rules ?? []).map(rule => [rule.name, rule.title])))

function eventMessage(kind: MonitorEventKind, message: string | null): string {
  if (kind === 'alert_sent') return ruleTitles.value[message ?? ''] ?? message ?? ''
  if (kind === 'sign_in_locked') return 'An account hit its limit of failed sign-ins'
  return message ?? ''
}

const tiles = computed(() => {
  const health = data.value?.health
  if (!health) return []
  const share = health.finished ? Math.round((health.failed / health.finished) * 100) : 0
  return [
    { label: 'Inspections finished', value: health.finished, note: null },
    { label: 'Failed', value: health.failed, note: health.finished ? `${share}% of finished` : null }
  ]
})

const testing = ref(false)
const testResult = ref<{ ok: boolean, text: string } | null>(null)
async function sendTest() {
  testing.value = true
  testResult.value = null
  try {
    const { channels } = await $fetch<{ channels: string[] }>('/api/admin/alerts/test', { method: 'POST' })
    testResult.value = { ok: true, text: `Sent to ${channels.map(channel => channel === 'webhook' ? 'the webhook' : 'email').join(' and ')}.` }
  } catch (err) {
    testResult.value = { ok: false, text: apiErrorMessage(err, 'Couldn’t send the test alert') }
  } finally {
    testing.value = false
  }
}

function reload() {
  return Promise.all([refresh(), refreshEvents()])
}
</script>

<template>
  <div class="flex flex-col gap-6">
    <BackofficeHeader
      title="Monitoring"
      lead="How inspections are doing, what raises an alert, and where alerts go."
    >
      <div class="flex items-center gap-2">
        <USelect
          v-model="hours"
          :items="WINDOWS"
          aria-label="Time window"
          class="w-40"
        />
        <UButton
          icon="i-lucide-refresh-cw"
          color="neutral"
          variant="outline"
          aria-label="Refresh"
          @click="reload"
        />
      </div>
    </BackofficeHeader>

    <UAlert
      v-if="error"
      color="error"
      variant="subtle"
      :title="apiErrorMessage(error, 'Failed to load monitoring')"
    />

    <template v-else-if="data">
      <section
        aria-label="Counts"
        class="surface grid grid-cols-2 gap-4 p-5 sm:grid-cols-3 sm:p-6 lg:grid-cols-5"
      >
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
      </section>

      <section
        v-if="data.health.last_error"
        aria-labelledby="last-error-heading"
        class="sheet flex flex-col gap-2 p-5 sm:p-6"
      >
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h2
            id="last-error-heading"
            class="sheet-title text-highlighted"
          >
            Last failed inspection
          </h2>
          <span class="flex items-center gap-3 text-sm text-muted">
            <span :title="formatDate(data.health.last_error.at)">
              <NuxtTime
                :datetime="data.health.last_error.at * 1000"
                relative
              />
            </span>
            <NuxtLink
              v-if="data.health.last_error.scan_id"
              :to="`/scan/${data.health.last_error.scan_id}`"
              class="font-semibold text-brand-ink underline-offset-2 hover:underline"
            >View the report →</NuxtLink>
          </span>
        </div>
        <code class="bg-muted p-3 font-mono text-xs break-words whitespace-pre-wrap text-highlighted ring ring-default">{{ data.health.last_error.message || 'No message' }}</code>
      </section>

      <section
        aria-labelledby="rules-heading"
        class="sheet flex flex-col gap-1 p-5 sm:p-6"
      >
        <h2
          id="rules-heading"
          class="sheet-title text-highlighted"
        >
          Alert rules
        </h2>
        <p class="text-sm text-muted">
          Checked as events happen. An alert isn’t repeated until its rule’s wait is over.
        </p>
        <ul class="mt-2 divide-y divide-default">
          <li
            v-for="rule in data.rules"
            :key="rule.name"
            class="flex flex-col gap-1.5 py-4 sm:flex-row sm:items-start sm:justify-between sm:gap-6"
            :class="{ 'opacity-60': !rule.applies }"
          >
            <div class="flex min-w-0 flex-col gap-1">
              <span class="flex items-center gap-2 font-semibold text-highlighted">
                <span
                  class="size-2 shrink-0"
                  :class="!rule.applies ? 'bg-accented' : rule.tripped ? 'bg-critical' : 'bg-safe'"
                />
                {{ rule.title }}
              </span>
              <span class="text-sm text-muted">{{ rule.condition }}. Waits {{ rule.cooldown_minutes }} minutes after alerting.</span>
              <span
                v-if="rule.current"
                class="font-mono text-xs text-dimmed"
              >Now: {{ rule.current }}</span>
            </div>
            <div class="flex shrink-0 flex-col gap-1 text-sm sm:items-end sm:text-right">
              <span
                class="font-semibold"
                :class="!rule.applies ? 'text-muted' : rule.tripped ? 'text-critical-ink' : 'text-highlighted'"
              >
                {{ !rule.applies ? 'With accounts only' : rule.tripped ? 'Tripped' : 'OK' }}
              </span>
              <span
                v-if="rule.last_alert_at"
                class="text-xs text-muted"
                :title="formatDate(rule.last_alert_at)"
              >
                Last alert <NuxtTime
                  :datetime="rule.last_alert_at * 1000"
                  relative
                />
              </span>
              <span
                v-else-if="rule.applies"
                class="text-xs text-muted"
              >Never alerted</span>
              <span
                v-if="rule.quiet_until"
                class="text-xs text-muted"
                :title="formatDate(rule.quiet_until)"
              >
                Quiet until <NuxtTime
                  :datetime="rule.quiet_until * 1000"
                  time-style="short"
                />
              </span>
            </div>
          </li>
        </ul>
      </section>

      <section
        aria-labelledby="channels-heading"
        class="sheet flex flex-col gap-4 p-5 sm:p-6"
      >
        <div class="flex flex-wrap items-center justify-between gap-3">
          <h2
            id="channels-heading"
            class="sheet-title text-highlighted"
          >
            Where alerts go
          </h2>
          <UButton
            v-if="data.health.alert_channels.length"
            color="neutral"
            variant="outline"
            size="sm"
            icon="i-lucide-bell-ring"
            :loading="testing"
            @click="sendTest"
          >
            Send a test alert
          </UButton>
        </div>
        <dl class="grid gap-4 sm:grid-cols-2">
          <div class="flex flex-col gap-1">
            <dt class="eyebrow text-muted">
              Webhook
            </dt>
            <dd class="text-sm text-highlighted">
              <template v-if="data.channels.webhook_host">
                <code class="font-mono text-xs">{{ data.channels.webhook_host }}</code>
                <span class="text-muted"> · the rest of the address is kept secret</span>
              </template>
              <span
                v-else
                class="text-muted"
              >Not set: <code class="font-mono text-xs">INSKECT_ALERT_WEBHOOK_URL</code></span>
            </dd>
          </div>
          <div class="flex flex-col gap-1">
            <dt class="eyebrow text-muted">
              Email
            </dt>
            <dd class="text-sm text-highlighted">
              <template v-if="data.channels.emails.length">
                {{ data.channels.emails.join(', ') }}
                <span
                  v-if="!data.channels.email_ready"
                  class="block text-error"
                >Email isn’t set up on this server, so none is sent.</span>
              </template>
              <span
                v-else
                class="text-muted"
              >Not set: <code class="font-mono text-xs">INSKECT_ALERT_EMAIL</code></span>
            </dd>
          </div>
        </dl>
        <p
          v-if="testResult"
          class="text-sm"
          :class="testResult.ok ? 'text-muted' : 'text-error'"
        >
          {{ testResult.text }}
        </p>
        <p class="text-xs text-dimmed">
          Alerts carry what went wrong, without keys, tokens, email addresses or the links users inspected.
        </p>
      </section>
    </template>

    <section
      aria-labelledby="events-heading"
      class="sheet flex flex-col gap-2 p-5 sm:p-6"
    >
      <div class="flex flex-wrap items-center justify-between gap-3">
        <h2
          id="events-heading"
          class="sheet-title text-highlighted"
        >
          Events
          <span class="text-sm font-normal text-muted">· kept 30 days</span>
        </h2>
        <USelect
          v-model="filter"
          :items="FILTERS"
          aria-label="Show"
          class="w-48"
        />
      </div>
      <UAlert
        v-if="eventsError"
        color="error"
        variant="subtle"
        :title="apiErrorMessage(eventsError, 'Failed to load events')"
      />
      <ul
        v-else-if="events?.items.length"
        class="divide-y divide-default"
      >
        <li
          v-for="item in events.items"
          :key="item.id"
          class="flex items-start gap-3 py-3"
        >
          <UIcon
            :name="KINDS[item.kind]?.icon ?? 'i-lucide-dot'"
            class="mt-0.5 size-4 shrink-0"
            :class="KINDS[item.kind]?.tone"
          />
          <div class="flex min-w-0 flex-1 flex-col gap-0.5">
            <span class="flex flex-wrap items-center gap-x-2 text-sm font-semibold text-highlighted">
              {{ KINDS[item.kind]?.label ?? item.kind }}
              <NuxtLink
                v-if="item.scan_id"
                :to="`/scan/${item.scan_id}`"
                class="text-xs font-normal text-muted underline-offset-2 hover:underline"
              >View the report</NuxtLink>
            </span>
            <span
              v-if="eventMessage(item.kind, item.message)"
              class="font-mono text-xs break-words text-muted"
            >{{ eventMessage(item.kind, item.message) }}</span>
          </div>
          <span
            class="shrink-0 font-mono text-xs whitespace-nowrap text-dimmed"
            :title="formatDate(item.created_at)"
          >
            <NuxtTime
              :datetime="item.created_at * 1000"
              relative
            />
          </span>
        </li>
      </ul>
      <p
        v-else
        class="py-3 text-sm text-muted"
      >
        {{ filter === 'all' ? 'Nothing yet: no inspection has failed, and no alert was sent.' : 'None in the last 30 days.' }}
      </p>
      <div
        v-if="events?.total"
        class="flex items-center justify-between gap-4 pt-2 text-sm text-muted"
      >
        <span>Showing {{ events.items.length }} of {{ events.total }}</span>
        <UButton
          v-if="hasMore"
          color="neutral"
          variant="outline"
          :loading="eventsStatus === 'pending'"
          @click="limit += PAGE"
        >
          Load more
        </UButton>
      </div>
    </section>
  </div>
</template>
