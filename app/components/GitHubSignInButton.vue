<script setup lang="ts">
// "Continue with GitHub" on the sign-in and sign-up pages, when this server's GitHub App is set up
// (backend/app/auth/github_sign_in.py); and what went wrong, when GitHub sent the visitor back here.
const { session } = useAuth()
const route = useRoute()

const shown = computed(() => !!session.value?.features?.github && !session.value?.needs_setup)
const error = computed(() => typeof route.query.github_error === 'string' ? route.query.github_error : '')
</script>

<template>
  <UAlert
    v-if="error"
    color="error"
    variant="subtle"
    icon="i-lucide-circle-alert"
    :title="error"
  />
  <template v-if="shown">
    <div
      class="flex items-center gap-3 text-xs text-dimmed"
      aria-hidden="true"
    >
      <span class="flex-1 border-t border-default" />
      or
      <span class="flex-1 border-t border-default" />
    </div>
    <UButton
      to="/api/auth/github/start?intent=sign_in"
      external
      color="neutral"
      variant="outline"
      size="lg"
      icon="i-simple-icons-github"
      block
    >
      Continue with GitHub
    </UButton>
  </template>
</template>
