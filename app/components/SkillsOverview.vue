<script setup lang="ts">
import type { SkillSummary, UnscannedSkill } from '../../shared/types/scan'

const props = defineProps<{ skills: SkillSummary[], unscanned: UnscannedSkill[] }>()

// Riskiest first; failed skills last.
const rows = computed(() =>
  props.skills
    .map((skill, index) => ({ skill, index }))
    .sort((a, b) => (b.skill.risk_assessment?.score ?? -1) - (a.skill.risk_assessment?.score ?? -1))
)
</script>

<template>
  <section
    aria-labelledby="skills-title"
    class="flex flex-col gap-3"
  >
    <div>
      <h2
        id="skills-title"
        class="text-lg font-semibold tracking-tight text-highlighted"
      >
        {{ skills.length }} skills
      </h2>
      <p class="text-sm text-muted">
        Each folder holding a <code class="font-mono text-xs">SKILL.md</code> was inspected as a skill of its own.
      </p>
    </div>

    <ul class="surface flex flex-col overflow-hidden">
      <li
        v-for="{ skill, index } in rows"
        :key="skill.path"
        class="border-t border-muted first:border-t-0"
      >
        <NuxtLink
          v-if="skill.risk_assessment"
          :to="{ query: { skill: String(index) } }"
          class="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 px-4 py-3 transition-colors hover:bg-muted sm:grid-cols-[minmax(0,1fr)_auto_7rem] sm:px-5"
        >
          <span class="flex min-w-0 flex-col gap-0.5">
            <span class="truncate font-semibold text-highlighted"><UntrustedText :value="skill.name" /></span>
            <span class="truncate font-mono text-xs text-dimmed"><UntrustedText :value="skill.path" /></span>
          </span>
          <span
            class="inline-flex justify-self-end px-3 py-1 text-sm font-medium"
            :class="RECOMMENDATION_CLASSES[skill.risk_assessment.recommendation].chip"
          >
            {{ RECOMMENDATION_SHORT_LABEL[skill.risk_assessment.recommendation] }}
          </span>
          <span class="col-span-2 flex items-center gap-2 font-mono text-xs text-muted tabular-nums sm:col-span-1 sm:justify-end">
            {{ skill.risk_assessment.score }}
            · {{ skill.issue_count }} finding{{ skill.issue_count === 1 ? '' : 's' }}
            <UIcon
              v-if="skill.ai_review === 'failed' || skill.ai_review === 'degraded' || skill.execution_successful === false"
              name="i-lucide-scan-eye"
              class="size-3.5 text-medium-ink"
              :title="skill.execution_successful === false ? 'Not fully inspected' : 'AI review didn’t fully run'"
            />
          </span>
        </NuxtLink>
        <div
          v-else
          class="flex flex-col gap-0.5 px-4 py-3 sm:px-5"
        >
          <span class="font-semibold text-highlighted"><UntrustedText :value="skill.name" /> <span class="font-mono text-xs font-normal text-dimmed"><UntrustedText :value="skill.path" /></span></span>
          <span class="text-sm text-critical-ink">Didn’t run: {{ skill.error }}</span>
        </div>
      </li>
    </ul>

    <UAlert
      v-if="unscanned.length"
      color="warning"
      variant="subtle"
      icon="i-lucide-timer-off"
      :title="`${unscanned.length} skill${unscanned.length === 1 ? ' wasn’t' : 's weren’t'} scanned`"
      :description="`${unscanned[0]!.reason}: ${unscanned.map(skill => skill.path).join(', ')}. Scan them one folder at a time.`"
    />
  </section>
</template>
