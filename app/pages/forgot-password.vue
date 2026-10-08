<script setup lang="ts">
const { session } = useAuth()

useSeoMeta({ title: 'Forgot password — Inskect' })

const email = ref('')
const submitting = ref(false)
const sent = ref(false)
const errorMessage = ref('')

async function submit() {
  submitting.value = true
  errorMessage.value = ''
  try {
    await $fetch('/api/auth/forgot', { method: 'POST', body: { email: email.value.trim() } })
    sent.value = true
  } catch (err) {
    errorMessage.value = apiErrorMessage(err, 'Failed to request a reset email')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AuthPanel
    eyebrow="Password reset"
    title="Forgot your password?"
    lead="Enter the email you sign in with, and we’ll send you a link to choose a new password."
  >
    <UAlert
      v-if="session && !session.email_enabled"
      color="neutral"
      variant="subtle"
      icon="i-lucide-mail-x"
      title="This server doesn’t send email"
      description="Ask an admin of this server for a password reset link."
    />
    <UAlert
      v-else-if="sent"
      color="success"
      variant="subtle"
      icon="i-lucide-mail-check"
      title="Check your inbox"
      :description="`If ${email.trim()} has an account here, a reset link is on its way. It works once, for 24 hours.`"
    />
    <form
      v-else
      class="flex flex-col gap-4"
      @submit.prevent="submit"
    >
      <UFormField label="Email">
        <UInput
          id="forgot-email"
          v-model="email"
          type="email"
          autocomplete="email"
          size="lg"
          class="w-full"
          required
          autofocus
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
        :disabled="!email.trim()"
      >
        Send reset link
      </UButton>
    </form>

    <template #footer>
      <p>
        Remembered it?
        <ULink
          to="/login"
          class="font-semibold text-highlighted underline underline-offset-2"
        >
          Back to sign in
        </ULink>
      </p>
    </template>
  </AuthPanel>
</template>
