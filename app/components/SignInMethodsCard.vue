<script setup lang="ts">
// How the signed-in user signs in: a password, GitHub (backend/app/auth/github_sign_in.py). Linking
// GitHub here only adds a way to sign in: scanning private repositories is connected separately.
const { session, user } = useAuth()
const route = useRoute()
const { data: methods, refresh, error: loadError } = useSignInMethods()

const unlinking = ref(false)
const errorMessage = ref('')
const notice = computed(() => {
  if (route.query.github === 'linked') return { color: 'success' as const, title: 'GitHub linked', text: 'You can now sign in with GitHub too.' }
  if (route.query.github === 'signed_up') {
    return {
      color: 'success' as const,
      title: 'Your account was made with GitHub',
      text: 'Signing in with GitHub gives no access to your repositories. To inspect private ones, connect GitHub below and choose which.'
    }
  }
  return null
})
const githubError = computed(() => typeof route.query.github_error === 'string' ? route.query.github_error : '')

// An account made with GitHub sets a password from the reset email "Forgot password?" sends.
const emailing = ref(false)
const emailed = ref(false)
async function emailPasswordLink() {
  emailing.value = true
  errorMessage.value = ''
  try {
    await $fetch('/api/auth/forgot', { method: 'POST', body: { email: user.value?.email } })
    emailed.value = true
  } catch (err) {
    errorMessage.value = apiErrorMessage(err, 'Couldn’t send the email')
  } finally {
    emailing.value = false
  }
}

async function unlink() {
  unlinking.value = true
  errorMessage.value = ''
  try {
    await $fetch('/api/account/sign-in-methods/github', { method: 'DELETE' })
    await refresh()
  } catch (err) {
    errorMessage.value = apiErrorMessage(err, 'Couldn’t unlink GitHub')
  } finally {
    unlinking.value = false
  }
}
</script>

<template>
  <UCard
    v-if="methods && (methods.github_available || methods.github)"
  >
    <div class="flex flex-col gap-4">
      <div class="flex flex-col gap-1">
        <h3 class="sheet-title text-highlighted">
          Sign in with GitHub
        </h3>
        <p class="text-sm text-muted">
          A way to sign in without your password. It gives this server no access to your repositories.
        </p>
      </div>

      <UAlert
        v-if="notice"
        :color="notice.color"
        variant="subtle"
        icon="i-lucide-check-circle-2"
        :title="notice.title"
        :description="notice.text"
      />
      <UAlert
        v-if="githubError || errorMessage || loadError"
        color="error"
        variant="subtle"
        icon="i-lucide-circle-alert"
        :title="githubError || errorMessage || 'Couldn’t load your sign-in methods'"
      />

      <div
        v-if="methods.github"
        class="flex flex-wrap items-center justify-between gap-3"
      >
        <span class="flex items-center gap-2 text-sm text-highlighted">
          <UIcon
            name="i-simple-icons-github"
            class="size-4"
          />
          <span class="font-medium">@{{ methods.github.login }}</span>
          <span class="text-muted">· linked <NuxtTime
            :datetime="methods.github.linked_at * 1000"
            relative
          /></span>
        </span>
        <UButton
          v-if="methods.password"
          color="neutral"
          variant="ghost"
          :loading="unlinking"
          @click="unlink"
        >
          Unlink
        </UButton>
      </div>
      <p
        v-if="methods.github && !methods.password"
        class="text-sm text-muted"
      >
        GitHub is how you sign in, so it can’t be unlinked until you set a password.
        <template v-if="!session?.email_enabled">
          Ask an admin of this server for a link to set one.
        </template>
        <template v-else-if="emailed">
          A link to set one is on its way to {{ user?.email }}.
        </template>
      </p>
      <UButton
        v-if="methods.github && !methods.password && session?.email_enabled && !emailed"
        color="neutral"
        variant="outline"
        icon="i-lucide-mail"
        class="self-start"
        :loading="emailing"
        @click="emailPasswordLink"
      >
        Email me a link to set a password
      </UButton>
      <UButton
        v-if="!methods.github && methods.github_available"
        to="/api/auth/github/start?intent=link"
        external
        color="neutral"
        variant="outline"
        icon="i-simple-icons-github"
        class="self-start"
      >
        Link GitHub
      </UButton>
    </div>
  </UCard>
</template>
