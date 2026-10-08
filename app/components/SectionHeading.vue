<script setup lang="ts">
// A report's section heading: its number (§2), a condensed title, and an aside on the right, over
// an ink rule. The `id` is for the section's aria-labelledby.
defineProps<{ id: string, number?: string | number, title: string, aside?: string }>()
</script>

<template>
  <div class="flex flex-wrap items-baseline gap-x-3.5 gap-y-1 border-b-2 border-inverted pb-2.5">
    <span
      v-if="number !== undefined"
      class="font-mono text-sm text-muted"
    >§{{ number }}</span>
    <h2
      :id="id"
      class="display text-3xl text-highlighted sm:text-4xl"
    >
      {{ title }}
    </h2>
    <span
      v-if="aside || $slots.aside"
      class="ml-auto text-sm text-muted"
    ><slot name="aside">{{ aside }}</slot></span>
  </div>
</template>
