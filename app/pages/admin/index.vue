<script setup lang="ts">
import type { Overview } from '../../../shared/types/backoffice'

useSeoMeta({ title: 'Backoffice — Inskect' })

const { data: overview, error } = await useFetch<Overview>('/api/admin/overview', { key: 'admin-overview' })

const scanTiles = computed(() => {
  const scans = overview.value?.scans
  if (!scans) return []
  return [
    { label: 'Rejected', value: scans.do_not_install, dot: 'bg-critical' },
    { label: 'Review first', value: scans.caution, dot: 'bg-medium' },
    { label: 'Passed', value: scans.safe, dot: 'bg-safe' },
    { label: 'Didn’t run', value: scans.failed, dot: 'bg-accented' }
  ]
})
</script>

<template>
  <div class="flex flex-col gap-6">
    <BackofficeHeader
      title="Overview"
      lead="Who uses this server and what they inspect."
    />

    <UAlert
      v-if="error"
      color="error"
      variant="subtle"
      :title="apiErrorMessage(error, 'Failed to load the overview')"
    />

    <template v-else-if="overview">
      <NoAuthWarning v-if="overview.auth === 'none'" />

      <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <NuxtLink
          v-if="overview.auth === 'accounts'"
          to="/admin/users"
          class="surface flex flex-col gap-1 border-t-[3px] border-t-brand p-5 transition-colors hover:bg-muted"
        >
          <span class="eyebrow text-muted">Users</span>
          <span class="display text-4xl text-highlighted tabular-nums">{{ overview.users.total }}</span>
          <span class="text-xs text-muted">{{ overview.users.new }} new this week · {{ overview.users.admins }} admin{{ overview.users.admins === 1 ? '' : 's' }}<template v-if="overview.users.suspended"> · {{ overview.users.suspended }} suspended</template></span>
        </NuxtLink>
        <NuxtLink
          to="/history"
          class="surface flex flex-col gap-1 border-t-[3px] border-t-brand p-5 transition-colors hover:bg-muted"
        >
          <span class="eyebrow text-muted">Inspections</span>
          <span class="display text-4xl text-highlighted tabular-nums">{{ overview.scans.total }}</span>
          <span class="text-xs text-muted">{{ overview.scans.recent }} this week<template v-if="overview.scans.active"> · {{ overview.scans.active }} running now</template></span>
        </NuxtLink>
        <div
          v-if="overview.auth === 'accounts'"
          class="surface flex flex-col gap-1 p-5"
        >
          <span class="eyebrow text-muted">Sign-up</span>
          <span class="text-lg font-semibold text-highlighted">{{ overview.signup_allowed ? 'Open' : 'Closed' }}</span>
          <NuxtLink
            to="/admin/settings"
            class="text-xs text-muted underline-offset-2 hover:underline"
          >Change in settings</NuxtLink>
        </div>
        <div
          v-if="overview.auth === 'accounts'"
          class="surface flex flex-col gap-1 p-5"
        >
          <span class="eyebrow text-muted">Email</span>
          <span class="text-lg font-semibold text-highlighted">{{ overview.email_enabled ? 'Sending' : 'Not configured' }}</span>
          <NuxtLink
            to="/admin/settings"
            class="text-xs text-muted underline-offset-2 hover:underline"
          >{{ overview.email_enabled ? 'Reset emails are on' : 'How to set it up' }}</NuxtLink>
        </div>
      </div>

      <HealthPanel :health="overview.health" />

      <section
        aria-labelledby="verdicts-heading"
        class="sheet flex flex-col gap-4 p-5 sm:p-6"
      >
        <h2
          id="verdicts-heading"
          class="sheet-title text-highlighted"
        >
          Verdicts
        </h2>
        <div class="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div
            v-for="tile in scanTiles"
            :key="tile.label"
            class="flex flex-col gap-1"
          >
            <span class="flex items-center gap-2 text-sm text-muted">
              <span
                class="size-2"
                :class="tile.dot"
              />
              {{ tile.label }}
            </span>
            <span class="font-mono text-2xl font-semibold text-highlighted tabular-nums">{{ tile.value }}</span>
          </div>
        </div>
      </section>

      <section
        aria-labelledby="activity-heading"
        class="sheet flex flex-col gap-2 p-5 sm:p-6"
      >
        <div class="flex items-center justify-between gap-3">
          <h2
            id="activity-heading"
            class="sheet-title text-highlighted"
          >
            Recent activity
          </h2>
          <ULink
            to="/admin/activity"
            class="text-sm font-semibold text-brand-ink"
          >
            All activity →
          </ULink>
        </div>
        <ActivityList :entries="overview.recent_activity" />
      </section>
    </template>
  </div>
</template>
