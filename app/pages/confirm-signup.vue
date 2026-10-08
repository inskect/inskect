<script setup lang="ts">
const route = useRoute()
const { onSessionChange } = useAuth()
const { track } = useAnalytics()

useSeoMeta({ title: 'Finish creating your account — Inskect' })

const token = computed(() => (typeof route.query.token === 'string' ? route.query.token : ''))
const submitting = ref(false)
const errorMessage = ref('')

// A button rather than on load: mail scanners that open links mustn't create the account.
async function submit() {
  submitting.value = true
  errorMessage.value = ''
  try {
    await $fetch('/api/auth/confirm-signup', { method: 'POST', body: { token: token.value } })
    track('Sign Up')
    await onSessionChange()
    await navigateTo('/')
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
    title="Finish creating your account"
    lead="This link works once. Your account is created with the email and password you signed up with, and you’re signed in."
  >
    <UAlert
      v-if="!token"
      color="error"
      variant="subtle"
      icon="i-lucide-link-2-off"
      title="This link is incomplete"
      description="Open the full link you were emailed, or sign up again."
    />
    <form
      v-else
      class="flex flex-col gap-4"
      @submit.prevent="submit"
    >
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
      >
        Create my account
      </UButton>
    </form>

    <template #footer>
      <p>
        Already have an account?
        <ULink
          to="/login"
          class="font-semibold text-highlighted underline underline-offset-2"
        >
          Sign in
        </ULink>
      </p>
    </template>
  </AuthPanel>
</template>
