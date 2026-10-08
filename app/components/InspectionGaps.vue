<script setup lang="ts">
import type { InspectionGaps } from '~~/shared/utils/coverage'

const props = defineProps<{ gaps: InspectionGaps }>()

// Past this, a group's locations hide behind "and N more".
const SHOWN_LOCATIONS = 8
const expanded = ref(new Set<string>())

const filesLine = computed(() => {
  const { totalFiles, fullyInspected, partiallyInspected, uninspected } = props.gaps
  const parts = [`${fullyInspected} of ${totalFiles} file${totalFiles === 1 ? '' : 's'} fully inspected`]
  if (partiallyInspected) parts.push(`${partiallyInspected} partly`)
  if (uninspected) parts.push(`${uninspected} not at all`)
  return parts.join(', ')
})

function toggle(reason: string) {
  const next = new Set(expanded.value)
  if (next.has(reason)) next.delete(reason)
  else next.add(reason)
  expanded.value = next
}
</script>

<template>
  <section
    aria-labelledby="inspection-gaps-title"
    class="surface flex flex-col gap-3 px-4 py-4 sm:px-5"
  >
    <div class="flex items-start gap-3">
      <UIcon
        :name="gaps.significant ? 'i-lucide-scan-eye' : 'i-lucide-info'"
        class="mt-0.5 size-[18px] shrink-0"
        :class="gaps.significant ? 'text-medium-ink' : 'text-muted'"
      />
      <div class="flex min-w-0 flex-col gap-0.5">
        <h2
          id="inspection-gaps-title"
          class="font-semibold text-highlighted"
        >
          {{ gaps.significant ? 'Not fully inspected' : 'Inspected, with minor gaps' }}
        </h2>
        <p class="text-sm text-muted">
          {{ filesLine }}.<template v-if="gaps.significant">
            Findings may be missing for the parts listed below.
          </template>
        </p>
      </div>
    </div>

    <ul class="flex flex-col">
      <li
        v-for="group in gaps.groups"
        :key="group.reason"
        class="flex flex-col gap-1.5 border-t border-muted py-3"
      >
        <p class="flex flex-wrap items-baseline gap-x-2 text-sm">
          <span
            class="font-medium"
            :class="group.minor ? 'text-default' : 'text-medium-ink'"
          >{{ group.label }}</span>
          <span class="font-mono text-xs text-muted">{{ group.locations.length }}</span>
        </p>
        <p
          v-if="group.message"
          class="text-sm text-muted"
        >
          {{ group.message }}
        </p>
        <p class="flex flex-wrap gap-x-3 gap-y-1 font-mono text-xs text-muted">
          <span
            v-for="location in expanded.has(group.reason) ? group.locations : group.locations.slice(0, SHOWN_LOCATIONS)"
            :key="`${location.path}:${location.line}`"
          ><UntrustedText :value="gapLocationLabel(location)" /></span>
          <button
            v-if="group.locations.length > SHOWN_LOCATIONS"
            type="button"
            class="cursor-pointer font-sans font-medium text-highlighted underline underline-offset-2"
            :aria-expanded="expanded.has(group.reason)"
            @click="toggle(group.reason)"
          >
            {{ expanded.has(group.reason) ? 'Show fewer' : `and ${group.locations.length - SHOWN_LOCATIONS} more` }}
          </button>
        </p>
      </li>
    </ul>
  </section>
</template>
