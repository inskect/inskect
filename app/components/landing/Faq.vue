<script setup lang="ts">
// Questions a visitor asks before signing up, answered as this server is set up.
const { session } = useAuth()
const { site } = useAppConfig()

const features = computed(() => session.value?.features)

const inspectionsPerDay = (limit: number) => `${limit} inspection${limit === 1 ? '' : 's'} a day`
const quotaAnswer = computed(() => {
  const daily = features.value?.daily_quota ?? null
  const concurrent = features.value?.concurrent_quota ?? null
  const limits = daily === null && concurrent === null
    ? 'Accounts on this server have no inspection quota.'
    : `Each account can run ${[daily === null ? null : inspectionsPerDay(daily), concurrent === null ? null : `${concurrent} at once`].filter(Boolean).join(', and ')}.`
  const cost = site.costAnswer || 'It’s free and open source; this server’s admin sets its limits.'
  return `${cost} ${limits}`
})

const QUESTIONS = computed(() => [
  {
    question: 'Which agents does it work with?',
    answer: 'Any that load agent skills, a folder with a SKILL.md: Claude Code, Codex and others. It also checks MCP servers listed in the MCP Registry. An inspection reads the skill’s files, so it doesn’t matter which agent will run them.'
  },
  {
    question: 'How far can I trust a verdict?',
    answer: 'It’s a strong first check, not a guarantee. More than 20 analyzers look for known techniques, and the optional AI review reads the skill as a whole; each finding is explained so you can judge it yourself. “Passed” means nothing it knows of was found: read the findings, and the code, before giving a skill access to your machine.'
  },
  { question: 'What does it cost, and how much can I inspect?', answer: quotaAnswer.value },
  {
    question: 'Can I run it myself?',
    answer: `Yes. ${site.name} is free and open source software, under the AGPL-3.0 licence. Run it with Docker Compose on your own server, with accounts or without. Admins get a backoffice with users, an activity log, a health panel, rate limits, quotas and a switch that pauses new inspections, and alerts to Slack, Discord, any webhook or email when inspections fail.`
  }
])
</script>

<template>
  <section
    aria-labelledby="faq-heading"
    class="flex flex-col gap-5"
  >
    <SectionHeading
      id="faq-heading"
      :number="7"
      title="Questions"
    />
    <div class="surface divide-y divide-default">
      <details
        v-for="item in QUESTIONS"
        :key="item.question"
        class="group px-5 sm:px-6"
      >
        <summary class="flex cursor-pointer list-none items-center justify-between gap-4 py-4 font-semibold text-highlighted [&::-webkit-details-marker]:hidden">
          {{ item.question }}
          <UIcon
            name="i-lucide-plus"
            class="size-4 shrink-0 text-muted transition-transform group-open:rotate-45"
            aria-hidden="true"
          />
        </summary>
        <p class="max-w-3xl pb-5 text-sm text-muted text-pretty">
          {{ item.answer }}
        </p>
      </details>
    </div>
  </section>
</template>
