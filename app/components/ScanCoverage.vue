<script setup lang="ts">
// What an inspection checks, as a numbered checklist; `number` is its § on the page.
defineProps<{ number?: number }>()
const { site } = useAppConfig()

// Grouped from skillspector's analyzer nodes (static_patterns_*, static_yara, behavioral_*,
// mcp_*, artifact_integrity), so the copy stays true to what an inspection actually runs.
const CHECKS = [
  {
    title: 'Prompt injection',
    description: 'Hidden instructions, anti-refusal tricks, system-prompt leaks and memory poisoning.'
  },
  {
    title: 'Data exfiltration',
    description: 'Reading secrets or agent data and sending it elsewhere, including server-side requests.'
  },
  {
    title: 'Dangerous code',
    description: 'Privilege escalation, tool misuse, unsafe deserialization, malware signatures and code-flow analysis.'
  },
  {
    title: 'Supply chain & MCP',
    description: 'Tampered artifacts, risky dependencies, and MCP tools that are poisoned, over-privileged or change later.'
  }
]
</script>

<template>
  <section
    aria-labelledby="scan-coverage-heading"
    class="flex flex-col gap-5"
  >
    <SectionHeading
      id="scan-coverage-heading"
      :number="number"
      title="What an inspection checks"
    />

    <ul class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <li
        v-for="(check, index) in CHECKS"
        :key="check.title"
        class="surface flex flex-col gap-2 p-5"
      >
        <span class="font-mono text-sm text-brand-ink">☑ {{ String(index + 1).padStart(2, '0') }}</span>
        <h3 class="text-base font-semibold text-highlighted">
          {{ check.title }}
        </h3>
        <p class="text-sm text-muted text-pretty">
          {{ check.description }}
        </p>
      </li>
    </ul>

    <p class="text-sm text-muted">
      Every inspection runs more than 20 static analyzers from
      <ULink
        :to="`https://github.com/${site.scannerRepo}`"
        target="_blank"
        class="font-medium text-highlighted underline underline-offset-2"
      >{{ site.scannerRepo }}</ULink>. AI review adds a semantic read of what the skill is trying
      to do.
    </p>
  </section>
</template>
