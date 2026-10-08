<script setup lang="ts">
// One setting on the backoffice's settings page: what it is on the left, its control on the right
// (below it on a phone, unless it's inline: a switch keeps to the right), and anything that follows
// from it underneath.
defineProps<{ label: string, description?: string, labelFor?: string, inline?: boolean }>()
</script>

<template>
  <div class="flex flex-col gap-3 py-5 first:pt-0 last:pb-0">
    <div
      class="flex gap-3 sm:gap-8"
      :class="inline ? 'flex-row items-start justify-between' : 'flex-col sm:flex-row sm:items-start sm:justify-between'"
    >
      <div class="flex min-w-0 flex-col gap-1">
        <component
          :is="labelFor ? 'label' : 'p'"
          :for="labelFor"
          class="font-semibold text-highlighted"
        >
          {{ label }}
        </component>
        <p
          v-if="description || $slots.description"
          class="text-sm text-muted"
        >
          <slot name="description">
            {{ description }}
          </slot>
        </p>
      </div>
      <div
        class="flex shrink-0 items-center gap-2"
        :class="inline ? 'justify-end' : 'flex-wrap sm:justify-end'"
      >
        <slot />
      </div>
    </div>
    <slot name="below" />
  </div>
</template>
