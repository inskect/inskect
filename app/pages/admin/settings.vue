<script setup lang="ts">
import type { SettingsResponse } from '~~/shared/types/settings'

useSeoMeta({ title: 'Settings — Backoffice — Inskect' })

const { accounts, session } = useAuth()
const { data: health } = useHealth()
const { data: settingsData } = await useFetch<SettingsResponse>('/api/settings')

// Every change saves the same way: a switch as soon as it's flipped, a field with its Save button
// (shown once it's changed) or Enter. Either says "Saved" beside it for a moment.
type SettingKey = 'signup' | 'pause' | 'quotas' | 'retention'
const saving = ref<SettingKey | null>(null)
const saved = ref<SettingKey | null>(null)
const errors = ref<Partial<Record<SettingKey, string>>>({})
let savedTimer: ReturnType<typeof setTimeout> | undefined

async function save(key: SettingKey, body: Record<string, unknown>, after?: () => Promise<unknown>) {
  saving.value = key
  errors.value = { ...errors.value, [key]: undefined }
  try {
    settingsData.value = await $fetch<SettingsResponse>('/api/settings', { method: 'PUT', body })
    await after?.()
    saved.value = key
    clearTimeout(savedTimer)
    savedTimer = setTimeout(() => {
      saved.value = null
    }, 2500)
  } catch (err) {
    errors.value = { ...errors.value, [key]: apiErrorMessage(err, 'Couldn’t save') }
  } finally {
    saving.value = null
  }
}
onUnmounted(() => clearTimeout(savedTimer))

const setSignup = (allowSignup: boolean) => save('signup', { allowSignup }, () => refreshNuxtData('auth-session'))
const setPaused = (scansPaused: boolean) => save('pause', { scansPaused })

// Quotas: an empty field means no limit.
const dailyQuota = ref<number | ''>('')
const concurrentQuota = ref<number | ''>('')
watch(settingsData, (value) => {
  if (!value) return
  dailyQuota.value = value.daily_scan_quota ?? ''
  concurrentQuota.value = value.concurrent_scan_quota ?? ''
}, { immediate: true })
const quotaValid = (value: number | '') => value === '' || (Number.isInteger(value) && value >= 1)
const quotasChanged = computed(() =>
  (dailyQuota.value === '' ? null : dailyQuota.value) !== (settingsData.value?.daily_scan_quota ?? null)
  || (concurrentQuota.value === '' ? null : concurrentQuota.value) !== (settingsData.value?.concurrent_scan_quota ?? null))
const quotasValid = computed(() => quotaValid(dailyQuota.value) && quotaValid(concurrentQuota.value))

function saveQuotas() {
  if (!quotasChanged.value || !quotasValid.value) return
  return save('quotas', {
    dailyScanQuota: dailyQuota.value === '' ? null : dailyQuota.value,
    concurrentScanQuota: concurrentQuota.value === '' ? null : concurrentQuota.value
  })
}

// Retention: a few common periods, or any number of days.
const RETENTION_PRESETS = [7, 30, 90, 365]
const retentionItems = [
  { label: 'Forever', value: 'forever' },
  ...RETENTION_PRESETS.map(days => ({ label: days === 365 ? '1 year' : `${days} days`, value: String(days) })),
  { label: 'Another number of days', value: 'custom' }
]
const retentionChoice = ref('forever')
const customDays = ref<number | ''>(60)
watch(settingsData, (value) => {
  if (!value) return
  const days = value.scan_retention_days
  if (days === null) {
    retentionChoice.value = 'forever'
  } else if (RETENTION_PRESETS.includes(days)) {
    retentionChoice.value = String(days)
  } else {
    retentionChoice.value = 'custom'
    customDays.value = days
  }
}, { immediate: true })
const retentionDays = computed<number | null>(() => {
  if (retentionChoice.value === 'forever') return null
  if (retentionChoice.value === 'custom') return customDays.value === '' ? Number.NaN : customDays.value
  return Number(retentionChoice.value)
})
const retentionValid = computed(() => retentionDays.value === null || (Number.isInteger(retentionDays.value) && retentionDays.value >= 1))
const retentionChanged = computed(() => retentionDays.value !== (settingsData.value?.scan_retention_days ?? null))
// Saving a shorter period deletes the older scans straight away: say so before.
const retentionDeletes = computed(() => {
  const next = retentionDays.value
  const current = settingsData.value?.scan_retention_days ?? null
  return retentionChanged.value && retentionValid.value && next !== null && (current === null || next < current)
})

function saveRetention() {
  if (!retentionChanged.value || !retentionValid.value) return
  return save('retention', { scanRetentionDays: retentionDays.value })
}

// The server's Claude login, which every Claude CLI scan shares, unless turned off
// (INSKECT_CLAUDE_CLI=false): start it here,
// sign in at Anthropic, and paste the code it shows back.
const claudeSignedIn = computed(() => !!health.value?.claude_cli_available)
const claudeCliAllowed = computed(() => !!health.value?.ai_providers.includes('claude_cli'))
const loginStep = ref<'idle' | 'started' | 'done'>('idle')
const loginUrl = ref('')
const code = ref('')
const loginBusy = ref<'start' | 'complete' | null>(null)
const loginError = ref('')
const loginResult = ref<{ success: boolean, output: string } | null>(null)

async function startLogin() {
  loginBusy.value = 'start'
  loginError.value = ''
  try {
    loginUrl.value = (await $fetch<{ url: string }>('/api/admin/claude-login/start', { method: 'POST' })).url
    loginStep.value = 'started'
  } catch (err) {
    loginError.value = apiErrorMessage(err, 'Couldn’t start the sign-in')
  } finally {
    loginBusy.value = null
  }
}

async function completeLogin() {
  if (!code.value.trim()) return
  loginBusy.value = 'complete'
  loginError.value = ''
  try {
    loginResult.value = await $fetch<{ success: boolean, output: string }>('/api/admin/claude-login/complete', {
      method: 'POST',
      body: { code: code.value.trim() }
    })
    loginStep.value = 'done'
    // Past the health cache, so the new sign-in shows straight away.
    health.value = await $fetch('/api/health', { query: { fresh: 1 } })
  } catch (err) {
    loginError.value = apiErrorMessage(err, 'Couldn’t finish the sign-in')
  } finally {
    loginBusy.value = null
  }
}

function resetLogin() {
  loginStep.value = 'idle'
  loginUrl.value = ''
  code.value = ''
  loginError.value = ''
  loginResult.value = null
}

const STATUS_CLASSES = {
  on: 'bg-safe-tint text-safe-ink ring-1 ring-safe-line',
  off: 'bg-elevated text-muted ring-1 ring-default',
  warn: 'bg-medium-tint text-medium-ink ring-1 ring-medium-line'
}
</script>

<template>
  <div class="flex flex-col gap-8">
    <BackofficeHeader
      title="Settings"
      lead="Who can sign up, how inspections run and how long they're kept, and what this server connects to."
    />

    <div class="flex max-w-3xl flex-col gap-8">
      <NoAuthWarning v-if="!accounts" />

      <section
        v-if="accounts"
        aria-labelledby="access-heading"
        class="flex flex-col gap-3"
      >
        <h2
          id="access-heading"
          class="eyebrow text-muted"
        >
          Access
        </h2>
        <div class="sheet px-5 py-5 sm:px-6">
          <SettingRow
            label="Sign-up"
            inline
            description="Visitors can create their own account from the landing page. Off, admins add users from the Users page."
          >
            <SettingSaved :show="saved === 'signup'" />
            <USwitch
              :model-value="settingsData?.allow_signup ?? false"
              :loading="saving === 'signup'"
              :aria-label="settingsData?.allow_signup ? 'Sign-up is on' : 'Sign-up is off'"
              @update:model-value="setSignup"
            />
            <template #below>
              <UAlert
                v-if="errors.signup"
                color="error"
                variant="subtle"
                :title="errors.signup"
              />
            </template>
          </SettingRow>
        </div>
      </section>

      <section
        aria-labelledby="scans-heading"
        class="flex flex-col gap-3"
      >
        <h2
          id="scans-heading"
          class="eyebrow text-muted"
        >
          Inspections
        </h2>
        <div class="sheet divide-y divide-muted px-5 py-5 sm:px-6">
          <SettingRow
            label="Pause new inspections"
            inline
            description="Refuses new inspections for everyone, admins included, until you resume. Those already running finish."
          >
            <span
              v-if="settingsData?.scans_paused"
              class="inline-flex items-center gap-1.5 px-2 py-1 text-xs font-semibold"
              :class="STATUS_CLASSES.warn"
            >
              <UIcon
                name="i-lucide-circle-pause"
                class="size-3.5"
              />
              Paused
            </span>
            <SettingSaved :show="saved === 'pause'" />
            <USwitch
              :model-value="settingsData?.scans_paused ?? false"
              :loading="saving === 'pause'"
              :aria-label="settingsData?.scans_paused ? 'New inspections are paused' : 'New inspections are allowed'"
              @update:model-value="setPaused"
            />
            <template #below>
              <UAlert
                v-if="errors.pause"
                color="error"
                variant="subtle"
                :title="errors.pause"
              />
            </template>
          </SettingRow>

          <SettingRow
            v-if="accounts"
            label="Quotas per user"
            description="For each signed-in user other than admins. Empty means no limit."
          >
            <template #below>
              <form
                class="flex flex-wrap items-end gap-3"
                @submit.prevent="saveQuotas"
              >
                <UFormField
                  label="Inspections per 24 hours"
                  class="w-44"
                >
                  <UInput
                    id="daily-scan-quota"
                    v-model.number="dailyQuota"
                    type="number"
                    min="1"
                    step="1"
                    placeholder="No limit"
                    class="w-full"
                  />
                </UFormField>
                <UFormField
                  label="In progress at once"
                  class="w-44"
                >
                  <UInput
                    id="concurrent-scan-quota"
                    v-model.number="concurrentQuota"
                    type="number"
                    min="1"
                    step="1"
                    placeholder="No limit"
                    class="w-full"
                  />
                </UFormField>
                <UButton
                  v-if="quotasChanged"
                  type="submit"
                  color="primary"
                  :loading="saving === 'quotas'"
                  :disabled="!quotasValid"
                >
                  Save
                </UButton>
                <SettingSaved :show="saved === 'quotas'" />
              </form>
              <p
                v-if="!quotasValid"
                class="text-sm text-critical-ink"
              >
                A quota is a whole number of inspections, at least 1.
              </p>
              <UAlert
                v-if="errors.quotas"
                color="error"
                variant="subtle"
                :title="errors.quotas"
              />
            </template>
          </SettingRow>

          <SettingRow
            label="Keep reports"
            description="Inspections older than this are deleted from the history automatically. Forever deletes nothing."
            label-for="retention-choice"
          >
            <template #below>
              <form
                class="flex flex-wrap items-end gap-3"
                @submit.prevent="saveRetention"
              >
                <USelect
                  id="retention-choice"
                  v-model="retentionChoice"
                  :items="retentionItems"
                  value-key="value"
                  class="w-56"
                />
                <UInput
                  v-if="retentionChoice === 'custom'"
                  id="retention-days"
                  v-model.number="customDays"
                  type="number"
                  min="1"
                  step="1"
                  aria-label="Days to keep reports"
                  class="w-28"
                >
                  <template #trailing>
                    <span class="text-xs text-muted">days</span>
                  </template>
                </UInput>
                <UButton
                  v-if="retentionChanged"
                  type="submit"
                  :color="retentionDeletes ? 'error' : 'primary'"
                  :loading="saving === 'retention'"
                  :disabled="!retentionValid"
                >
                  Save
                </UButton>
                <SettingSaved :show="saved === 'retention'" />
              </form>
              <p
                v-if="retentionDeletes"
                class="flex items-center gap-1.5 text-sm text-critical-ink"
              >
                <UIcon
                  name="i-lucide-triangle-alert"
                  class="size-4 shrink-0"
                />
                Saving deletes inspections older than {{ retentionDays }} days straight away.
              </p>
              <UAlert
                v-if="errors.retention"
                color="error"
                variant="subtle"
                :title="errors.retention"
              />
            </template>
          </SettingRow>
        </div>
      </section>

      <section
        v-if="claudeCliAllowed || accounts"
        aria-labelledby="integrations-heading"
        class="flex flex-col gap-3"
      >
        <h2
          id="integrations-heading"
          class="eyebrow text-muted"
        >
          Integrations
        </h2>
        <div class="sheet divide-y divide-muted px-5 py-5 sm:px-6">
          <SettingRow
            v-if="claudeCliAllowed"
            label="Claude login"
            description="The server's own Claude sign-in, which every “Claude via this server” review uses. Sign in again when it expires."
          >
            <span
              class="inline-flex items-center gap-1.5 px-2 py-1 text-xs font-semibold"
              :class="claudeSignedIn ? STATUS_CLASSES.on : STATUS_CLASSES.off"
            >
              <UIcon
                :name="claudeSignedIn ? 'i-lucide-circle-check' : 'i-lucide-circle-dashed'"
                class="size-3.5"
              />
              {{ claudeSignedIn ? 'Signed in' : 'Not signed in' }}
            </span>
            <UButton
              v-if="loginStep === 'idle'"
              :color="claudeSignedIn ? 'neutral' : 'primary'"
              :variant="claudeSignedIn ? 'outline' : 'solid'"
              icon="i-lucide-log-in"
              :loading="loginBusy === 'start'"
              @click="startLogin"
            >
              {{ claudeSignedIn ? 'Sign in again' : 'Sign in' }}
            </UButton>
            <template #below>
              <ol
                v-if="loginStep === 'started'"
                class="flex flex-col gap-4 bg-muted p-4 ring ring-default"
              >
                <li class="flex flex-col gap-2">
                  <p class="text-sm font-semibold text-highlighted">
                    1. Sign in at Anthropic
                  </p>
                  <div class="flex flex-wrap items-center gap-2">
                    <UButton
                      :to="loginUrl"
                      target="_blank"
                      icon="i-lucide-external-link"
                      color="neutral"
                      variant="outline"
                    >
                      Open the sign-in page
                    </UButton>
                    <code class="min-w-0 flex-1 truncate font-mono text-xs text-muted">{{ loginUrl }}</code>
                  </div>
                </li>
                <li>
                  <form
                    class="flex flex-col gap-2"
                    @submit.prevent="completeLogin"
                  >
                    <label
                      for="claude-login-code"
                      class="text-sm font-semibold text-highlighted"
                    >2. Paste the code it shows you</label>
                    <div class="flex flex-wrap gap-2">
                      <UInput
                        id="claude-login-code"
                        v-model="code"
                        icon="i-lucide-clipboard-paste"
                        autocomplete="off"
                        class="min-w-48 flex-1"
                      />
                      <UButton
                        type="submit"
                        color="primary"
                        :loading="loginBusy === 'complete'"
                        :disabled="!code.trim()"
                      >
                        Finish
                      </UButton>
                      <UButton
                        color="neutral"
                        variant="ghost"
                        @click="resetLogin"
                      >
                        Cancel
                      </UButton>
                    </div>
                  </form>
                </li>
              </ol>
              <div
                v-if="loginStep === 'done' && loginResult"
                class="flex flex-col gap-2"
              >
                <UAlert
                  :color="loginResult.success ? 'success' : 'error'"
                  variant="subtle"
                  :icon="loginResult.success ? 'i-lucide-circle-check' : 'i-lucide-circle-x'"
                  :title="loginResult.success ? 'Signed in: Claude CLI reviews work again' : 'The sign-in didn’t work'"
                  :actions="[{ label: loginResult.success ? 'Done' : 'Try again', color: 'neutral', variant: 'outline', onClick: resetLogin }]"
                />
                <details v-if="loginResult.output">
                  <summary class="cursor-pointer text-sm text-muted">
                    What the Claude CLI said
                  </summary>
                  <pre class="mt-2 overflow-x-auto bg-elevated p-3 font-mono text-xs">{{ loginResult.output }}</pre>
                </details>
              </div>
              <UAlert
                v-if="loginError"
                color="error"
                variant="subtle"
                :title="loginError"
              />
            </template>
          </SettingRow>

          <SettingRow
            v-if="accounts"
            label="Email"
          >
            <template #description>
              <template v-if="session?.email_enabled">
                Users can reset a forgotten password by email, and you can email them a reset link
                from their page.
              </template>
              <template v-else>
                Off, forgotten passwords go through reset links you copy from a user's page.
              </template>
            </template>
            <span
              class="inline-flex items-center gap-1.5 px-2 py-1 text-xs font-semibold"
              :class="session?.email_enabled ? STATUS_CLASSES.on : STATUS_CLASSES.off"
            >
              <UIcon
                :name="session?.email_enabled ? 'i-lucide-mail-check' : 'i-lucide-mail-x'"
                class="size-3.5"
              />
              {{ session?.email_enabled ? 'Configured' : 'Not configured' }}
            </span>
            <template
              v-if="!session?.email_enabled"
              #below
            >
              <details class="bg-muted px-4 py-3 ring ring-default">
                <summary class="cursor-pointer text-sm font-medium text-highlighted">
                  How to turn it on
                </summary>
                <p class="mt-2 text-sm text-muted">
                  Set these on the API, with your SMTP server's details, and restart it:
                </p>
                <pre class="mt-2 overflow-x-auto bg-default p-3 font-mono text-xs text-highlighted">INSKECT_SMTP_HOST=smtp.example.com
INSKECT_SMTP_PORT=587
INSKECT_SMTP_USERNAME=…
INSKECT_SMTP_PASSWORD=…
INSKECT_MAIL_FROM=Inskect &lt;noreply@example.com&gt;
INSKECT_PUBLIC_URL=https://inskect.example.com</pre>
              </details>
            </template>
          </SettingRow>
        </div>
      </section>
    </div>
  </div>
</template>
