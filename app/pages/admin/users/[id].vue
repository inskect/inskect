<script setup lang="ts">
import type { UserDetail } from '../../../../shared/types/backoffice'
import type { UserRole, UserStatus } from '../../../../shared/types/auth'

const route = useRoute()
const id = route.params.id as string
const { user: me, session } = useAuth()

const { data, error, refresh } = await useFetch<UserDetail>(`/api/admin/users/${id}`, { key: `admin-user-${id}` })
const user = computed(() => data.value?.user)
const isMe = computed(() => user.value?.id === me.value?.id)

useSeoMeta({ title: () => `${user.value?.email ?? 'User'} — Backoffice — Inskect` })

const busy = ref('')
const actionError = ref('')
const notice = ref('')

async function run(action: string, work: () => Promise<unknown>, done?: string) {
  busy.value = action
  actionError.value = ''
  notice.value = ''
  try {
    await work()
    if (done) notice.value = done
    await refresh()
  } catch (err) {
    actionError.value = apiErrorMessage(err, 'That didn’t work')
  } finally {
    busy.value = ''
  }
}

function update(body: { role?: UserRole, status?: UserStatus }, done: string) {
  return run(body.role ? 'role' : 'status', () => $fetch(`/api/admin/users/${id}`, { method: 'PATCH', body }), done)
}

function sendResetEmail() {
  return run('email', () => $fetch(`/api/admin/users/${id}/reset-email`, { method: 'POST' }), `Reset email sent to ${user.value?.email}.`)
}

// A one-time link the admin passes on themselves, for when email isn't set up (or doesn't arrive).
const resetLink = ref<{ url: string, expiresAt: number } | null>(null)
const copied = ref(false)
const copyFailed = ref(false)
const resetLinkEl = useTemplateRef<HTMLElement>('resetLinkEl')

function createResetLink() {
  copied.value = false
  copyFailed.value = false
  return run('link', async () => {
    resetLink.value = await $fetch<{ url: string, expiresAt: number }>(`/api/admin/users/${id}/reset`, { method: 'POST' })
  })
}

async function copyResetLink() {
  if (!resetLink.value) return
  try {
    await navigator.clipboard.writeText(resetLink.value.url)
    copied.value = true
  } catch {
    // No clipboard access (e.g. plain HTTP): select the link so it can be copied by hand.
    copyFailed.value = true
    if (resetLinkEl.value) window.getSelection()?.selectAllChildren(resetLinkEl.value)
  }
}

const confirmingDelete = ref(false)
async function deleteUser() {
  busy.value = 'delete'
  actionError.value = ''
  try {
    await $fetch(`/api/admin/users/${id}`, { method: 'DELETE' })
    await navigateTo('/admin/users')
  } catch (err) {
    actionError.value = apiErrorMessage(err, 'Failed to delete the user')
    confirmingDelete.value = false
  } finally {
    busy.value = ''
  }
}
</script>

<template>
  <div class="flex flex-col gap-6">
    <nav
      aria-label="Breadcrumb"
      class="flex items-center gap-2 text-sm text-muted"
    >
      <ULink
        to="/admin/users"
        class="font-medium text-muted hover:text-highlighted"
      >
        Users
      </ULink>
      <UIcon
        name="i-lucide-chevron-right"
        class="size-3.5 shrink-0"
      />
      <span class="truncate text-highlighted">{{ user?.email ?? 'User' }}</span>
    </nav>

    <UAlert
      v-if="error"
      color="error"
      variant="subtle"
      :title="apiErrorMessage(error, 'Failed to load the user')"
    />

    <template v-else-if="user && data">
      <BackofficeHeader :title="user.email">
        <UserBadges
          :role="user.role"
          :status="user.status"
        />
      </BackofficeHeader>

      <dl class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div class="surface p-4">
          <dt class="eyebrow text-muted">
            Inspections
          </dt>
          <dd class="mt-1 font-mono text-2xl font-semibold text-highlighted tabular-nums">
            {{ user.scan_count }}
          </dd>
        </div>
        <div class="surface p-4">
          <dt class="eyebrow text-muted">
            Last sign-in
          </dt>
          <dd
            class="mt-1 text-sm font-semibold text-highlighted"
            :title="user.last_login_at ? formatDate(user.last_login_at) : undefined"
          >
            <NuxtTime
              v-if="user.last_login_at"
              :datetime="user.last_login_at * 1000"
              relative
            />
            <template v-else>
              Never
            </template>
          </dd>
        </div>
        <div class="surface p-4">
          <dt class="eyebrow text-muted">
            Joined
          </dt>
          <dd
            class="mt-1 text-sm font-semibold text-highlighted"
            :title="formatDate(user.created_at)"
          >
            <NuxtTime
              :datetime="user.created_at * 1000"
              relative
            />
          </dd>
        </div>
        <div class="surface p-4">
          <dt class="eyebrow text-muted">
            Status
          </dt>
          <dd class="mt-1 text-sm font-semibold text-highlighted capitalize">
            {{ user.status }}
          </dd>
        </div>
      </dl>

      <UAlert
        v-if="notice"
        color="success"
        variant="subtle"
        icon="i-lucide-check-circle-2"
        :title="notice"
      />
      <UAlert
        v-if="actionError"
        color="error"
        variant="subtle"
        icon="i-lucide-circle-alert"
        :title="actionError"
      />

      <section
        aria-labelledby="actions-heading"
        class="sheet flex flex-col gap-5 p-5 sm:p-6"
      >
        <h2
          id="actions-heading"
          class="sheet-title text-highlighted"
        >
          Manage
        </h2>

        <p
          v-if="isMe"
          class="text-sm text-muted"
        >
          This is your account. Change your password from
          <ULink
            to="/account"
            class="font-semibold text-highlighted underline underline-offset-2"
          >your account page</ULink>; another admin manages your role and status.
        </p>

        <template v-else>
          <div class="grid gap-4 md:grid-cols-2">
            <div class="flex flex-col gap-2">
              <p class="text-sm font-semibold text-highlighted">
                Role
              </p>
              <p class="text-sm text-muted">
                {{ user.role === 'admin' ? 'Admins see every inspection and run the backoffice.' : 'Users see only their own inspections.' }}
              </p>
              <UButton
                color="neutral"
                variant="outline"
                class="self-start"
                :icon="user.role === 'admin' ? 'i-lucide-shield-minus' : 'i-lucide-shield-plus'"
                :loading="busy === 'role'"
                @click="update({ role: user.role === 'admin' ? 'user' : 'admin' }, user.role === 'admin' ? 'No longer an admin.' : 'Now an admin.')"
              >
                {{ user.role === 'admin' ? 'Make a regular user' : 'Make an admin' }}
              </UButton>
            </div>

            <div class="flex flex-col gap-2">
              <p class="text-sm font-semibold text-highlighted">
                Access
              </p>
              <p class="text-sm text-muted">
                {{ user.status === 'suspended'
                  ? 'Suspended: they can’t sign in. Their inspections stay.'
                  : 'Suspending signs them out everywhere and blocks sign-in until you reactivate them.' }}
              </p>
              <UButton
                :color="user.status === 'suspended' ? 'primary' : 'error'"
                :variant="user.status === 'suspended' ? 'solid' : 'outline'"
                class="self-start"
                :icon="user.status === 'suspended' ? 'i-lucide-user-check' : 'i-lucide-user-x'"
                :loading="busy === 'status'"
                @click="update({ status: user.status === 'suspended' ? 'active' : 'suspended' }, user.status === 'suspended' ? 'Reactivated.' : 'Suspended and signed out.')"
              >
                {{ user.status === 'suspended' ? 'Reactivate' : 'Suspend' }}
              </UButton>
            </div>

            <div class="flex flex-col gap-2">
              <p class="text-sm font-semibold text-highlighted">
                Password
              </p>
              <p class="text-sm text-muted">
                A one-time link, valid for 24 hours, to choose a new password. A new link cancels older ones.
              </p>
              <div class="flex flex-wrap gap-2">
                <UButton
                  v-if="session?.email_enabled"
                  color="neutral"
                  variant="outline"
                  icon="i-lucide-mail"
                  :loading="busy === 'email'"
                  :disabled="user.status === 'suspended'"
                  @click="sendResetEmail"
                >
                  Email a reset link
                </UButton>
                <UButton
                  color="neutral"
                  variant="outline"
                  icon="i-lucide-link"
                  :loading="busy === 'link'"
                  :disabled="user.status === 'suspended'"
                  @click="createResetLink"
                >
                  Copy a reset link
                </UButton>
              </div>
            </div>

            <div class="flex flex-col gap-2">
              <p class="text-sm font-semibold text-highlighted">
                Delete
              </p>
              <p class="text-sm text-muted">
                Removes the account and signs them out. Their inspections stay, visible to admins.
              </p>
              <UButton
                color="error"
                variant="outline"
                icon="i-lucide-trash-2"
                class="self-start"
                @click="confirmingDelete = true"
              >
                Delete user
              </UButton>
            </div>
          </div>
        </template>
      </section>

      <UserQuotasCard
        :user-id="user.id"
        :quotas="data.quotas"
        @saved="refresh()"
      />

      <div class="grid gap-6 xl:grid-cols-2">
        <section
          aria-labelledby="scans-heading"
          class="sheet flex flex-col gap-2 p-5 sm:p-6"
        >
          <h2
            id="scans-heading"
            class="sheet-title text-highlighted"
          >
            Recent inspections
          </h2>
          <p
            v-if="data.ai_usage.scans"
            class="text-sm text-muted"
          >
            AI review used {{ formatTokenUsage({ input: data.ai_usage.input_tokens, output: data.ai_usage.output_tokens, cached: data.ai_usage.cached_tokens }) }}
            tokens across {{ data.ai_usage.scans }} inspection{{ data.ai_usage.scans === 1 ? '' : 's' }} in the last {{ data.ai_usage.days }} days.
          </p>
          <ul
            v-if="data.recent_scans.length"
            class="divide-y divide-default"
          >
            <li
              v-for="scan in data.recent_scans"
              :key="scan.id"
            >
              <NuxtLink
                :to="`/scan/${scan.id}`"
                class="flex items-center justify-between gap-3 py-3 text-sm hover:text-highlighted"
              >
                <span class="flex min-w-0 flex-col gap-0.5">
                  <span class="truncate font-semibold text-highlighted"><UntrustedText :value="splitScanTitle(scan.target).name" /></span>
                  <span
                    v-if="reportLabel(scan.report_no)"
                    class="font-mono text-xs text-muted"
                  >{{ reportLabel(scan.report_no) }}</span>
                </span>
                <VerdictStamp
                  :recommendation="scan.recommendation"
                  :failed="scan.status === 'error'"
                  size="sm"
                />
              </NuxtLink>
            </li>
          </ul>
          <p
            v-else
            class="py-3 text-sm text-muted"
          >
            No inspections yet.
          </p>
        </section>

        <section
          aria-labelledby="history-heading"
          class="sheet flex flex-col gap-2 p-5 sm:p-6"
        >
          <h2
            id="history-heading"
            class="sheet-title text-highlighted"
          >
            Account history
          </h2>
          <ActivityList :entries="data.activity" />
        </section>
      </div>

      <ApiTokensCard :user-id="id" />
    </template>

    <UModal
      :open="!!resetLink"
      title="Password reset link"
      :description="`Send this to ${user?.email ?? 'them'} yourself. It works once, for 24 hours, and cancels any earlier link.`"
      @update:open="(value) => { if (!value) resetLink = null }"
    >
      <template #body>
        <div class="flex flex-col gap-3">
          <code
            ref="resetLinkEl"
            class="block bg-muted p-3 font-mono text-xs break-all text-highlighted select-all"
          >{{ resetLink?.url }}</code>
          <p
            v-if="copyFailed"
            class="text-xs text-warning"
          >
            Couldn’t copy automatically: the link is selected, copy it with Ctrl+C or ⌘C.
          </p>
          <p
            v-if="resetLink"
            class="text-xs text-muted"
          >
            Expires <NuxtTime
              :datetime="resetLink.expiresAt * 1000"
              relative
            />.
          </p>
        </div>
      </template>
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <UButton
            variant="ghost"
            color="neutral"
            @click="resetLink = null"
          >
            Done
          </UButton>
          <UButton
            color="primary"
            :icon="copied ? 'i-lucide-check' : 'i-lucide-copy'"
            @click="copyResetLink"
          >
            {{ copied ? 'Copied' : 'Copy link' }}
          </UButton>
        </div>
      </template>
    </UModal>

    <UModal
      v-model:open="confirmingDelete"
      title="Delete user"
      :description="`Everything of ${user?.email}’s is deleted: their inspections and reports, keys, tokens and connections. The activity log keeps their entries without their email. This can’t be undone.`"
    >
      <template #footer>
        <div class="flex w-full justify-end gap-2">
          <UButton
            variant="ghost"
            color="neutral"
            @click="confirmingDelete = false"
          >
            Cancel
          </UButton>
          <UButton
            color="error"
            icon="i-lucide-trash-2"
            :loading="busy === 'delete'"
            @click="deleteUser"
          >
            Delete
          </UButton>
        </div>
      </template>
    </UModal>
  </div>
</template>
