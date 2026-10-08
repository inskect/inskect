<script setup lang="ts">
import type { NuxtError } from '#app'

const props = defineProps<{
  error: NuxtError
}>()

const { site } = useAppConfig()

const statusCode = computed(() => props.error?.statusCode ?? 500)
const isNotFound = computed(() => statusCode.value === 404)
const message = computed(() => {
  if (isNotFound.value) return 'This page does not exist.'
  return props.error?.statusMessage || props.error?.message || 'Something went wrong.'
})

useSeoMeta({ title: `${statusCode.value} — ${site.name}`, robots: NOINDEX })

function goHome() {
  clearError({ redirect: '/' })
}
</script>

<template>
  <UApp>
    <UContainer class="py-24">
      <div class="mx-auto flex max-w-lg flex-col items-start gap-5">
        <p class="eyebrow flex items-center gap-2 text-critical-ink">
          <UIcon
            :name="isNotFound ? 'i-lucide-file-question' : 'i-lucide-shield-alert'"
            class="size-4"
          />
          Error {{ statusCode }}
        </p>
        <h1 class="display text-5xl text-highlighted sm:text-6xl">
          {{ isNotFound ? 'Nothing here' : 'Something broke' }}
        </h1>
        <p class="text-lg text-muted">
          {{ message }}
        </p>
        <UButton
          icon="i-lucide-arrow-left"
          color="primary"
          size="lg"
          class="font-semibold"
          @click="goHome"
        >
          Back home
        </UButton>
      </div>
    </UContainer>
  </UApp>
</template>
