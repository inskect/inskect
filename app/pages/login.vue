<script setup lang="ts">
const { session, onSessionChange } = useAuth()
const redirect = useAuthRedirect()

// The very first visitor on a server with accounts creates the admin instead of signing in.
const setup = computed(() => !!session.value?.needs_setup)

useSeoMeta({ title: () => (setup.value ? 'Set up — Inskect' : 'Sign in — Inskect') })

const email = ref('')
const password = ref('')
const submitting = ref(false)
const errorMessage = ref('')

async function submit() {
  submitting.value = true
  errorMessage.value = ''
  try {
    await $fetch(setup.value ? '/api/auth/setup' : '/api/auth/login', {
      method: 'POST',
      body: { email: email.value.trim(), password: password.value }
    })
    await onSessionChange()
    await navigateTo(redirect.value)
  } catch (err) {
    errorMessage.value = apiErrorMessage(err, 'Something went wrong')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <AuthPanel
    :eyebrow="setup ? 'First run' : 'Welcome back'"
    :title="setup ? 'Create the admin account' : 'Sign in'"
    :lead="setup
      ? 'This server has accounts turned on and no one has signed up yet. The first account becomes the admin.'
      : 'Sign in to scan skills and see your scan history.'"
  >
    <form
      class="flex flex-col gap-4"
      @submit.prevent="submit"
    >
      <UFormField label="Email">
        <UInput
          id="login-email"
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
        :description="setup ? 'At least 10 characters.' : undefined"
      >
        <template
          v-if="!setup && session?.email_enabled"
          #hint
        >
          <ULink
            to="/forgot-password"
            class="text-xs font-semibold text-brand-ink"
          >
            Forgot password?
          </ULink>
        </template>
        <PasswordInput
          id="login-password"
          v-model="password"
          :autocomplete="setup ? 'new-password' : 'current-password'"
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
        :disabled="!email.trim() || !password"
      >
        {{ setup ? 'Create admin account' : 'Sign in' }}
      </UButton>
    </form>
    <GitHubSignInButton />

    <template
      v-if="!setup"
      #footer
    >
      <p v-if="session?.signup_allowed">
        New here?
        <ULink
          :to="{ path: '/signup', query: $route.query }"
          class="font-semibold text-highlighted underline underline-offset-2"
        >
          Create an account
        </ULink>
      </p>
      <p v-else>
        No account? Ask an admin of this server to add you.
      </p>
      <p v-if="!session?.email_enabled">
        Forgot your password? Ask an admin for a reset link.
      </p>
    </template>
  </AuthPanel>
</template>
