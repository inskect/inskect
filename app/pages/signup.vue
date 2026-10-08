<script setup lang="ts">
const { session, onSessionChange } = useAuth()
const redirect = useAuthRedirect()
const { track } = useAnalytics()

useSeoMeta({
  title: 'Create an account — Inskect',
  description: 'Create an account to scan AI agent skills and MCP servers before you install them, with your scan history kept private to you.'
})

const email = ref('')
const password = ref('')
const confirm = ref('')
const submitting = ref(false)
const errorMessage = ref('')
// With email set up, the account is created from an emailed link: the answer is the same whether or
// not the address already has one.
const sent = ref(false)

const mismatch = computed(() => confirm.value.length > 0 && confirm.value !== password.value)

async function submit() {
  submitting.value = true
  errorMessage.value = ''
  try {
    const result = await $fetch<{ pending?: boolean }>('/api/auth/signup', { method: 'POST', body: { email: email.value.trim(), password: password.value } })
    if (result.pending) {
      sent.value = true
      return
    }
    track('Sign Up')
    await onSessionChange()
    await navigateTo(redirect.value)
  } catch (err) {
    errorMessage.value = apiErrorMessage(err, 'Failed to create your account')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AuthPanel
    eyebrow="Get started"
    title="Create an account"
    :lead="session?.needs_setup
      ? 'No one has an account here yet, so yours becomes the admin of this server.'
      : session?.email_enabled
        ? 'Your scans are private to your account. We’ll email you a link to finish.'
        : 'Your scans are private to your account. It takes a few seconds.'"
  >
    <UAlert
      v-if="session && !session.signup_allowed && !session.needs_setup"
      color="neutral"
      variant="subtle"
      icon="i-lucide-user-lock"
      title="Sign-up is closed on this server"
      description="Ask an admin of this server to add you."
    />
    <UAlert
      v-else-if="sent"
      color="success"
      variant="subtle"
      icon="i-lucide-mail-check"
      title="Check your email to finish creating your account"
      :description="`We sent a message to ${email.trim()}. Its link works once, for 24 hours.`"
    />
    <form
      v-else
      class="flex flex-col gap-4"
      @submit.prevent="submit"
    >
      <UFormField label="Email">
        <UInput
          id="signup-email"
          v-model="email"
          type="email"
          autocomplete="email"
          size="lg"
          class="w-full"
          required
          autofocus
        />
      </UFormField>
      <UFormField
        label="Password"
        description="At least 10 characters."
      >
        <PasswordInput
          id="signup-password"
          v-model="password"
          autocomplete="new-password"
          size="lg"
          class="w-full"
          required
        />
      </UFormField>
      <UFormField
        label="Confirm password"
        :error="mismatch ? 'The passwords don’t match' : undefined"
      >
        <PasswordInput
          id="signup-confirm"
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
        :disabled="!email.trim() || password.length < 10 || password !== confirm"
      >
        Create account
      </UButton>
    </form>
    <GitHubSignInButton v-if="!sent && session?.signup_allowed" />

    <template #footer>
      <p>
        Already have an account?
        <ULink
          :to="{ path: '/login', query: $route.query }"
          class="font-semibold text-highlighted underline underline-offset-2"
        >
          Sign in
        </ULink>
      </p>
    </template>
  </AuthPanel>
</template>
