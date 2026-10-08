<script setup lang="ts">
// Inskect's mark: the paper tag hung on goods that passed inspection, with its eyelet and a check.
// The tag takes the current colour; the eyelet and check are punched through to `hole`.
withDefaults(defineProps<{ hole?: string }>(), { hole: 'var(--ui-bg)' })
</script>

<template>
  <svg
    viewBox="0 0 40 40"
    fill="none"
    aria-hidden="true"
  >
    <path
      d="M14 6h20a2 2 0 0 1 2 2v24a2 2 0 0 1-2 2H14L4 20z"
      fill="currentColor"
    />
    <circle
      cx="11"
      cy="20"
      r="2.6"
      :fill="hole"
    />
    <path
      d="M17.5 20.4l4 4 8-8.8"
      :stroke="hole"
      stroke-width="3"
      stroke-linecap="square"
    />
  </svg>
</template>
