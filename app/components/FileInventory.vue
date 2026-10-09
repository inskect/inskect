<script setup lang="ts">
import type { ScanReport } from '../../shared/types/scan'

const props = defineProps<{
  report: ScanReport
  // For links to the code (see FindingCard).
  target?: string
  skillPath?: string
}>()

defineEmits<{
  'show-file': [file: string]
}>()

const open = ref(false)
const components = computed(() => props.report.components ?? [])
const summaries = computed(() => props.report.structured_summaries ?? [])

const findingsByFile = computed(() => {
  const counts = new Map<string, number>()
  for (const issue of props.report.issues) counts.set(issue.location.file, (counts.get(issue.location.file) ?? 0) + 1)
  return counts
})

// Riskiest first: files with findings, then executables, then by path. A file from a followed
// reference links into its own source.
const rows = computed(() => [...components.value]
  .sort((a, b) =>
    (findingsByFile.value.get(b.path) ?? 0) - (findingsByFile.value.get(a.path) ?? 0)
    || Number(b.executable) - Number(a.executable)
    || a.path.localeCompare(b.path))
  .map(component => ({
    ...component,
    findings: findingsByFile.value.get(component.path) ?? 0,
    href: component.source_url
      ? codeLink(component.source_url, component.path)
      : props.target ? codeLink(props.target, component.path, null, props.skillPath) : null
  })))

const summaryLine = computed(() => {
  const total = components.value.reduce((sum, component) => sum + (component.size_bytes ?? 0), 0)
  const executables = components.value.filter(component => component.executable).length
  const parts = [`${components.value.length} file${components.value.length === 1 ? '' : 's'}`]
  if (executables) parts.push(`${executables} executable`)
  if (total) parts.push(formatBytes(total))
  return parts.join(' · ')
})

// The fields skillspector's own report prints for a structured summary.
const SUMMARY_FIELDS: [string, string][] = [
  ['file', 'File'],
  ['protocol', 'Protocol'],
  ['layout_kind', 'Layout'],
  ['declared_tools', 'Declared tools'],
  ['workflow_nodes', 'Workflow nodes'],
  ['constraints', 'Constraints'],
  ['resources', 'Resources'],
  ['tags', 'Tags']
]

function display(value: unknown): string {
  if (Array.isArray(value)) return value.map(item => (typeof item === 'object' ? JSON.stringify(item) : String(item))).join(', ')
  if (value && typeof value === 'object') return JSON.stringify(value)
  return value === null || value === undefined ? '' : String(value)
}
</script>

<template>
  <section
    aria-labelledby="files-heading"
    class="surface flex flex-col"
  >
    <button
      type="button"
      class="flex cursor-pointer items-center gap-3 px-4 py-4 text-left transition-colors hover:bg-muted sm:px-5"
      :aria-expanded="open"
      @click="open = !open"
    >
      <UIcon
        :name="open ? 'i-lucide-chevron-down' : 'i-lucide-chevron-right'"
        class="size-[18px] shrink-0 text-muted"
      />
      <span class="flex min-w-0 flex-col">
        <span
          id="files-heading"
          class="font-semibold text-highlighted"
        >Files inspected</span>
        <span class="text-sm text-muted">{{ summaryLine }}</span>
      </span>
    </button>

    <div
      v-if="open"
      class="flex flex-col gap-5 border-t border-muted px-4 pt-3 pb-5 sm:px-5"
    >
      <div class="overflow-x-auto">
        <table class="w-full min-w-[34rem] text-sm">
          <thead>
            <tr class="text-left text-xs text-muted">
              <th class="py-2 pr-3 font-medium">
                File
              </th>
              <th class="py-2 pr-3 font-medium">
                Type
              </th>
              <th class="py-2 pr-3 text-right font-medium">
                Lines
              </th>
              <th class="py-2 pr-3 text-right font-medium">
                Size
              </th>
              <th class="py-2 text-right font-medium">
                Findings
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="component in rows"
              :key="component.path"
              class="border-t border-muted"
            >
              <td class="py-2 pr-3">
                <span class="flex min-w-0 items-center gap-2">
                  <UIcon
                    v-if="component.executable"
                    name="i-lucide-file-terminal"
                    class="size-4 shrink-0 text-medium-ink"
                    title="Executable"
                  />
                  <ULink
                    v-if="component.href"
                    :to="component.href"
                    target="_blank"
                    class="font-mono text-xs break-all text-highlighted hover:underline"
                  ><UntrustedText :value="component.path" /></ULink>
                  <span
                    v-else
                    class="font-mono text-xs break-all text-highlighted"
                  ><UntrustedText :value="component.path" /></span>
                  <span
                    v-if="component.executable"
                    class="sr-only"
                  >(executable)</span>
                </span>
              </td>
              <td class="py-2 pr-3 text-muted">
                {{ component.type }}
              </td>
              <td class="py-2 pr-3 text-right font-mono text-xs text-muted tabular-nums">
                {{ component.lines ?? '—' }}
              </td>
              <td class="py-2 pr-3 text-right font-mono text-xs text-muted tabular-nums">
                {{ component.size_bytes === null ? '—' : formatBytes(component.size_bytes) }}
              </td>
              <td class="py-2 text-right">
                <button
                  v-if="component.findings"
                  type="button"
                  class="cursor-pointer font-mono text-xs font-medium text-highlighted underline underline-offset-2"
                  :title="`Show only the findings in ${component.path}`"
                  @click="$emit('show-file', component.path)"
                >
                  {{ component.findings }}
                </button>
                <span
                  v-else
                  class="font-mono text-xs text-dimmed"
                >0</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div
        v-if="summaries.length"
        class="flex flex-col gap-3"
      >
        <h3 class="font-semibold text-highlighted">
          Structured skill summary
        </h3>
        <dl
          v-for="(summary, index) in summaries"
          :key="index"
          class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1 text-sm"
        >
          <dt class="font-mono text-xs text-muted">
            {{ summary.id ?? 'SSR' }}
          </dt>
          <dd class="text-highlighted">
            {{ summary.message }}
          </dd>
          <template
            v-for="[key, label] in SUMMARY_FIELDS"
            :key="key"
          >
            <template v-if="display(summary[key])">
              <dt class="text-muted">
                {{ label }}
              </dt>
              <dd class="font-mono text-xs break-all text-default">
                {{ display(summary[key]) }}
              </dd>
            </template>
          </template>
        </dl>
      </div>
    </div>
  </section>
</template>
