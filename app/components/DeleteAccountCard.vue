<script setup lang="ts">
// Deleting the account and everything of the user's (backend/app/accounts.py), with their password.
const { onSessionChange } = useAuth()

const confirming = ref(false)
const password = ref('')
// An account made with GitHub has no password: a recent sign-in stands in for it.
const { data: methods } = useSignInMethods()
const hasPassword = computed(() => methods.value?.password !== false)
const deleting = ref(false)
const errorMessage = ref('')

function close() {
  confirming.value = false
  password.value = ''
  errorMessage.value = ''
}

async function remove() {
  deleting.value = true
  errorMessage.value = ''
  try {
    await $fetch('/api/account', { method: 'DELETE', body: { password: password.value } })
    await onSessionChange()
    await navigateTo('/login')
  } catch (err) {
    errorMessage.value = apiErrorMessage(err, 'Couldn’t delete your account')
  } finally {
    deleting.value = false
  }
}
</script>

<template>
  <UCard :ui="{ root: 'border-error ring-error/40' }">
    <div class="flex flex-col gap-4">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="flex flex-col gap-1">
          <h3 class="sheet-title text-highlighted">
            Delete account
          </h3>
          <p class="text-sm text-muted">
            Deletes your account and everything of yours on this server: your inspections and their
            reports, shared links and badges, your Claude key, API tokens and GitHub connection. The
            activity log keeps what happened, without your email.
          </p>
          <AccountDeletionNotice />
        </div>
        <UButton
          v-if="!confirming"
          color="error"
          variant="outline"
          icon="i-lucide-trash-2"
          @click="confirming = true"
        >
          Delete account
        </UButton>
      </div>
      <form
        v-if="confirming"
        class="flex flex-col gap-4 bg-muted p-4 ring ring-default"
        @submit.prevent="remove"
      >
        <p class="text-sm font-medium text-highlighted">
          This can’t be undone. Download any report you want to keep first.
        </p>
        <UFormField
          v-if="hasPassword"
          label="Your password"
        >
          <PasswordInput
            id="account-delete-password"
            v-model="password"
            autocomplete="current-password"
            autofocus
            class="w-full sm:max-w-sm"
            required
          />
        </UFormField>
        <p
          v-else
          class="text-sm text-muted"
        >
          You sign in with GitHub, without a password: this works within 10 minutes of signing in.
          If it’s been longer, sign out and in again with GitHub.
        </p>
        <UAlert
          v-if="errorMessage"
          color="error"
          variant="subtle"
          :title="errorMessage"
        />
        <div class="flex flex-wrap gap-2">
          <UButton
            type="submit"
            color="error"
            icon="i-lucide-trash-2"
            :loading="deleting"
            :disabled="hasPassword && !password"
          >
            Delete my account
          </UButton>
          <UButton
            color="neutral"
            variant="ghost"
            @click="close"
          >
            Cancel
          </UButton>
        </div>
      </form>
    </div>
  </UCard>
</template>
