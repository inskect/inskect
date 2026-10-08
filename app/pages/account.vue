<script setup lang="ts">
const { accounts, user, session } = useAuth()

useSeoMeta({ title: 'Account — Inskect' })

// The file's index, beside it on a wide screen: each card, by its group.
const sectionIndex = computed(() => [
  {
    label: 'Connections',
    items: [
      ...(session.value?.claude_key_available ? [{ id: 'claude-key', label: 'Claude key' }] : []),
      ...(session.value?.features.github ? [{ id: 'github', label: 'GitHub' }] : []),
      { id: 'api-tokens', label: 'API tokens' }
    ]
  },
  {
    label: 'Security',
    items: [
      { id: 'password', label: 'Password' },
      ...(session.value?.features.github ? [{ id: 'sign-in-methods', label: 'Sign-in methods' }] : []),
      { id: 'sessions', label: 'Sign out everywhere' },
      { id: 'delete-account', label: 'Delete account' }
    ]
  }
])

// There's nothing to manage without accounts.
if (!accounts.value) await navigateTo('/')

const current = ref('')
const next = ref('')
const confirm = ref('')
const saving = ref(false)
const errorMessage = ref('')
const saved = ref(false)
// Revoking the API tokens too, when the password changes: yes unless unticked.
const revokeTokens = ref(true)
const revokedWithPassword = ref(false)

const mismatch = computed(() => confirm.value.length > 0 && confirm.value !== next.value)
// The password form opens from its button, and closes once the password is changed.
const changingPassword = ref(false)
// An account made with GitHub has no password to change: it sets one from a reset email.
const { data: signInMethods } = useSignInMethods()
const hasPassword = computed(() => signInMethods.value?.password !== false)

function closePasswordForm() {
  changingPassword.value = false
  current.value = ''
  next.value = ''
  confirm.value = ''
  errorMessage.value = ''
}

async function save() {
  saving.value = true
  errorMessage.value = ''
  saved.value = false
  try {
    await $fetch('/api/auth/password', { method: 'POST', body: { currentPassword: current.value, newPassword: next.value, revokeTokens: revokeTokens.value } })
    revokedWithPassword.value = revokeTokens.value
    closePasswordForm()
    saved.value = true
    if (revokedWithPassword.value) await refreshNuxtData('api-tokens-me')
  } catch (err) {
    errorMessage.value = apiErrorMessage(err, 'Failed to change the password')
  } finally {
    saving.value = false
  }
}

// Every other session ended and every API token revoked: after an account was taken over, nothing
// its intruder holds still works. Asked twice, since it also stops scripts using the tokens.
const confirmingSignOut = ref(false)
const signingOut = ref(false)
const signOutError = ref('')
const signedOut = ref<number | null>(null)

async function signOutEverywhere() {
  signingOut.value = true
  signOutError.value = ''
  try {
    signedOut.value = (await $fetch<{ tokens_revoked: number }>('/api/auth/sign-out-everywhere', { method: 'POST' })).tokens_revoked
    confirmingSignOut.value = false
    await refreshNuxtData('api-tokens-me')
  } catch (err) {
    signOutError.value = apiErrorMessage(err, 'Couldn’t sign out everywhere')
  } finally {
    signingOut.value = false
  }
}
</script>

<template>
  <UContainer class="py-12 sm:py-14">
    <div class="mx-auto flex max-w-5xl flex-col gap-8">
      <div class="flex flex-col gap-2 border-b-2 border-inverted pb-5">
        <p class="eyebrow text-muted">
          Inspector’s file
        </p>
        <h1 class="display text-5xl text-highlighted sm:text-6xl">
          Account
        </h1>
        <p class="flex flex-wrap items-center gap-2 text-[15px] text-muted">
          <span>Signed in as <span class="font-semibold text-highlighted">{{ user?.email }}</span></span>
          <span
            v-if="user?.role === 'admin'"
            class="border border-current px-1.5 font-display text-sm leading-tight font-bold tracking-wider text-brand-ink uppercase"
          >Admin</span>
        </p>
      </div>

      <div class="grid gap-8 lg:grid-cols-[13rem_minmax(0,1fr)] lg:gap-10">
        <nav
          aria-label="Account sections"
          class="flex flex-col gap-5 max-lg:hidden lg:sticky lg:top-[calc(var(--ui-header-height)+2rem)] lg:self-start"
        >
          <div
            v-for="group in sectionIndex"
            :key="group.label"
            class="flex flex-col gap-1"
          >
            <p class="eyebrow text-muted">
              {{ group.label }}
            </p>
            <ul class="m-0 flex list-none flex-col p-0">
              <li
                v-for="item in group.items"
                :key="item.id"
              >
                <a
                  :href="`#${item.id}`"
                  class="flex h-9 items-center border-l-[3px] border-transparent px-3 text-sm font-semibold text-muted transition-colors hover:border-brand hover:text-highlighted"
                >{{ item.label }}</a>
              </li>
            </ul>
          </div>
        </nav>

        <div class="flex min-w-0 flex-col gap-8">
          <UsageCard />

          <section
            aria-labelledby="connections-heading"
            class="flex flex-col gap-3"
          >
            <h2
              id="connections-heading"
              class="eyebrow text-muted"
            >
              Connections
            </h2>
            <ClaudeKeyCard
              v-if="session?.claude_key_available"
              id="claude-key"
              class="scroll-mt-24"
            />
            <UAlert
              v-else-if="user?.role === 'admin'"
              color="neutral"
              variant="subtle"
              icon="i-lucide-key-round"
              title="Saved Claude keys are off on this server"
              description="To let users connect their own Claude key, set INSKECT_SECRET_KEY on the API (generate one with python -m app.secrets_box) and restart it."
            />
            <div
              id="github"
              class="scroll-mt-24"
            >
              <GitHubConnectionCard />
            </div>
            <div
              id="api-tokens"
              class="scroll-mt-24"
            >
              <ApiTokensCard />
            </div>
          </section>

          <section
            aria-labelledby="security-heading"
            class="flex flex-col gap-3"
          >
            <h2
              id="security-heading"
              class="eyebrow text-muted"
            >
              Security
            </h2>
            <UCard
              id="password"
              class="scroll-mt-24"
            >
              <div class="flex flex-col gap-4">
                <div class="flex flex-wrap items-start justify-between gap-3">
                  <div class="flex flex-col gap-1">
                    <h3 class="sheet-title text-highlighted">
                      Password
                    </h3>
                    <p class="text-sm text-muted">
                      {{ hasPassword
                        ? 'Changing it keeps you signed in here, and signs you out everywhere else.'
                        : 'You sign in with GitHub, without a password. Set one from the GitHub card below.' }}
                    </p>
                  </div>
                  <UButton
                    v-if="hasPassword && !changingPassword"
                    color="neutral"
                    variant="outline"
                    icon="i-lucide-key-round"
                    @click="changingPassword = true; saved = false"
                  >
                    Change password
                  </UButton>
                </div>
                <UAlert
                  v-if="saved"
                  color="success"
                  variant="subtle"
                  icon="i-lucide-check-circle-2"
                  title="Password changed"
                  :description="revokedWithPassword ? 'Your other devices are signed out, and your API tokens revoked.' : 'Your other devices are signed out. Your API tokens still work.'"
                />
                <form
                  v-if="changingPassword"
                  class="flex flex-col gap-4 bg-muted p-4 ring ring-default"
                  @submit.prevent="save"
                >
                  <UFormField label="Current password">
                    <PasswordInput
                      id="account-current-password"
                      v-model="current"
                      autocomplete="current-password"
                      autofocus
                      class="w-full"
                      required
                    />
                  </UFormField>
                  <div class="grid gap-4 sm:grid-cols-2">
                    <UFormField
                      label="New password"
                      hint="10+ characters"
                    >
                      <PasswordInput
                        id="account-new-password"
                        v-model="next"
                        autocomplete="new-password"
                        class="w-full"
                        required
                      />
                    </UFormField>
                    <UFormField
                      label="Confirm it"
                      :error="mismatch ? 'The passwords don’t match' : undefined"
                    >
                      <PasswordInput
                        id="account-confirm-password"
                        v-model="confirm"
                        autocomplete="new-password"
                        class="w-full"
                        required
                      />
                    </UFormField>
                  </div>
                  <UCheckbox
                    v-model="revokeTokens"
                    label="Revoke my API tokens too"
                    description="Scripts and CI using them stop working until you give them new ones. Leave it ticked if someone else may have had your password."
                  />
                  <UAlert
                    v-if="errorMessage"
                    color="error"
                    variant="subtle"
                    :title="errorMessage"
                  />
                  <div class="flex flex-wrap gap-2">
                    <UButton
                      type="submit"
                      color="primary"
                      :loading="saving"
                      :disabled="!current || next.length < 10 || next !== confirm"
                    >
                      Change password
                    </UButton>
                    <UButton
                      color="neutral"
                      variant="ghost"
                      @click="closePasswordForm"
                    >
                      Cancel
                    </UButton>
                  </div>
                </form>
              </div>
            </UCard>
            <div
              id="sign-in-methods"
              class="scroll-mt-24"
            >
              <SignInMethodsCard />
            </div>
            <UCard
              id="sessions"
              class="scroll-mt-24"
            >
              <div class="flex flex-col gap-4">
                <div class="flex flex-wrap items-start justify-between gap-3">
                  <div class="flex flex-col gap-1">
                    <h3 class="sheet-title text-highlighted">
                      Sign out everywhere
                    </h3>
                    <p class="text-sm text-muted">
                      Ends every session but this one, and revokes all your API tokens. Use it if someone
                      else may have got into your account.
                    </p>
                  </div>
                  <UButton
                    v-if="!confirmingSignOut"
                    color="neutral"
                    variant="outline"
                    icon="i-lucide-log-out"
                    @click="confirmingSignOut = true; signedOut = null"
                  >
                    Sign out everywhere
                  </UButton>
                </div>
                <UAlert
                  v-if="signedOut !== null"
                  color="success"
                  variant="subtle"
                  icon="i-lucide-check-circle-2"
                  title="Signed out everywhere else"
                  :description="`${signedOut} API token${signedOut === 1 ? '' : 's'} revoked. You're still signed in here.`"
                />
                <div
                  v-if="confirmingSignOut"
                  class="flex flex-col gap-3 bg-muted p-4 ring ring-default"
                >
                  <p class="text-sm text-highlighted">
                    Your other devices will be signed out, and every script or CI job using one of your API
                    tokens will stop working.
                  </p>
                  <UAlert
                    v-if="signOutError"
                    color="error"
                    variant="subtle"
                    :title="signOutError"
                  />
                  <div class="flex flex-wrap gap-2">
                    <UButton
                      color="error"
                      icon="i-lucide-log-out"
                      :loading="signingOut"
                      @click="signOutEverywhere"
                    >
                      Sign out everywhere
                    </UButton>
                    <UButton
                      color="neutral"
                      variant="ghost"
                      @click="confirmingSignOut = false; signOutError = ''"
                    >
                      Cancel
                    </UButton>
                  </div>
                </div>
              </div>
            </UCard>
            <div
              id="delete-account"
              class="scroll-mt-24"
            >
              <DeleteAccountCard />
            </div>
          </section>
        </div>
      </div>
    </div>
  </UContainer>
</template>
