<script setup lang="ts">
// The user's GitHub connection, to scan their private repositories (backend/app/repo_connections.py):
// connecting goes to GitHub and back (server/api/account/connections/github/), which lands here with
// ?connected=github or ?connection_error=….
interface GitHubStatus {
  available: boolean
  manage_url: string | null
  connection: { provider: string, account_name: string, connected_at: number } | null
}

const { data, refresh } = await useFetch<{ github: GitHubStatus }>('/api/account/connections', { key: 'account-connections' })
const github = computed(() => data.value?.github ?? null)
const connection = computed(() => github.value?.connection ?? null)

const route = useRoute()
const notice = ref(route.query.connected === 'github' ? 'Connected. Inspections of your private GitHub repositories now use it.' : '')
const errorMessage = ref(typeof route.query.connection_error === 'string' ? route.query.connection_error : '')
onMounted(() => {
  // Once shown, the message leaves the address, so a reload doesn't show it again.
  if (route.query.connected || route.query.connection_error) {
    navigateTo({ query: { ...route.query, connected: undefined, connection_error: undefined } }, { replace: true })
  }
})

const removing = ref(false)
async function disconnect() {
  removing.value = true
  errorMessage.value = ''
  notice.value = ''
  try {
    await $fetch('/api/account/connections/github', { method: 'DELETE' })
    notice.value = 'Disconnected. Its tokens were deleted from this server and revoked at GitHub.'
    await refresh()
  } catch (err) {
    errorMessage.value = apiErrorMessage(err, 'Failed to disconnect GitHub')
  } finally {
    removing.value = false
  }
}
</script>

<template>
  <UCard
    v-if="github?.available"
  >
    <div class="flex flex-col gap-4">
      <div class="flex flex-col gap-1">
        <div class="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
          <h2 class="sheet-title text-highlighted">
            GitHub
          </h2>
          <span
            class="inline-flex shrink-0 items-center gap-1.5 px-2 py-1 text-xs font-semibold"
            :class="connection ? 'bg-safe-tint text-safe-ink ring-1 ring-safe-line' : 'bg-elevated text-muted ring-1 ring-default'"
          >
            <UIcon
              :name="connection ? 'i-lucide-plug' : 'i-lucide-unplug'"
              class="size-3.5"
            />
            {{ connection ? 'Connected' : 'Not connected' }}
          </span>
        </div>
        <p class="text-sm text-muted">
          Inspect your private repositories: connect GitHub, then choose on GitHub which repositories the
          app may read. It can only read them, and only for your inspections. Their reports stay yours.
        </p>
      </div>

      <p
        v-if="connection"
        class="text-sm text-default"
      >
        Connected as <span class="font-semibold text-highlighted">@{{ connection.account_name }}</span>
        <NuxtTime
          :datetime="connection.connected_at * 1000"
          relative
        />.
      </p>

      <div class="flex flex-wrap gap-2">
        <UButton
          v-if="!connection"
          to="/api/account/connections/github/start"
          external
          color="primary"
          icon="i-simple-icons-github"
        >
          Connect GitHub
        </UButton>
        <template v-else>
          <UButton
            v-if="github.manage_url"
            :to="github.manage_url"
            target="_blank"
            color="neutral"
            variant="outline"
            icon="i-lucide-folder-git-2"
          >
            Choose repositories
          </UButton>
          <UButton
            color="error"
            variant="outline"
            icon="i-lucide-unplug"
            :loading="removing"
            @click="disconnect"
          >
            Disconnect
          </UButton>
        </template>
      </div>

      <UAlert
        v-if="notice"
        color="success"
        variant="subtle"
        icon="i-lucide-check-circle-2"
        :title="notice"
      />
      <UAlert
        v-if="errorMessage"
        color="error"
        variant="subtle"
        icon="i-lucide-circle-alert"
        :title="errorMessage"
      />
    </div>
  </UCard>
</template>
