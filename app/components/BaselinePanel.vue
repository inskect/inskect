<script setup lang="ts">
import type { BaselineDownload, ScanReport } from '../../shared/types/scan'

const props = withDefaults(defineProps<{
  scanId: string
  report: ScanReport
  // One skill of several shows its suppressed findings; the baseline downloads for the whole scan.
  downloadable?: boolean
  activeCount?: number
  // The whole scan's: which baseline applied, and the one the skill ships, if any.
  applied?: ScanReport['applied_baseline']
  shipped?: ScanReport['shipped_baseline']
}>(), { downloadable: true, activeCount: undefined, applied: undefined, shipped: undefined })

const suppressedBy = computed(() => {
  if (props.applied === 'shipped') return 'the skill’s own baseline'
  return props.applied === 'uploaded' ? 'your baseline' : 'the baseline'
})

const active = computed(() => props.activeCount ?? props.report.issues.length)

const suppressed = computed(() => props.report.suppressed ?? [])
const showSuppressed = ref(false)

const reason = ref('')
const downloading = ref(false)
const downloadError = ref('')

// The baseline lists every active finding as accepted, with the reason given (or skillspector's
// default). Scanning again with it suppresses exactly those findings.
async function download() {
  downloading.value = true
  downloadError.value = ''
  try {
    const { filename, content } = await $fetch<BaselineDownload>(`/api/scan/${props.scanId}/baseline`, {
      query: reason.value.trim() ? { reason: reason.value.trim() } : undefined
    })
    const url = URL.createObjectURL(new Blob([content], { type: 'application/yaml' }))
    const link = Object.assign(document.createElement('a'), { href: url, download: filename })
    link.click()
    URL.revokeObjectURL(url)
  } catch (err) {
    downloadError.value = apiErrorMessage(err, 'Couldn’t download the baseline')
  } finally {
    downloading.value = false
  }
}
</script>

<template>
  <section
    aria-labelledby="baseline-title"
    class="surface flex flex-col gap-4 px-4 py-4 sm:px-5"
  >
    <h2
      id="baseline-title"
      class="font-semibold text-highlighted"
    >
      Baseline
    </h2>

    <UAlert
      v-if="shipped"
      :color="shipped.applied ? 'warning' : 'neutral'"
      variant="subtle"
      :icon="shipped.applied ? 'i-lucide-shield-alert' : 'i-lucide-file-check'"
      :title="shipped.applied ? 'The skill’s own baseline was applied' : 'The skill ships a baseline, not applied'"
    >
      <template #description>
        <template v-if="shipped.applied">
          Its author wrote the <code class="font-mono text-xs">.skillspector-baseline.yaml</code> it ships,
          so the findings it suppresses are theirs to accept: review them below.
        </template>
        <template v-else-if="shipped.problem">
          It couldn’t be used: {{ shipped.problem }}. Every finding counts.
        </template>
        <template v-else-if="applied === 'uploaded'">
          Your baseline file was used instead.
        </template>
        <template v-else>
          Every finding counts. To apply it, inspect again with “Use the baseline the skill ships”, under
          More options.
        </template>
      </template>
    </UAlert>

    <div
      v-if="suppressed.length"
      class="flex flex-col gap-2"
    >
      <button
        type="button"
        class="flex cursor-pointer items-center gap-2 self-start text-sm text-default"
        :aria-expanded="showSuppressed"
        @click="showSuppressed = !showSuppressed"
      >
        <UIcon
          :name="showSuppressed ? 'i-lucide-chevron-down' : 'i-lucide-chevron-right'"
          class="size-4 text-muted"
        />
        {{ suppressed.length }} finding{{ suppressed.length === 1 ? '' : 's' }} suppressed by {{ suppressedBy }}, not counted in the score
      </button>
      <ul
        v-if="showSuppressed"
        class="flex flex-col"
      >
        <li
          v-for="finding in suppressed"
          :key="findingKey(finding)"
          class="flex flex-col gap-0.5 border-t border-muted py-2.5 text-sm"
        >
          <p class="flex flex-wrap items-baseline gap-x-2">
            <span class="font-medium text-highlighted">{{ findingTitle(finding) }}</span>
            <span class="font-mono text-xs text-muted">{{ finding.id }} · {{ findingLocation(finding) }}</span>
          </p>
          <p class="text-muted">
            {{ finding.suppression_reason }}
          </p>
        </li>
      </ul>
    </div>

    <form
      v-if="report.generated_baseline && downloadable"
      class="flex flex-col gap-2"
      @submit.prevent="download"
    >
      <p class="text-sm text-muted">
        Accept this inspection’s {{ active }} active finding{{ active === 1 ? '' : 's' }}:
        inspect again with the file as its baseline, and only new findings count.
        Changes to the files or a new skillspector version bring them back.
      </p>
      <div class="flex flex-wrap items-center gap-2">
        <UInput
          v-model="reason"
          placeholder="Reason, for example “Reviewed with the security team”"
          aria-label="Reason recorded in the baseline"
          maxlength="500"
          class="min-w-0 flex-1 sm:max-w-md"
          :ui="{ base: 'rounded-none' }"
        />
        <UButton
          type="submit"
          label="Download baseline"
          icon="i-lucide-download"
          color="neutral"
          variant="outline"
          :loading="downloading"
        />
      </div>
      <p
        v-if="downloadError"
        class="text-sm text-critical-ink"
      >
        {{ downloadError }}
      </p>
    </form>
  </section>
</template>
