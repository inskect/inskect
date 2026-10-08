<script setup lang="ts">
// One of the repositories the user's GitHub connection reads, picked to scan: its link becomes the
// scan form's target, so a pick scans exactly as a pasted link does. Listed when first opened, as
// listing takes a call to GitHub per hundred repositories.
interface GitHubRepository {
  full_name: string
  url: string
  private: boolean
  description: string | null
}

defineProps<{ manageUrl: string | null, disabled?: boolean }>()
const url = defineModel<string>({ required: true })

const { data, status, error, execute } = useFetch<{ repositories: GitHubRepository[], truncated: boolean }>(
  '/api/account/connections/github/repositories',
  { key: 'github-repositories', immediate: false, server: false }
)
function load() {
  if (!data.value && status.value !== 'pending') execute()
}

const items = computed(() => (data.value?.repositories ?? []).map(repo => ({
  label: repo.full_name,
  value: repo.url,
  description: repo.description ?? undefined,
  icon: repo.private ? 'i-lucide-lock' : 'i-lucide-book-marked'
})))
// The picked repository's link, or none while what's in the field isn't one of them.
const picked = computed({
  get: () => items.value.some(item => item.value === url.value) ? url.value : undefined,
  set: (value) => { url.value = value ?? '' }
})

const menu = useTemplateRef('menu')
defineExpose({ focus: () => menu.value?.inputRef?.focus() })
</script>

<template>
  <UInputMenu
    ref="menu"
    v-model="picked"
    :items="items"
    value-key="value"
    :filter-fields="['label', 'description']"
    :loading="status === 'pending'"
    placeholder="Search your repositories"
    icon="i-simple-icons-github"
    size="xl"
    variant="none"
    open-on-click
    open-on-focus
    :disabled="disabled"
    :ui="{ base: 'h-12 font-mono text-sm', leadingIcon: 'text-dimmed', content: 'min-w-80', itemDescription: 'font-sans' }"
    @focus="load"
    @update:open="(open: boolean) => open && load()"
  >
    <template #empty>
      <span v-if="status === 'pending'">Listing your repositories…</span>
      <span v-else-if="error">{{ apiErrorMessage(error, 'Couldn’t list your GitHub repositories') }}</span>
      <span v-else-if="data && !data.repositories.length">The app can’t read any of your repositories yet.</span>
      <span v-else>No repository matches.</span>
    </template>
    <template #content-bottom>
      <div class="flex items-center gap-2 border-t border-default px-3 py-2 text-xs text-muted">
        <span class="flex-1">
          <template v-if="data?.truncated">Your {{ data.repositories.length }} most recently pushed. </template>
          Missing one?
          <ULink
            v-if="manageUrl"
            :to="manageUrl"
            target="_blank"
            class="font-medium text-highlighted underline"
          >Choose repositories on GitHub</ULink>
          <template v-else>Give the app access to it on GitHub.</template>
        </span>
        <UButton
          icon="i-lucide-refresh-cw"
          color="neutral"
          variant="ghost"
          size="xs"
          aria-label="List again"
          :loading="status === 'pending'"
          @click="execute()"
        />
      </div>
    </template>
  </UInputMenu>
</template>
