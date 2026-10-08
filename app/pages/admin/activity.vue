<script setup lang="ts">
import type { ActivityPage } from '~~/shared/types/backoffice'

useSeoMeta({ title: 'Activity — Backoffice — Inskect' })

const PAGE = 50
const limit = ref(PAGE)
const { data, error, status } = await useFetch<ActivityPage>('/api/admin/activity', {
  key: 'admin-activity',
  query: { limit }
})
const hasMore = computed(() => (data.value?.items.length ?? 0) < (data.value?.total ?? 0))
</script>

<template>
  <div class="flex flex-col gap-6">
    <BackofficeHeader
      title="Activity"
      lead="Accounts created, roles and suspensions changed, passwords reset, settings changed: who did it and when."
    />

    <UAlert
      v-if="error"
      color="error"
      variant="subtle"
      :title="apiErrorMessage(error, 'Failed to load activity')"
    />
    <section
      v-else
      class="sheet px-5 py-2 sm:px-6"
    >
      <ActivityList :entries="data?.items ?? []" />
    </section>

    <div class="flex items-center justify-between gap-4 text-sm text-muted">
      <span v-if="data">Showing {{ data.items.length }} of {{ data.total }}</span>
      <UButton
        v-if="hasMore"
        color="neutral"
        variant="outline"
        :loading="status === 'pending'"
        @click="limit += PAGE"
      >
        Load more
      </UButton>
    </div>
  </div>
</template>
