<script setup lang="ts">
import type { UserQuotas } from '../../shared/types/backoffice'

// A user's own scan quotas on their backoffice page (PUT /api/admin/users/{id}/quotas): the
// server's, a number of their own, or no limit. Applies from their next scan.
const props = defineProps<{ userId: string, quotas: UserQuotas }>()
const emit = defineEmits<{ saved: [quotas: UserQuotas] }>()

type Choice = 'server' | 'custom' | 'none'

interface QuotaField {
  key: 'daily_scan_quota' | 'concurrent_scan_quota'
  label: string
  server: number | null
  used: string
}

const fields = computed<QuotaField[]>(() => [
  {
    key: 'daily_scan_quota',
    label: 'Inspections per 24 hours',
    server: props.quotas.server_daily_scan_quota,
    used: `${props.quotas.scans_today} used in the last 24 hours`
  },
  {
    key: 'concurrent_scan_quota',
    label: 'In progress at once',
    server: props.quotas.server_concurrent_scan_quota,
    used: `${props.quotas.active_scans} in progress now`
  }
])

const choice = reactive<Record<QuotaField['key'], Choice>>({ daily_scan_quota: 'server', concurrent_scan_quota: 'server' })
const custom = reactive<Record<QuotaField['key'], number | ''>>({ daily_scan_quota: '', concurrent_scan_quota: '' })

function load(quotas: UserQuotas) {
  for (const key of ['daily_scan_quota', 'concurrent_scan_quota'] as const) {
    const value = quotas[key]
    choice[key] = value === null ? 'server' : value === 0 ? 'none' : 'custom'
    custom[key] = value ? value : ''
  }
}
watch(() => props.quotas, load, { immediate: true })

function items(field: QuotaField) {
  return [
    { label: `The server’s (${field.server === null ? 'no limit' : field.server})`, value: 'server' },
    { label: 'Their own', value: 'custom' },
    { label: 'No limit', value: 'none' }
  ]
}

function wanted(key: QuotaField['key']): number | null {
  if (choice[key] === 'server') return null
  if (choice[key] === 'none') return 0
  return custom[key] === '' ? null : custom[key]
}

const valid = computed(() => (['daily_scan_quota', 'concurrent_scan_quota'] as const).every(key =>
  choice[key] !== 'custom' || (typeof custom[key] === 'number' && Number.isInteger(custom[key]) && custom[key] >= 1)
))
const changed = computed(() => (['daily_scan_quota', 'concurrent_scan_quota'] as const).some(key => wanted(key) !== props.quotas[key]))
const hasOwn = computed(() => (['daily_scan_quota', 'concurrent_scan_quota'] as const).some(key => props.quotas[key] !== null))

const saving = ref(false)
const saved = ref(false)
const errorMessage = ref('')

async function save(body?: { daily_scan_quota: number | null, concurrent_scan_quota: number | null }) {
  saving.value = true
  saved.value = false
  errorMessage.value = ''
  try {
    const quotas = await $fetch<UserQuotas>(`/api/admin/users/${props.userId}/quotas`, {
      method: 'PUT',
      body: body ?? { daily_scan_quota: wanted('daily_scan_quota'), concurrent_scan_quota: wanted('concurrent_scan_quota') }
    })
    saved.value = true
    emit('saved', quotas)
  } catch (err) {
    errorMessage.value = apiErrorMessage(err, 'Couldn’t save the quotas')
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section
    aria-labelledby="quotas-heading"
    class="sheet flex flex-col gap-4 p-5 sm:p-6"
  >
    <div class="flex flex-col gap-1">
      <h2
        id="quotas-heading"
        class="sheet-title text-highlighted"
      >
        Inspection quotas
      </h2>
      <p class="text-sm text-muted">
        <template v-if="quotas.applies">
          Give this user more inspections, or fewer, than the
          <ULink
            to="/admin/settings"
            class="font-semibold text-highlighted underline underline-offset-2"
          >server’s quotas</ULink>. It applies from their next inspection.
        </template>
        <template v-else>
          Quotas don’t apply to admins. Anything set here applies if they become a regular user.
        </template>
      </p>
    </div>

    <form
      class="flex flex-col gap-4"
      @submit.prevent="save()"
    >
      <div class="grid gap-4 md:grid-cols-2">
        <div
          v-for="field in fields"
          :key="field.key"
          class="flex flex-col gap-2"
        >
          <label
            :for="`quota-${field.key}`"
            class="text-sm font-semibold text-highlighted"
          >{{ field.label }}</label>
          <div class="flex flex-wrap items-center gap-2">
            <USelect
              :id="`quota-${field.key}`"
              v-model="choice[field.key]"
              :items="items(field)"
              value-key="value"
              class="w-52"
            />
            <UInput
              v-if="choice[field.key] === 'custom'"
              v-model.number="custom[field.key]"
              type="number"
              min="1"
              step="1"
              :aria-label="`${field.label}: their own`"
              class="w-28"
            />
          </div>
          <span
            v-if="quotas.applies"
            class="text-xs text-dimmed"
          >{{ field.used }}</span>
        </div>
      </div>

      <p
        v-if="!valid"
        class="text-sm text-critical-ink"
      >
        Their own quota is a whole number of scans, at least 1. For no limit, choose No limit.
      </p>
      <div class="flex flex-wrap items-center gap-3">
        <UButton
          type="submit"
          color="primary"
          :loading="saving"
          :disabled="!changed || !valid"
        >
          Save quotas
        </UButton>
        <UButton
          v-if="hasOwn"
          color="neutral"
          variant="ghost"
          :disabled="saving"
          @click="save({ daily_scan_quota: null, concurrent_scan_quota: null })"
        >
          Back to the server’s
        </UButton>
        <SettingSaved :show="saved && !changed" />
      </div>
      <UAlert
        v-if="errorMessage"
        color="error"
        variant="subtle"
        :title="errorMessage"
      />
    </form>
  </section>
</template>
