<script setup lang="ts">
import type { Severity } from '../../../shared/types/scan'

// A real report, written out rather than loaded: skillspector's own test fixture of a poisoned MCP
// tool, as a scan of it reports (verdict, score, and three of its nine findings). Static, so the
// landing page carries none of the scanner's code.
const FIXTURE = 'https://github.com/NVIDIA/skillspector/blob/main/tests/fixtures/mcp_poisoned_tool/SKILL.md'

const FINDINGS: { severity: Severity, category: string, title: string, explanation: string, line: number }[] = [
  {
    severity: 'HIGH',
    category: 'Prompt injection',
    title: '“ignore previous instructions”',
    explanation: 'Tries to override the agent’s instructions or safety rules.',
    line: 10
  },
  {
    severity: 'HIGH',
    category: 'MCP tool poisoning',
    title: 'Hidden HTML comment in tool metadata',
    explanation: 'Invisible to people, but read by the agent: a place to hide instructions.',
    line: 1
  },
  {
    severity: 'HIGH',
    category: 'MCP tool poisoning',
    title: 'Look-alike letters in a tool name',
    explanation: 'Cyrillic or Greek letters that make a malicious tool pass for a trusted one.',
    line: 1
  }
]
</script>

<template>
  <section
    aria-labelledby="example-heading"
    class="flex flex-col gap-5"
  >
    <SectionHeading
      id="example-heading"
      :number="2"
      title="An actual report"
      aside="skillspector’s own test fixture of a poisoned MCP tool"
    />

    <figure class="surface m-0 flex flex-col">
      <div class="flex flex-wrap items-center justify-between gap-6 border-b border-default p-5 sm:p-6">
        <div class="flex min-w-0 flex-col gap-1.5">
          <span class="eyebrow text-muted">Target</span>
          <a
            :href="FIXTURE"
            class="font-mono text-sm break-all text-highlighted underline-offset-2 hover:underline"
          >NVIDIA/skillspector · tests/fixtures/mcp_poisoned_tool/SKILL.md</a>
        </div>
        <div class="flex items-center gap-7">
          <span class="font-mono text-sm text-muted">Risk <b class="text-3xl text-highlighted">100</b> / 100 · Critical</span>
          <VerdictStamp
            recommendation="DO_NOT_INSTALL"
            tilt
          />
        </div>
      </div>
      <ol class="m-0 list-none p-0">
        <li
          v-for="(finding, index) in FINDINGS"
          :key="finding.title"
          class="grid grid-cols-[2.5rem_minmax(0,1fr)] gap-x-3 gap-y-1.5 border-b border-muted px-5 py-4 sm:grid-cols-[2.5rem_6rem_minmax(0,1fr)_8rem] sm:px-6"
        >
          <span class="font-mono text-sm text-muted">{{ String(index + 1).padStart(2, '0') }}</span>
          <span class="sm:order-none">
            <span
              class="px-1.5 py-0.5 font-mono text-xs font-medium"
              :class="SEVERITY_CLASSES[finding.severity].chip"
            >{{ finding.severity }}</span>
          </span>
          <span class="col-start-2 flex min-w-0 flex-col gap-0.5 sm:col-start-auto">
            <span class="font-semibold text-highlighted">{{ finding.title }}</span>
            <span class="text-sm text-muted">{{ finding.category }} · {{ finding.explanation }}</span>
          </span>
          <span class="col-start-2 font-mono text-sm text-muted sm:col-start-auto sm:text-right">SKILL.md:{{ finding.line }}</span>
        </li>
      </ol>
      <figcaption class="px-5 py-3 text-sm text-muted sm:px-6">
        And six more: “Ignore all safety rules”, privilege escalation (“grant full access”), analysis
        evasion, a YARA match and more tool poisoning.
      </figcaption>
    </figure>
  </section>
</template>
