<script setup lang="ts">
defineProps<{
  title: string
  lead?: string
}>()
</script>

<template>
  <div class="flex flex-wrap items-end justify-between gap-4 border-b-2 border-inverted pb-5">
    <div class="flex min-w-0 flex-col gap-2">
      <p class="eyebrow text-muted">
        Backoffice
      </p>
      <h1 class="display text-4xl break-words text-highlighted sm:text-5xl">
        {{ title }}
      </h1>
      <p
        v-if="lead"
        class="text-[15px] text-muted"
      >
        {{ lead }}
      </p>
    </div>
    <slot />
  </div>
</template>
