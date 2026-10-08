<script setup lang="ts">
// "Saved", beside a setting for a moment after it saves; announced to screen readers.
defineProps<{ show: boolean }>()
</script>

<template>
  <span
    class="inline-flex items-center gap-1 text-sm whitespace-nowrap text-safe-ink transition-opacity duration-300"
    :class="show ? 'opacity-100' : 'opacity-0'"
    aria-live="polite"
  >
    <template v-if="show">
      <UIcon
        name="i-lucide-check"
        class="size-4"
      />
      Saved
    </template>
  </span>
</template>
