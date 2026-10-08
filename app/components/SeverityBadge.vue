<script setup lang="ts">
import type { Severity } from '../../shared/types/scan'

defineProps<{
  severity: Severity
}>()
</script>

<template>
  <span
    class="inline-flex items-center px-2.5 py-1 font-mono text-[11px] font-medium leading-none tracking-wider"
    :class="SEVERITY_CLASSES[severity].chip"
  >
    <slot>{{ severity }}</slot>
  </span>
</template>
