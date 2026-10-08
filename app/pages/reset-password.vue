<script setup lang="ts">
const route = useRoute()
const { onSessionChange } = useAuth()

useSeoMeta({ title: 'Choose a new password — Inskect' })

const token = computed(() => (typeof route.query.token === 'string' ? route.query.token : ''))
const password = ref('')
const confirm = ref('')
const submitting = ref(false)
const errorMessage = ref('')

const mismatch = computed(() => confirm.value.length > 0 && confirm.value !== password.value)

async function submit() {
  submitting.value = true
  errorMessage.value = ''
  try {
    await $fetch('/api/auth/reset', { method: 'POST', body: { token: token.value, password: password.value } })
    await onSessionChange()
    await navigateTo('/')
  } catch (err) {
    errorMessage.value = apiErrorMessage(err, 'Failed to reset the password')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <UContainer class="py-16 sm:py-24">
    <div class="mx-auto flex max-w-md flex-col gap-7">
      <div class="flex flex-col gap-3">
        <p class="eyebrow text-brand-ink">
          Password reset
        </p>
        <h1 class="display text-4xl text-highlighted sm:text-5xl">
          Choose a new password
        </h1>
        <p class="text-[15px] text-muted">
          This link works once. Setting a password signs you in here and out everywhere else, and revokes your API tokens.
        </p>
      </div>

      <UAlert
        v-if="!token"
        color="error"
        variant="subtle"
        icon="i-lucide-link-2-off"
        title="This link is incomplete"
        description="Open the full reset link you were sent, or ask an admin for a new one."
      />

      <form
        v-else
        class="surface flex flex-col gap-4 border-t-[3px] border-t-brand p-5 sm:p-6"
        @submit.prevent="submit"
      >
        <UFormField
          label="New password"
          description="At least 10 characters."
        >
          <PasswordInput
            id="reset-password"
            v-model="password"
            autocomplete="new-password"
            size="lg"
            class="w-full"
            required
            autofocus
          />
        </UFormField>
        <UFormField
          label="Confirm new password"
          :error="mismatch ? 'The passwords don’t match' : undefined"
        >
          <PasswordInput
            id="reset-password-confirm"
            v-model="confirm"
            autocomplete="new-password"
            size="lg"
            class="w-full"
            required
          />
        </UFormField>

        <UAlert
          v-if="errorMessage"
          color="error"
          variant="subtle"
          icon="i-lucide-circle-alert"
          :title="errorMessage"
        />

        <UButton
          type="submit"
          color="primary"
          size="lg"
          block
          :loading="submitting"
          :disabled="password.length < 10 || password !== confirm"
        >
          Set new password
        </UButton>
      </form>
    </div>
  </UContainer>
</template>
