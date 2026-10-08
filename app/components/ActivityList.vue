<script setup lang="ts">
import type { ActivityEntry } from '~~/shared/types/backoffice'

defineProps<{
  entries: ActivityEntry[]
}>()
</script>

<template>
  <ul
    v-if="entries.length"
    class="divide-y divide-default"
  >
    <li
      v-for="entry in entries"
      :key="entry.id"
      class="flex items-start gap-3 py-3"
    >
      <UIcon
        :name="describeActivity(entry).icon"
        class="mt-0.5 size-4 shrink-0 text-dimmed"
      />
      <div class="min-w-0 flex-1 text-sm">
        <p class="break-words text-default">
          <span class="font-semibold text-highlighted">{{ describeActivity(entry).actor }}</span>
          {{ describeActivity(entry).verb }}
          <NuxtLink
            v-if="describeActivity(entry).target && entry.target_id"
            :to="`/admin/users/${entry.target_id}`"
            class="font-semibold text-highlighted underline-offset-2 hover:underline"
          >{{ describeActivity(entry).target }}</NuxtLink>
          <span
            v-if="describeActivity(entry).detail"
            class="text-muted"
          > · {{ describeActivity(entry).detail }}</span>
        </p>
      </div>
      <span
        class="shrink-0 font-mono text-xs whitespace-nowrap text-dimmed"
        :title="formatDate(entry.created_at)"
      >
        <NuxtTime
          :datetime="entry.created_at * 1000"
          relative
        />
      </span>
    </li>
  </ul>
  <p
    v-else
    class="py-3 text-sm text-muted"
  >
    Nothing yet.
  </p>
</template>
