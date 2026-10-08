<script setup lang="ts">
const props = defineProps<{
  lines: string[]
  tall?: boolean
  // Shown in place of lines when there are none.
  empty?: string
}>()

const container = ref<HTMLElement>()

watch(() => props.lines.length, () => {
  nextTick(() => {
    const el = container.value
    if (el) el.scrollTop = el.scrollHeight
  })
})

const CATEGORY_PREFIXES: [RegExp, string][] = [
  [/^static_patterns_/, 'Static pattern: '],
  [/^static_/, 'Static: '],
  [/^semantic_/, 'Semantic: '],
  [/^behavioral_/, 'Behavioral: '],
  [/^mcp_/, 'MCP: ']
]

function humanizeStage(name: string): string {
  let label = name
  for (const [pattern, prefix] of CATEGORY_PREFIXES) {
    if (pattern.test(label)) {
      label = prefix + label.replace(pattern, '')
      break
    }
  }
  label = label.replace(/_/g, ' ')
  return label.charAt(0).toUpperCase() + label.slice(1)
}

interface LogLine {
  icon: string
  class: string
  text: string
}

// The panel is always dark, in both themes, so these are fixed shades rather than theme tokens.
function parseLine(line: string): LogLine {
  const stageMatch = line.match(/^(.+) completed$/)
  if (stageMatch) {
    return { icon: 'i-lucide-check', class: 'text-graphite-300', text: humanizeStage(stageMatch[1]!) }
  }
  // Each as the API logs it, and as it did before inspections were called so, for older logs.
  if (line.startsWith('Starting the inspection of') || line.startsWith('Starting scan of')) {
    return { icon: 'i-lucide-play', class: 'text-graphite-50 font-medium', text: line }
  }
  if (line === 'Inspection complete' || line === 'Scan complete') {
    return { icon: 'i-lucide-check-circle-2', class: 'text-green-300 font-medium', text: line }
  }
  if (line.startsWith('Inspection failed:') || line.startsWith('Scan failed:')) {
    return { icon: 'i-lucide-x-circle', class: 'text-red-300 font-medium', text: line }
  }
  if (line.startsWith('WARNING ')) {
    return { icon: 'i-lucide-alert-triangle', class: 'text-amber-300', text: line.slice('WARNING '.length) }
  }
  if (line.startsWith('ERROR ')) {
    return { icon: 'i-lucide-alert-circle', class: 'text-red-300', text: line.slice('ERROR '.length) }
  }
  if (line.startsWith('INFO ')) {
    return { icon: 'i-lucide-info', class: 'text-graphite-400', text: line.slice('INFO '.length) }
  }
  return { icon: 'i-lucide-minus', class: 'text-graphite-400', text: line }
}

const parsedLines = computed(() => props.lines.map(parseLine))
</script>

<template>
  <div
    ref="container"
    class="flex flex-col gap-1 overflow-y-auto bg-code p-4 font-mono text-xs sm:p-5"
    :class="tall ? 'max-h-[26rem]' : 'max-h-64'"
  >
    <p
      v-if="!lines.length && empty"
      class="text-muted"
    >
      {{ empty }}
    </p>
    <div
      v-for="(line, index) in parsedLines"
      :key="index"
      class="flex items-start gap-2"
      :class="line.class"
    >
      <UIcon
        :name="line.icon"
        class="mt-0.5 size-3.5 shrink-0"
      />
      <span class="leading-relaxed break-all whitespace-pre-wrap">{{ line.text }}</span>
    </div>
  </div>
</template>
