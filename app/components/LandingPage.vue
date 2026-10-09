<script setup lang="ts">
import type { Feature } from './landing/FeatureGrid.vue'

// The home page for signed-out visitors: what the product does, as this server is set up
// (session.features), and where to sign up. Its own chunk, without any of the scanner's code.
const { session } = useAuth()
const { site } = useAppConfig()
// Awaited, so the AI review text rendered on the server is the one the browser shows.
const { data: health } = await useHealth()

const features = computed(() => session.value?.features)
const repoUrl = `https://github.com/${site.repo}`
const docsUrl = `${repoUrl}/tree/main/docs`
// What's kept, and how it's protected.
const privacyLink = site.privacyLink ?? { to: `${repoUrl}/blob/main/docs/SECURITY_MODEL.md`, label: 'Read the security model' }

const STEPS = [
  { label: 'Target', title: 'Paste a link', text: 'A GitHub, GitLab, Bitbucket or Hugging Face repository or folder, a single SKILL.md, an upload, or an MCP server’s name.' },
  { label: 'Checks', title: 'More than 20 analyzers read it', text: 'Hidden instructions, exfiltration, dangerous code, tampered artifacts and poisoned MCP tools. AI review reads it as a whole, if you ask.' },
  { label: 'Verdict', title: 'Get the report, and its stamp', text: 'Passed, review first, or rejected, with every finding located, explained and given a fix.' }
]

const inspectable = computed<Feature[]>(() => [
  { title: 'Links', text: 'A repository, one folder in it, or a single skill file, on GitHub, GitLab, Bitbucket or Hugging Face.' },
  ...(features.value?.uploads ? [{ title: 'Uploads', text: 'Drop a .zip of a skill, or its SKILL.md, to check one you haven’t published. The file is deleted once it’s inspected.' }] : []),
  ...(features.value?.github ? [{ title: 'Private GitHub repositories', text: 'Connect GitHub, choose the repositories it may read, and inspect them like any link. The report stays yours.' }] : []),
  { title: 'Repositories with several skills', text: 'Each skill gets its own verdict and report, under one overall result.' },
  { title: 'MCP servers', text: 'A server’s name from the MCP Registry, to check its posture: pinned packages with valid hashes, a source repository, an active status and HTTPS endpoints.' },
  { title: 'Optional AI review', text: aiReviewText(health.value?.ai_providers, health.value?.allow_custom_ai_url) }
])

const KEEP_TRACK: Feature[] = [
  { title: 'History', text: 'Your inspections in one register you can sort and filter, each target’s lined up as a timeline. Follow an inspection’s checks and log while it runs.' },
  { title: 'Re-inspect, and see what changed', text: 'Inspect a skill again: findings are marked new, fixed or unchanged, with the change in score and verdict.' },
  { title: 'Baselines', text: 'Accept the findings you’ve reviewed, and see only what’s new next time. A skill can ship a baseline of its own, applied only if you ask.' }
]

const SHARE_AUTOMATE: Feature[] = [
  { title: 'Export', text: 'Download a report as skillspector’s JSON, or as SARIF for GitHub code scanning and other SARIF tools.' },
  { title: 'Share links and the inspection tag', text: 'A read-only link to a report that works without signing in, until you revoke it, and a README badge that shows its stamp.' },
  { title: 'GitHub Action and API tokens', text: 'Inspect the skills a pull request changes and comment with each verdict; start and read inspections from scripts and CI.' }
]

const PRIVACY = computed(() => [
  'Your inspections and their reports are yours alone, until you share one.',
  features.value?.uploads ? 'An uploaded skill is deleted as soon as it’s inspected.' : null,
  'A Claude key you save is checked, encrypted, and never shown again.',
  'AI review runs only when you turn it on, and the skill goes only to the provider you chose.',
  'You can delete your account, and everything of yours goes with it.'
].filter((line): line is string => !!line))
</script>

<template>
  <div class="flex flex-col gap-20 pt-12 pb-8 sm:pt-16 lg:gap-24">
    <UContainer>
      <section class="grid items-center gap-12 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] lg:gap-14">
        <div class="flex flex-col items-start gap-6">
          <p class="eyebrow text-muted">
            Pre-install inspection for agent skills
          </p>
          <h1 class="display text-6xl text-highlighted text-balance sm:text-7xl lg:text-[5.25rem]">
            Inspect a skill before it runs on your machine.
          </h1>
          <p class="max-w-xl text-lg text-toned text-pretty">
            Claude Code, Codex and MCP skills checked for prompt injection, data exfiltration and
            dangerous code. You get an inspection report: every finding, its evidence, and a verdict.
          </p>
          <div class="flex flex-wrap gap-3">
            <UButton
              v-if="session?.signup_allowed"
              to="/signup"
              color="primary"
              size="xl"
              trailing-icon="i-lucide-arrow-right"
            >
              Create an account
            </UButton>
            <UButton
              to="/login"
              :color="session?.signup_allowed ? 'neutral' : 'primary'"
              :variant="session?.signup_allowed ? 'outline' : 'solid'"
              size="xl"
            >
              Sign in
            </UButton>
          </div>
        </div>

        <figure
          class="surface m-0 flex flex-col gap-4 p-6 shadow-[8px_8px_0_var(--ui-border)] sm:p-7"
          aria-label="An inspection report, stamped Rejected"
        >
          <div class="flex items-baseline justify-between border-b border-inverted pb-2.5">
            <span class="display text-2xl text-highlighted">Inspection report</span>
            <span class="font-mono text-sm text-muted">INS-0412</span>
          </div>
          <dl class="m-0 grid grid-cols-[7rem_minmax(0,1fr)] gap-y-2 text-sm">
            <dt class="eyebrow pt-0.5 text-muted">
              Skill
            </dt>
            <dd class="m-0 font-mono break-all text-highlighted">
              github.com/acme/pdf-tools
            </dd>
            <dt class="eyebrow pt-0.5 text-muted">
              Checks
            </dt>
            <dd class="m-0 text-highlighted">
              24 run · 0 skipped
            </dd>
            <dt class="eyebrow pt-0.5 text-muted">
              Findings
            </dt>
            <dd class="m-0 text-highlighted">
              9 · 4 high
            </dd>
            <dt class="eyebrow pt-0.5 text-muted">
              Risk
            </dt>
            <dd class="m-0 font-mono text-highlighted">
              100 / 100
            </dd>
          </dl>
          <VerdictStamp
            recommendation="DO_NOT_INSTALL"
            size="lg"
            tilt
            class="mt-2 self-end"
          />
        </figure>
      </section>
    </UContainer>

    <UContainer>
      <section
        aria-labelledby="how-heading"
        class="flex flex-col gap-5"
      >
        <SectionHeading
          id="how-heading"
          :number="1"
          title="How an inspection works"
        />
        <ol class="surface m-0 grid list-none p-0 md:grid-cols-3">
          <li
            v-for="(step, index) in STEPS"
            :key="step.title"
            class="flex flex-col gap-2.5 border-default p-6 not-last:border-b md:not-last:border-r md:not-last:border-b-0"
          >
            <span class="font-mono text-sm text-brand-ink">0{{ index + 1 }} · {{ step.label }}</span>
            <h3 class="text-lg font-semibold text-highlighted">
              {{ step.title }}
            </h3>
            <p class="text-sm text-muted text-pretty">
              {{ step.text }}
            </p>
          </li>
        </ol>
      </section>
    </UContainer>

    <UContainer>
      <LandingExampleResult />
    </UContainer>

    <UContainer>
      <ScanCoverage :number="3" />
    </UContainer>

    <UContainer>
      <LandingFeatureGrid
        id="sources-heading"
        :number="4"
        title="What you can inspect"
        :features="inspectable"
      />
    </UContainer>

    <UContainer class="grid gap-12 lg:grid-cols-2 lg:gap-8">
      <LandingFeatureGrid
        id="track-heading"
        :number="5"
        title="Keep track"
        lead="Skills change. See what a new version brings, and focus on what’s new."
        :features="KEEP_TRACK"
        :columns="2"
        class="[&_ul]:sm:grid-cols-1"
      />
      <LandingFeatureGrid
        id="share-heading"
        :number="6"
        title="Share and automate"
        lead="Reports that travel: to a teammate, a README, or a pull request."
        :features="SHARE_AUTOMATE"
        :columns="2"
        class="[&_ul]:sm:grid-cols-1"
      />
    </UContainer>

    <UContainer>
      <div class="grid gap-3 lg:grid-cols-2">
        <section
          aria-labelledby="privacy-heading"
          class="surface flex flex-col gap-4 p-6 sm:p-7"
        >
          <h2
            id="privacy-heading"
            class="eyebrow text-muted"
          >
            Private by default
          </h2>
          <ul class="flex flex-col gap-2.5">
            <li
              v-for="line in PRIVACY"
              :key="line"
              class="flex items-start gap-2.5 text-sm text-highlighted"
            >
              <UIcon
                name="i-lucide-lock"
                class="mt-0.5 size-4 shrink-0 text-brand-ink"
                aria-hidden="true"
              />
              {{ line }}
            </li>
          </ul>
          <ULink
            :to="privacyLink.to"
            class="self-start text-sm font-semibold text-brand-ink underline underline-offset-2"
          >
            {{ privacyLink.label }}
          </ULink>
        </section>

        <section
          aria-labelledby="open-source-heading"
          class="flex flex-col gap-4 bg-graphite-950 p-6 text-graphite-200 sm:p-7"
        >
          <h2
            id="open-source-heading"
            class="eyebrow text-graphite-400"
          >
            Free software
          </h2>
          <p class="text-[15px] text-pretty">
            {{ site.name }} is free software under the AGPL-3.0, built on
            <ULink
              :to="`https://github.com/${site.scannerRepo}`"
              class="font-semibold text-white underline underline-offset-2"
            >NVIDIA’s skillspector</ULink>, run as a library. Run your own with Docker Compose,
            with accounts or without.
          </p>
          <div class="mt-auto flex flex-wrap gap-2">
            <UButton
              :to="repoUrl"
              icon="i-simple-icons-github"
              class="bg-white text-graphite-950 hover:bg-graphite-200"
            >
              Source code
            </UButton>
            <UButton
              :to="docsUrl"
              icon="i-lucide-book-open"
              variant="outline"
              class="text-white ring-white hover:bg-white/10"
            >
              Documentation
            </UButton>
          </div>
        </section>
      </div>
    </UContainer>

    <UContainer>
      <LandingFaq />
    </UContainer>

    <UContainer>
      <section
        aria-labelledby="start-heading"
        class="surface flex flex-col items-start gap-5 border-2 border-inverted p-6 sm:flex-row sm:items-center sm:justify-between sm:p-10"
      >
        <div class="flex flex-col gap-3">
          <h2
            id="start-heading"
            class="display text-4xl text-highlighted text-balance sm:text-5xl"
          >
            Inspect the next skill before you install it.
          </h2>
          <p class="max-w-2xl text-[15px] text-muted text-pretty">
            {{ session?.signup_allowed
              ? 'Create an account in a few seconds: your reports stay private to it.'
              : 'Sign-up is closed on this server: ask its admin for an account, or run your own.' }}
          </p>
        </div>
        <UButton
          :to="session?.signup_allowed ? '/signup' : '/login'"
          color="primary"
          size="xl"
          class="shrink-0"
          trailing-icon="i-lucide-arrow-right"
        >
          {{ session?.signup_allowed ? 'Create an account' : 'Sign in' }}
        </UButton>
      </section>
    </UContainer>
  </div>
</template>
