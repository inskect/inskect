<script setup lang="ts">
import type { Finding } from '../../shared/types/scan'

const props = defineProps<{
  finding: Finding
  expanded: boolean
  // The scan's target and, in a repository of several skills, this skill's folder: for links to
  // the code.
  target?: string
  skillPath?: string
}>()

defineEmits<{
  toggle: []
}>()

const title = computed(() => findingTitle(props.finding))
const ruleDocs = computed(() => ruleDocsLink(props.finding.id))
const ruleLabel = computed(() => ruleName(props.finding.id))

// Every place it matched, each linked to its line on the code host when the target is on one. A
// finding in a referenced file links into that file's source instead.
const places = computed(() => {
  const occurrences = props.finding.occurrences?.length ? props.finding.occurrences : [props.finding.location]
  const source = props.finding.transitive_depth && props.finding.source_url ? props.finding.source_url : props.target
  return occurrences.map(place => ({
    label: findingLocation({ ...props.finding, location: { ...place, end_line: place.end_line ?? null } }),
    href: source ? codeLink(source, place.file, place.start_line, props.finding.transitive_depth ? undefined : props.skillPath) : null
  }))
})
const host = computed(() => {
  const href = places.value.find(place => place.href)?.href
  return href ? new URL(href).hostname.replace(/^www\./, '') : null
})

// Evidence, flattened to label/value pairs; reasons (AE1) become their messages.
const evidence = computed(() => {
  const entries: { label: string, value: string }[] = []
  for (const [key, value] of Object.entries(props.finding.evidence ?? {})) {
    if (value === null || value === '' || (Array.isArray(value) && !value.length)) continue
    const label = key.replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase())
    if (Array.isArray(value)) {
      const items = value.map(item => typeof item === 'object' && item ? String((item as { message?: unknown }).message ?? JSON.stringify(item)) : String(item))
      entries.push({ label, value: [...new Set(items)].join(' · ') })
    } else {
      entries.push({ label, value: typeof value === 'object' ? JSON.stringify(value) : String(value) })
    }
  }
  return entries
})
const location = computed(() => findingLocation(props.finding))
// Snippets often open with blank lines around the match; they only push the code out of view.
const snippet = computed(() => props.finding.code_snippet?.replace(/^\s*\n/, '').trimEnd() ?? '')
// `finding` holds the matched text. Skip it when it just repeats the title or the location.
const matched = computed(() => {
  const text = props.finding.finding?.trim()
  if (!text || text === title.value || text.startsWith(props.finding.location.file)) return undefined
  return text
})
</script>

<template>
  <article class="surface overflow-hidden">
    <button
      type="button"
      :aria-expanded="expanded"
      class="grid w-full cursor-pointer grid-cols-[20px_minmax(0,1fr)] items-start gap-x-3.5 gap-y-2 px-4 py-4 text-left transition-colors hover:bg-muted sm:grid-cols-[20px_minmax(0,1fr)_auto] sm:px-5"
      @click="$emit('toggle')"
    >
      <UIcon
        :name="expanded ? 'i-lucide-chevron-down' : 'i-lucide-chevron-right'"
        class="mt-0.5 size-[18px] text-muted"
      />
      <span class="flex min-w-0 flex-col gap-1.5">
        <span class="text-base font-semibold break-words text-highlighted">{{ title }}</span>
        <span class="flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-xs text-muted">
          <span v-if="finding.id">{{ finding.id }}</span>
          <span v-if="finding.category && finding.category !== title">{{ finding.category }}</span>
          <span class="break-all"><UntrustedText :value="location" /><template v-if="places.length > 1"> +{{ places.length - 1 }}</template></span>
        </span>
        <span
          v-if="finding.transitive_depth && finding.source_url"
          class="flex items-center gap-1.5 text-xs text-medium-ink"
        >
          <UIcon
            name="i-lucide-link"
            class="size-3.5 shrink-0"
          />
          <span class="break-all">In a file the skill references{{ finding.transitive_depth > 1 ? ` (${finding.transitive_depth} links away)` : '' }}: {{ finding.source_url }}</span>
        </span>
      </span>
      <span class="flex items-center gap-2.5 max-sm:col-start-2">
        <span
          v-if="finding.change === 'new'"
          class="bg-insp-100 px-1.5 py-0.5 text-xs font-semibold text-insp-900 dark:bg-insp-900/60 dark:text-insp-100"
          title="Not in the previous inspection of this target"
        >New</span>
        <span class="font-mono text-xs whitespace-nowrap text-muted">{{ Math.round(finding.confidence * 100) }}% sure</span>
        <SeverityBadge :severity="finding.severity" />
      </span>
    </button>

    <div
      v-if="expanded"
      class="flex flex-col gap-4 px-4 pb-5 sm:pr-5 sm:pl-[54px]"
    >
      <p
        v-if="finding.explanation && finding.explanation !== title"
        class="text-[15px] leading-relaxed text-default"
      >
        {{ finding.explanation }}
      </p>

      <p
        v-if="finding.intent"
        class="text-sm text-muted"
      >
        <span class="font-semibold text-highlighted">Likely intent:</span> {{ finding.intent }}
      </p>

      <dl class="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-sm">
        <dt class="font-semibold text-highlighted">
          Rule
        </dt>
        <dd class="text-muted">
          <code class="font-mono text-xs text-highlighted">{{ finding.id }}</code><template v-if="ruleLabel">
            {{ ruleLabel }}
          </template><template v-if="ruleDocs">
            · <ULink
              :to="ruleDocs"
              target="_blank"
              class="font-medium text-highlighted underline underline-offset-2"
            >skillspector docs</ULink>
          </template>
        </dd>
        <dt class="font-semibold text-highlighted">
          {{ places.length > 1 ? `Found in ${places.length} places` : 'Found in' }}
        </dt>
        <dd class="flex min-w-0 flex-col gap-0.5">
          <template
            v-for="place in places"
            :key="place.label"
          >
            <ULink
              v-if="place.href"
              :to="place.href"
              target="_blank"
              class="inline-flex items-center gap-1 font-mono text-xs break-all text-highlighted underline underline-offset-2"
            >
              {{ place.label }}
              <UIcon
                name="i-lucide-external-link"
                class="size-3 shrink-0"
              />
            </ULink>
            <span
              v-else
              class="font-mono text-xs break-all text-muted"
            >{{ place.label }}</span>
          </template>
          <span
            v-if="host"
            class="text-xs text-dimmed"
          >Opens on {{ host }}, at the branch the inspection fetched or its default one.</span>
        </dd>
        <template
          v-for="item in evidence"
          :key="item.label"
        >
          <dt class="font-semibold text-highlighted">
            {{ item.label }}
          </dt>
          <dd class="min-w-0 font-mono text-xs break-all text-muted">
            {{ item.value }}
          </dd>
        </template>
      </dl>

      <p
        v-if="matched"
        class="flex min-w-0 flex-col gap-1 text-sm"
      >
        <span class="font-semibold text-highlighted">Matched</span>
        <code class="line-clamp-3 bg-muted px-2.5 py-1.5 font-mono text-xs break-all text-default">{{ matched }}</code>
      </p>

      <figure
        v-if="snippet"
        class="overflow-hidden bg-code"
      >
        <figcaption class="flex justify-between gap-4 border-b border-white/10 px-4 py-2.5 font-mono text-xs text-graphite-400">
          <span class="truncate"><UntrustedText :value="finding.location.file" /></span>
          <span
            v-if="finding.location.start_line"
            class="shrink-0"
          >line {{ finding.location.start_line }}</span>
        </figcaption>
        <pre class="max-h-80 overflow-auto p-4 font-mono text-[13px] leading-relaxed text-graphite-200">{{ snippet }}</pre>
      </figure>

      <div
        v-if="finding.remediation"
        class="grid grid-cols-[18px_minmax(0,1fr)] gap-2.5 bg-safe-tint px-4 py-3.5 ring-1 ring-safe-line"
      >
        <UIcon
          name="i-lucide-check"
          class="mt-0.5 size-[18px] text-safe-ink"
        />
        <div class="flex flex-col gap-1 text-sm">
          <span class="font-semibold text-safe-ink">How to fix</span>
          <span class="leading-relaxed text-highlighted">{{ finding.remediation }}</span>
        </div>
      </div>

      <ul
        v-if="finding.tags.length"
        class="flex flex-wrap gap-1.5"
      >
        <li
          v-for="tag in finding.tags"
          :key="tag"
          class="border border-default px-2 py-0.5 font-mono text-[11px] text-muted"
        >
          {{ tag }}
        </li>
      </ul>
    </div>
  </article>
</template>
