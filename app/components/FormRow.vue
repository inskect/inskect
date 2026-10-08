<script setup lang="ts">
// One numbered field of a form sheet: §1, its label and a hint on the left, the field on the right.
// Stacked on a narrow screen.
defineProps<{ number: string | number, title: string, hint?: string }>()
</script>

<template>
  <div class="grid gap-3 border-b border-muted px-5 py-5 sm:px-7 md:grid-cols-[12rem_minmax(0,1fr)] md:gap-6">
    <div class="flex flex-col gap-1">
      <span class="font-mono text-sm text-brand-ink">§{{ number }}</span>
      <span class="font-semibold text-highlighted">{{ title }}</span>
      <span
        v-if="hint"
        class="text-sm text-muted text-pretty"
      >{{ hint }}</span>
    </div>
    <div class="flex min-w-0 flex-col gap-4">
      <slot />
    </div>
  </div>
</template>
