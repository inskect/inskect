<script setup lang="ts">
// The inspection form, as the home page shows it to anyone who can inspect. Its own chunk, loaded only where
// it's shown (pages/index.vue): the landing page for signed-out visitors carries none of it.
const { data: health } = useHealth()
const online = computed(() => health.value && health.value.status !== 'down')
</script>

<template>
  <UContainer class="flex flex-col gap-16 pt-8 pb-12 sm:pt-10 lg:gap-24">
    <div class="flex flex-col gap-6">
      <p
        v-if="health"
        class="flex items-center gap-2 self-start font-mono text-xs text-muted"
      >
        <span class="relative flex size-2">
          <span
            v-if="online"
            class="absolute inline-flex size-full animate-ping bg-safe opacity-60"
          />
          <span
            class="relative inline-flex size-2"
            :class="online ? 'bg-safe' : 'bg-critical'"
          />
        </span>
        <template v-if="online">
          inskect {{ health.version }} · skillspector {{ health.skillspector_version }} · inspector online
        </template>
        <template v-else>
          inspector offline
        </template>
      </p>

      <!-- The form, and beside it on a wide screen the latest reports. -->
      <div class="flex flex-wrap items-start gap-8">
        <ScanForm class="min-w-0 flex-[999_1_40rem]" />
        <RecentScans class="min-w-0 flex-[1_1_18rem]" />
      </div>
    </div>

    <ScanCoverage />
  </UContainer>
</template>
