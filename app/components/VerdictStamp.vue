<script setup lang="ts">
import type { Recommendation } from '../../shared/types/scan'

// An inspection's verdict, as the stamp on its report: Passed, Review first or Rejected, in the
// verdict's ink. Without one yet, a dashed "Inspecting…" stamp, or "Didn’t run" once it `failed`.
// `sm` fits a table row or a list.
const props = withDefaults(defineProps<{
  recommendation: Recommendation | null
  size?: 'sm' | 'md' | 'lg'
  // Set at an angle, as stamped by hand: for a report's own verdict, not for lists.
  tilt?: boolean
  // The inspection ended without a verdict.
  failed?: boolean
}>(), { size: 'md', tilt: false, failed: false })

const SIZES = {
  sm: 'border-2 px-1.5 text-sm leading-tight tracking-wider',
  md: 'stamp text-2xl',
  lg: 'stamp text-4xl sm:text-5xl'
}

const label = computed(() => {
  if (props.recommendation) return RECOMMENDATION_LABEL[props.recommendation]
  return props.failed ? 'Didn’t run' : 'Inspecting…'
})
const ink = computed(() => props.recommendation ? RECOMMENDATION_CLASSES[props.recommendation].ink : 'text-muted')
</script>

<template>
  <span
    class="inline-block shrink-0 font-display font-bold whitespace-nowrap uppercase"
    :class="[SIZES[size], ink, { '-rotate-3': tilt, 'border-dashed': !recommendation, 'outline-dashed': !recommendation && size !== 'sm' }]"
  >{{ label }}</span>
</template>
