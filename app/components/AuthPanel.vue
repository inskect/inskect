<script setup lang="ts">
defineProps<{
  eyebrow: string
  title: string
  lead: string
}>()
</script>

<template>
  <UContainer class="py-16 sm:py-24">
    <div class="mx-auto flex max-w-md flex-col gap-7">
      <div class="flex flex-col gap-3">
        <p class="eyebrow text-brand-ink">
          {{ eyebrow }}
        </p>
        <h1 class="display text-4xl text-highlighted sm:text-5xl">
          {{ title }}
        </h1>
        <p class="text-[15px] text-muted">
          {{ lead }}
        </p>
      </div>

      <div class="surface flex flex-col gap-4 border-t-[3px] border-t-brand p-5 sm:p-6">
        <slot />
      </div>

      <div
        v-if="$slots.footer"
        class="flex flex-col gap-2 text-sm text-muted"
      >
        <slot name="footer" />
      </div>
    </div>
  </UContainer>
</template>
