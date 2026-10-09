<script setup lang="ts">
import type { LLMConfig, LLMProvider } from '../../shared/types/scan'
import type { ScanTargetKind } from '../../shared/utils/scan'

// Awaited so the server-rendered default provider matches the client's (see the watch below).
const { data: health, pending: healthPending } = await useHealth()

const PROVIDER_LABELS: Record<LLMProvider, string> = {
  anthropic: 'Anthropic',
  openai: 'OpenAI',
  azure_openai: 'Azure OpenAI',
  openai_compatible: 'OpenAI-compatible API (Groq, Together, Mistral…)',
  nv_build: 'NVIDIA build.nvidia.com',
  ollama: 'Ollama (self-hosted)',
  claude_cli: 'Claude via this server — no key needed'
}

const PROVIDER_RECIPIENTS: Record<LLMProvider, string> = {
  anthropic: 'Anthropic',
  openai: 'OpenAI (or the endpoint you set)',
  azure_openai: 'your Azure OpenAI resource',
  openai_compatible: 'the API at the endpoint you set',
  nv_build: 'NVIDIA',
  ollama: 'your Ollama server',
  claude_cli: 'Anthropic, through this server’s Claude login'
}

const API_KEY_LINKS: Partial<Record<LLMProvider, string>> = {
  anthropic: 'https://console.anthropic.com/settings/keys',
  openai: 'https://platform.openai.com/api-keys',
  azure_openai: 'https://portal.azure.com/#view/Microsoft_Azure_ProjectOxford/CognitiveServicesHub/~/OpenAI',
  nv_build: 'https://build.nvidia.com/settings/api-keys'
}

// Providers that only work with an endpoint of the user's (scanner.NEEDS_BASE_URL on the API).
const NEEDS_ENDPOINT: LLMProvider[] = ['azure_openai', 'openai_compatible']

const PROVIDER_ICONS: Record<LLMProvider, string> = {
  anthropic: 'i-simple-icons-anthropic',
  openai: 'i-simple-icons-openai',
  azure_openai: 'i-simple-icons-microsoftazure',
  openai_compatible: 'i-lucide-plug',
  nv_build: 'i-simple-icons-nvidia',
  ollama: 'i-simple-icons-ollama',
  claude_cli: 'i-lucide-terminal'
}

const { session, user } = useAuth()
// The providers this server lets scans use (INSKECT_AI_PROVIDERS), and whether a scan may
// point one at an endpoint of its own (INSKECT_ALLOW_CUSTOM_AI_URL).
const customAiUrl = computed(() => health.value?.allow_custom_ai_url ?? true)
const providerAllowed = (value: LLMProvider) =>
  !!health.value?.ai_providers.includes(value) && (customAiUrl.value || !NEEDS_ENDPOINT.includes(value))

const providerOptions = computed(() => {
  const claudeCliLabel = healthPending.value
    ? 'Claude CLI (checking availability…)'
    : PROVIDER_LABELS.claude_cli

  type ProviderOption = { value: LLMProvider, label: string, icon: string, disabled?: boolean }
  const claudeCli: ProviderOption = { value: 'claude_cli', label: claudeCliLabel, icon: PROVIDER_ICONS.claude_cli, disabled: healthPending.value }
  const withKey: ProviderOption[] = [
    { value: 'anthropic', label: PROVIDER_LABELS.anthropic, icon: PROVIDER_ICONS.anthropic },
    { value: 'openai', label: PROVIDER_LABELS.openai, icon: PROVIDER_ICONS.openai },
    { value: 'azure_openai', label: PROVIDER_LABELS.azure_openai, icon: PROVIDER_ICONS.azure_openai },
    { value: 'nv_build', label: PROVIDER_LABELS.nv_build, icon: PROVIDER_ICONS.nv_build },
    { value: 'openai_compatible', label: PROVIDER_LABELS.openai_compatible, icon: PROVIDER_ICONS.openai_compatible },
    { value: 'ollama', label: PROVIDER_LABELS.ollama, icon: PROVIDER_ICONS.ollama }
  ]
  // The zero-setup option goes first when it works.
  const options = health.value?.claude_cli_available ? [claudeCli, ...withKey] : [...withKey, claudeCli]
  return options.filter(option => providerAllowed(option.value))
})

// `/?target=…&deep=1` prefills the form, e.g. from a result page's "Scan again".
const route = useRoute()
const queryTarget = typeof route.query.target === 'string' ? route.query.target : ''
const target = ref(queryTarget)
const targetInput = useTemplateRef('targetInput')
const repoSelect = useTemplateRef('repoSelect')
const targetTouched = ref(!!queryTarget)
const targetInfo = computed(() => describeScanTarget(target.value))
const targetProblem = computed(() =>
  targetTouched.value && targetInfo.value && !targetInfo.value.ok ? targetInfo.value.problem : undefined
)

// Where the skill comes from, chosen on the left of the field. Typing or dropping something that
// belongs to another source switches to it, so pasting never needs choosing first.
type Source = 'link' | 'github' | 'upload' | 'mcp'
const kindOf = (value: string) => {
  const info = describeScanTarget(value)
  return info?.ok ? info.kind : undefined
}
const source = ref<Source>(kindOf(queryTarget) === 'mcp' ? 'mcp' : 'link')
watch(targetInfo, (info) => {
  if (info?.ok && (source.value === 'link' || source.value === 'mcp')) source.value = info.kind === 'mcp' ? 'mcp' : 'link'
})
// An MCP server is checked from its registry entry alone: the depth and the options, which are
// about a skill's code, don't apply to it.
const isMcpServer = computed(() => source.value === 'mcp')

// A skill uploaded from this computer instead of a link: a .zip, or a SKILL.md on its own. Offered
// when the server takes uploads, which it holds only until the scan ends (backend/app/uploads.py).
const uploadStore = computed(() => health.value?.upload_store ?? null)
const file = ref<File | null>(null)
const fileError = ref('')
const fileInput = ref<HTMLInputElement>()
const dragging = ref(false)

function pickFile(picked: File | null | undefined) {
  fileError.value = ''
  if (!picked) return
  const maxBytes = health.value?.max_upload_bytes ?? 0
  if (!/\.(zip|md)$/i.test(picked.name)) {
    fileError.value = 'Upload a .zip of the skill, or its SKILL.md'
  } else if (picked.size > maxBytes) {
    fileError.value = `${picked.name} is larger than ${formatBytes(maxBytes)}`
  } else {
    file.value = picked
  }
  source.value = 'upload'
}

function onFileInput(event: Event) {
  const input = event.target as HTMLInputElement
  pickFile(input.files?.[0])
  // Picking the same file again still fires a change.
  input.value = ''
}

function onDrop(event: DragEvent) {
  dragging.value = false
  if (uploadStore.value && !submitting.value) pickFile(event.dataTransfer?.files?.[0])
}

function clearFile() {
  file.value = null
  fileError.value = ''
}

// Point at an existing result before starting a duplicate scan of the same URL.
const { data: recentScans } = useRecentScans()
// As the API stores it: an MCP server's name becomes its registry entry's URL.
const normalizeTarget = (value: string) => {
  const server = parseMcpServer(value)
  return server ? mcpEntryUrl(server) : value.trim().replace(/\/+$/, '')
}
const previousScan = computed(() => {
  if (source.value === 'upload' || !targetInfo.value?.ok) return undefined
  const wanted = normalizeTarget(target.value)
  return recentScans.value?.items.find(scan => scan.status !== 'error' && normalizeTarget(scan.target) === wanted)
})

// Real, stable targets: a published skill, a skillspector test fixture that's flagged
// DO_NOT_INSTALL even without AI analysis, and a well-known MCP server.
const EXAMPLES = [
  { label: 'Anthropic’s PDF skill', icon: 'i-lucide-file-text', target: 'https://github.com/anthropics/skills/blob/main/skills/pdf/SKILL.md' },
  { label: 'A poisoned MCP tool', icon: 'i-lucide-skull', target: 'https://github.com/NVIDIA/skillspector/blob/main/tests/fixtures/mcp_poisoned_tool/SKILL.md' },
  { label: 'GitHub’s MCP server', icon: 'i-lucide-server', target: 'io.github.github/github-mcp-server' }
]

// Signed in with GitHub connected, one of their repositories can be picked instead of pasted
// (GitHubRepoSelect): its link is the target.
const { data: connections, execute: loadConnections } = useFetch<{ github: { available: boolean, manage_url: string | null, connection: object | null } }>(
  '/api/account/connections',
  { key: 'account-connections', immediate: false, server: false }
)
watch(user, (signedIn) => {
  if (signedIn) loadConnections()
}, { immediate: true })
const github = computed(() => user.value && connections.value?.github.available ? connections.value.github : null)

const SOURCES: Record<Source, { label: string, icon: string }> = {
  link: { label: 'Link', icon: 'i-lucide-link' },
  github: { label: 'GitHub', icon: 'i-simple-icons-github' },
  upload: { label: 'Upload', icon: 'i-lucide-upload' },
  mcp: { label: 'MCP server', icon: 'i-lucide-server' }
}
const sources = computed(() => (['link', 'github', 'upload', 'mcp'] as Source[]).filter(name =>
  name === 'github' ? !!github.value?.connection : name === 'upload' ? !!uploadStore.value : true
))
// A source that went away (GitHub disconnected, uploads turned off) falls back to a link.
watch(sources, (available) => {
  if (!available.includes(source.value)) selectSource('link')
})

const sourceItems = computed(() => [
  [
    { type: 'label' as const, label: 'Inspect from' },
    ...sources.value.map(name => ({
      type: 'checkbox' as const,
      label: SOURCES[name].label,
      icon: SOURCES[name].icon,
      checked: source.value === name,
      onSelect: () => selectSource(name)
    })),
    ...(github.value && !github.value.connection
      ? [{ label: 'Connect GitHub…', icon: SOURCES.github.icon, to: '/account' }]
      : [])
  ],
  [
    { type: 'label' as const, label: 'Try an example' },
    ...EXAMPLES.map(example => ({ label: example.label, icon: example.icon, onSelect: () => fillTarget(example.target) }))
  ]
])

function focusField() {
  nextTick(() => {
    if (source.value === 'github') repoSelect.value?.focus()
    else targetInput.value?.inputRef?.focus()
  })
}

function selectSource(next: Source) {
  if (next === source.value) return
  // What's in the field stays only when it's also a target of the new source.
  const kind = kindOf(target.value)
  const fits = next === 'mcp' ? kind === 'mcp' : next === 'link' ? !!kind && kind !== 'mcp' : false
  if (!fits) target.value = ''
  targetTouched.value = false
  fileError.value = ''
  source.value = next
  if (next === 'upload') {
    if (!file.value) fileInput.value?.click()
  } else {
    focusField()
  }
}

function fillTarget(value: string) {
  source.value = kindOf(value) === 'mcp' ? 'mcp' : 'link'
  target.value = value
  targetTouched.value = true
  // Keep focus in the form so Enter scans.
  focusField()
}

const TARGET_KIND_LABELS: Record<ScanTargetKind, { icon: string, label: string }> = {
  repository: { icon: 'i-lucide-git-branch', label: 'repository' },
  folder: { icon: 'i-lucide-folder', label: 'folder' },
  file: { icon: 'i-lucide-file-text', label: 'single file' },
  archive: { icon: 'i-lucide-file-archive', label: 'archive' },
  mcp: { icon: 'i-lucide-server', label: 'MCP server' }
}

const useLlm = ref(false)
const provider = ref<LLMProvider>('anthropic')
const apiKey = ref('')
const baseUrl = ref('')
const model = ref('')
const advancedOpen = ref(false)
const submitting = ref(false)
const errorMessage = ref('')

// Remembered per browser so repeat visitors don't re-pick their setup. The API key never is.
const PREFS_KEY = 'inskect:scan-prefs'
interface ScanPrefs {
  source?: Source
  useLlm?: boolean
  provider?: LLMProvider
  baseUrl?: string
  model?: string
}
const hasStoredProvider = ref(false)

onMounted(() => {
  // Skip on touch devices, where focusing pops up the keyboard over the page.
  if (window.matchMedia('(pointer: fine)').matches) targetInput.value?.inputRef?.focus()

  let prefs: ScanPrefs = {}
  try {
    prefs = JSON.parse(localStorage.getItem(PREFS_KEY) ?? '{}') as ScanPrefs
  } catch {
    // Unreadable or unavailable storage: start from the defaults.
  }
  // The last source, once it's known to be offered (GitHub's is fetched), unless a link was given.
  if (prefs.source && !queryTarget) {
    const stop = watch(sources, (available) => {
      if (!available.includes(prefs.source!)) return
      if (source.value === 'link' && !target.value) source.value = prefs.source!
      nextTick(() => stop())
    }, { immediate: true })
  }
  if (route.query.deep === '1') useLlm.value = true
  else if (typeof prefs.useLlm === 'boolean') useLlm.value = prefs.useLlm
  if (prefs.provider && prefs.provider in PROVIDER_LABELS) {
    provider.value = prefs.provider
    hasStoredProvider.value = true
  }
  baseUrl.value = prefs.baseUrl ?? ''
  model.value = prefs.model ?? ''
  advancedOpen.value = !!(baseUrl.value || model.value)
})

function savePrefs() {
  const prefs: ScanPrefs = {
    source: source.value,
    useLlm: useLlm.value,
    provider: provider.value,
    baseUrl: baseUrl.value.trim() || undefined,
    model: model.value.trim() || undefined
  }
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs))
  } catch {
    // Storage can be unavailable (private mode, blocked site data); preferences are optional.
  }
}

// Default to the server's Claude login when it's available, unless the visitor picked before.
// Default provider, unless the visitor picked one before: their own saved Claude key first, then
// the server's Claude login when it's available.
watch([() => session.value?.claude_key, () => health.value?.claude_cli_available], ([saved, cliAvailable]) => {
  if (hasStoredProvider.value) return
  if (saved) provider.value = 'anthropic'
  else if (cliAvailable) provider.value = 'claude_cli'
}, { immediate: true })

// A remembered provider this server doesn't offer (e.g. after its settings changed) falls back to the
// first it does.
watch([providerOptions, provider], ([options, current]) => {
  if (options.length && !options.some(option => option.value === current)) provider.value = options[0]!.value
}, { immediate: true })

// Measured on this deployment: static inspections of a repo or SKILL.md take about a minute.
const durationHint = computed(() => useLlm.value ? 'With AI review, takes a few minutes.' : 'Takes about a minute.')

const AI_REVIEW_HELP = 'Off, 20+ static analyzers run and nothing leaves this server. '
  + 'On, an AI model also reads the skill’s intent: slower, and its content is sent to the AI provider.'

// The Claude key saved to the user's account (app/claude_key.py on the API), used unless they
// choose to paste a different one for this scan.
const savedKey = computed(() => session.value?.claude_key ?? null)
const useOtherKey = ref(false)
const usingSavedKey = computed(() => provider.value === 'anthropic' && !!savedKey.value && !useOtherKey.value)
const needsApiKey = computed(() => provider.value !== 'ollama' && provider.value !== 'claude_cli' && !usingSavedKey.value)
const claudeCliUnauthenticated = computed(() =>
  provider.value === 'claude_cli' && !healthPending.value && !health.value?.claude_cli_available
)
const backendDown = computed(() => health.value?.status === 'down')
const canSubmit = computed(() => {
  if (backendDown.value) return false
  if (source.value === 'upload' ? !file.value : !targetInfo.value?.ok) return false
  if (isMcpServer.value) return true
  if (useLlm.value && needsApiKey.value && !apiKey.value.trim()) return false
  if (useLlm.value && needsEndpoint.value && !baseUrl.value.trim()) return false
  if (useLlm.value && claudeCliUnauthenticated.value) return false
  return true
})

const needsEndpoint = computed(() => NEEDS_ENDPOINT.includes(provider.value))
const baseUrlPlaceholder = computed(() => {
  switch (provider.value) {
    case 'ollama':
      return 'http://host.docker.internal:11434/v1'
    case 'openai':
      return 'https://api.openai.com/v1 (or an OpenAI-compatible endpoint)'
    case 'azure_openai':
      return 'https://your-resource.openai.azure.com'
    case 'openai_compatible':
      return 'https://api.groq.com/openai/v1'
    default:
      return 'https://api.anthropic.com'
  }
})

// skillspector's known models for the provider (GET /api/models), offered first; any other model
// can still be typed in.
const { data: modelCatalog } = useFetch<Record<string, { default: string | null, models: string[] }>>('/api/models', { key: 'models', lazy: true })
const modelItems = computed(() => {
  const known = modelCatalog.value?.[provider.value]?.models ?? []
  return model.value && !known.includes(model.value) ? [model.value, ...known] : known
})
const modelDefault = computed(() => modelCatalog.value?.[provider.value]?.default)

// An optional skillspector baseline: findings it accepts don't count. Read in the browser and sent
// as text; the API checks it before queueing the scan.
const MAX_BASELINE_BYTES = 256 * 1024
// skillspector's example of the format, at the version the API pins (backend/pyproject.toml).
const BASELINE_FORMAT_DOCS = 'https://github.com/NVIDIA/SkillSpector/blob/v2.12.0/docs/SUPPRESSION.md#baseline-file-format'
const baselineInput = ref<HTMLInputElement>()
const baseline = ref<{ name: string, text: string } | null>(null)
const baselineError = ref('')
// The baseline the skill's author ships in it, applied only when asked: it's theirs, so it could hide
// real findings. A baseline file chosen here is used instead.
const useShippedBaseline = ref(false)
const applyShippedBaseline = computed(() => useShippedBaseline.value && !baseline.value)

async function pickBaseline(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  baselineError.value = ''
  if (!file) return
  if (file.size > MAX_BASELINE_BYTES) {
    baselineError.value = `${file.name} is larger than ${MAX_BASELINE_BYTES / 1024} KB`
    baseline.value = null
  } else {
    baseline.value = { name: file.name, text: await file.text() }
  }
  // Picking the same file again still fires a change.
  if (baselineInput.value) baselineInput.value.value = ''
}

// Following the skill's external references (Git repositories and raw files it links to), as deep
// as the server allows.
const followReferences = ref(false)
const referenceDepth = ref(1)
const maxReferenceDepth = computed(() => health.value?.transitive_max_depth ?? 0)
const referenceDepthOptions = computed(() => Array.from({ length: maxReferenceDepth.value }, (_, i) => ({
  label: i === 0 ? '1 level: what the skill links to' : `${i + 1} levels: and what those link to`,
  value: i + 1
})))

// Baseline and references are rarely needed, so they sit behind "More options"; its label says
// what's set, so nothing hidden is applied unnoticed.
const moreOpen = ref(false)
const moreSummary = computed(() => {
  const set = []
  if (baseline.value) set.push(`baseline: ${baseline.value.name}`)
  if (applyShippedBaseline.value) set.push('the skill’s own baseline')
  if (followReferences.value && maxReferenceDepth.value) {
    set.push(`references: ${referenceDepth.value} level${referenceDepth.value === 1 ? '' : 's'}`)
  }
  return set.join(' · ')
})

// The file goes with the scan.
const submitUpload = useSkillUpload()

const { track } = useAnalytics()

async function submit() {
  targetTouched.value = true
  if (!canSubmit.value) return

  submitting.value = true
  errorMessage.value = ''

  const forCode = !isMcpServer.value
  const llm: LLMConfig | undefined = forCode && useLlm.value
    ? {
        provider: provider.value,
        useSavedKey: usingSavedKey.value || undefined,
        apiKey: usingSavedKey.value ? undefined : apiKey.value.trim() || undefined,
        baseUrl: baseUrl.value.trim() || undefined,
        model: model.value.trim() || undefined
      }
    : undefined

  const options = {
    llm,
    baseline: forCode ? baseline.value?.text : undefined,
    useShippedBaseline: forCode && applyShippedBaseline.value ? true : undefined,
    transitiveDepth: forCode && followReferences.value && maxReferenceDepth.value ? referenceDepth.value : undefined
  }

  try {
    const { id } = source.value === 'upload' && file.value
      ? await submitUpload(file.value, options)
      : await $fetch<{ id: string }>('/api/scan', { method: 'POST', body: { target: target.value.trim(), ...options } })
    savePrefs()
    track('Scan Started', { source: source.value, ai_review: !!llm })
    await navigateTo(`/scan/${id}`)
  } catch (err) {
    errorMessage.value = apiErrorMessage(err, 'Failed to start the inspection')
    submitting.value = false
  }
}
</script>

<template>
  <form
    class="surface relative flex flex-col"
    @submit.prevent="submit"
    @dragover.prevent="dragging = !!uploadStore"
    @dragleave.self="dragging = false"
    @drop.prevent="onDrop"
  >
    <div
      v-if="dragging"
      class="pointer-events-none absolute inset-0 z-10 flex items-center justify-center gap-2 bg-default/90 font-semibold text-highlighted ring-2 ring-brand ring-inset"
    >
      <UIcon
        name="i-lucide-upload"
        class="size-5"
      />
      Drop a .zip or SKILL.md to inspect it (up to {{ formatBytes(health?.max_upload_bytes ?? 0) }})
    </div>
    <input
      ref="fileInput"
      type="file"
      accept=".zip,.md,application/zip,text/markdown"
      class="hidden"
      @change="onFileInput"
    >

    <div class="flex flex-col gap-1 border-b-2 border-inverted px-5 py-5 sm:px-7">
      <span class="eyebrow text-muted">Form · new inspection</span>
      <h1 class="display text-4xl text-highlighted sm:text-5xl">
        What should we inspect?
      </h1>
    </div>

    <div
      v-if="backendDown"
      class="px-5 pt-5 sm:px-7"
    >
      <UAlert
        color="warning"
        variant="subtle"
        icon="i-lucide-server-off"
        title="The inspector is unavailable right now"
        description="The inspection service isn’t responding, so new inspections can’t start. Past reports in the history are still available."
      />
    </div>

    <FormRow
      number="1"
      title="Target"
      hint="A skill, or an MCP server from the registry."
    >
      <UFormField
        label="Skill or MCP server"
        :error="fileError || (source === 'upload' ? undefined : targetProblem)"
        :ui="{ label: 'sr-only' }"
      >
        <div class="flex gap-2 bg-muted p-1.5 ring-1 ring-default transition-shadow focus-within:ring-2 focus-within:ring-brand max-sm:flex-col">
          <div class="flex min-w-0 flex-1 items-center">
            <UDropdownMenu
              :items="sourceItems"
              :content="{ align: 'start' }"
              :ui="{ content: 'w-56' }"
            >
              <UButton
                :icon="SOURCES[source].icon"
                trailing-icon="i-lucide-chevron-down"
                color="neutral"
                variant="ghost"
                size="xl"
                class="h-12 shrink-0 font-medium"
                :aria-label="`Inspect from: ${SOURCES[source].label}`"
                :disabled="submitting"
              >
                <span class="max-sm:sr-only">{{ SOURCES[source].label }}</span>
              </UButton>
            </UDropdownMenu>
            <USeparator
              orientation="vertical"
              class="h-6 shrink-0"
            />

            <template v-if="source === 'upload'">
              <div
                v-if="file"
                class="flex h-12 min-w-0 flex-1 items-center gap-2 px-3"
              >
                <UIcon
                  :name="file.name.toLowerCase().endsWith('.zip') ? 'i-lucide-file-archive' : 'i-lucide-file-text'"
                  class="size-5 shrink-0 text-dimmed"
                />
                <span class="truncate font-mono text-sm text-highlighted">{{ file.name }}</span>
                <span class="shrink-0 text-xs text-muted">{{ formatBytes(file.size) }}</span>
                <UButton
                  icon="i-lucide-x"
                  color="neutral"
                  variant="ghost"
                  size="sm"
                  class="ml-auto"
                  aria-label="Remove the file"
                  :disabled="submitting"
                  @click="clearFile"
                />
              </div>
              <UButton
                v-else
                color="neutral"
                variant="ghost"
                size="xl"
                class="h-12 min-w-0 flex-1 text-sm font-normal text-muted"
                :disabled="submitting"
                @click="fileInput?.click()"
              >
                <span class="truncate">Choose or drop a .zip or SKILL.md, up to {{ formatBytes(health?.max_upload_bytes ?? 0) }}</span>
              </UButton>
            </template>
            <GitHubRepoSelect
              v-else-if="source === 'github'"
              ref="repoSelect"
              v-model="target"
              :manage-url="github?.manage_url ?? null"
              :disabled="submitting"
              class="min-w-0 flex-1"
            />
            <UInput
              v-else
              id="scan-target"
              ref="targetInput"
              v-model="target"
              type="text"
              :inputmode="source === 'mcp' ? 'text' : 'url'"
              autocapitalize="off"
              autocomplete="off"
              spellcheck="false"
              :placeholder="source === 'mcp' ? 'io.github.acme/weather' : 'Paste a link, or pick an example from the menu'"
              size="xl"
              class="min-w-0 flex-1"
              variant="none"
              :ui="{ base: 'h-12 font-mono text-sm' }"
              :disabled="submitting"
              @blur="targetTouched = true"
            />
          </div>
          <UButton
            type="submit"
            color="primary"
            size="xl"
            trailing-icon="i-lucide-arrow-right"
            class="h-12 justify-center px-6 font-semibold shadow-sm"
            :loading="submitting"
            :disabled="!canSubmit"
          >
            Inspect
          </UButton>
        </div>
        <template #help>
          <span v-if="source === 'upload'">
            Uploaded for this inspection only, and deleted once it’s inspected.
          </span>
          <span
            v-else-if="targetInfo?.ok"
            class="flex min-w-0 items-center gap-1.5"
          >
            <UIcon
              name="i-lucide-check"
              class="size-4 shrink-0 text-primary"
            />
            <span class="shrink-0">{{ targetInfo.host }} · {{ TARGET_KIND_LABELS[targetInfo.kind].label }} ·</span>
            <span class="truncate font-mono text-xs text-highlighted">{{ targetInfo.title }}</span>
          </span>
        </template>
      </UFormField>

      <UAlert
        v-if="previousScan"
        color="neutral"
        variant="subtle"
        icon="i-lucide-history"
        :description="previousScan.status === 'done' ? 'Open its report, or inspect it again for a fresh one.' : 'Follow its progress instead of starting another inspection.'"
        :actions="[{ label: previousScan.status === 'done' ? 'View report' : 'Follow inspection', to: `/scan/${previousScan.id}`, color: 'neutral', variant: 'outline', trailingIcon: 'i-lucide-arrow-right' }]"
        orientation="horizontal"
      >
        <template #title>
          <template v-if="previousScan.status === 'done'">
            Already inspected <NuxtTime
              :datetime="previousScan.created_at * 1000"
              relative
            /><template v-if="previousScan.recommendation">
              — {{ RECOMMENDATION_LABEL[previousScan.recommendation] }}
            </template>
          </template>
          <template v-else>
            This {{ isMcpServer ? 'server' : 'skill' }} is being inspected right now
          </template>
        </template>
      </UAlert>
    </FormRow>

    <FormRow
      v-if="!isMcpServer"
      number="2"
      title="AI review"
      hint="A semantic read on top of the static checks. The skill’s content goes to the provider."
    >
      <div class="flex items-center gap-1.5">
        <USwitch
          id="scan-ai-review"
          v-model="useLlm"
          label="AI review"
          :disabled="submitting"
          :ui="{ label: 'font-medium text-highlighted' }"
        />
        <UTooltip
          :text="AI_REVIEW_HELP"
          :content="{ side: 'top' }"
          :ui="{ content: 'max-w-xs h-auto whitespace-normal py-1.5' }"
        >
          <UIcon
            name="i-lucide-info"
            class="size-4 text-muted"
            tabindex="0"
            :aria-label="AI_REVIEW_HELP"
          />
        </UTooltip>
      </div>
      <Transition
        enter-active-class="transition duration-200 ease-out"
        enter-from-class="opacity-0 -translate-y-1"
        enter-to-class="opacity-100 translate-y-0"
        leave-active-class="transition duration-150 ease-in"
        leave-from-class="opacity-100 translate-y-0"
        leave-to-class="opacity-0 -translate-y-1"
      >
        <div
          v-if="useLlm && !isMcpServer"
          class="flex flex-col gap-3 bg-muted p-4 ring ring-default"
        >
          <p class="text-sm text-muted">
            Adds a semantic read of the skill’s intent. Slower, and the skill’s content is sent to {{ PROVIDER_RECIPIENTS[provider] }}.
          </p>
          <UFormField label="Provider">
            <USelect
              id="scan-provider"
              v-model="provider"
              :items="providerOptions"
              value-key="value"
              class="w-full"
              :disabled="submitting"
              :loading="healthPending"
            />
          </UFormField>

          <div
            v-if="usingSavedKey"
            class="flex flex-wrap items-center justify-between gap-2 border-l-[3px] border-brand bg-default px-3 py-2.5 text-sm"
          >
            <span class="flex items-center gap-2 text-default">
              <UIcon
                name="i-lucide-plug"
                class="size-4 shrink-0 text-brand-ink"
              />
              Using your saved Claude key
              <code class="font-mono text-xs text-highlighted">{{ savedKey?.hint }}</code>
            </span>
            <button
              type="button"
              class="cursor-pointer text-xs font-semibold text-muted underline underline-offset-2 hover:text-highlighted"
              @click="useOtherKey = true"
            >
              Use a different key for this inspection
            </button>
          </div>

          <UFormField
            v-if="needsApiKey"
            label="API key"
            description="Used only for this inspection, to call the provider directly, and deleted once it has run."
          >
            <template
              v-if="API_KEY_LINKS[provider]"
              #hint
            >
              <ULink
                :to="API_KEY_LINKS[provider]"
                target="_blank"
                class="text-xs"
              >
                Get a key
              </ULink>
            </template>
            <PasswordInput
              id="scan-api-key"
              v-model="apiKey"
              subject="API key"
              placeholder="sk-..."
              class="w-full"
              :disabled="submitting"
            />
            <template
              v-if="provider === 'anthropic' && savedKey"
              #help
            >
              <button
                type="button"
                class="cursor-pointer font-semibold underline underline-offset-2 hover:text-highlighted"
                @click="useOtherKey = false; apiKey = ''"
              >
                Use my saved key ({{ savedKey.hint }}) instead
              </button>
            </template>
            <template
              v-else-if="provider === 'anthropic' && session?.claude_key_available"
              #help
            >
              Tired of pasting it? <ULink
                to="/account"
                class="font-semibold underline underline-offset-2"
              >Save your key to your account</ULink>.
            </template>
          </UFormField>

          <UFormField
            v-if="needsEndpoint"
            :label="provider === 'azure_openai' ? 'Endpoint' : 'Base URL'"
            :description="provider === 'azure_openai' ? 'Your Azure OpenAI resource’s endpoint.' : 'The API’s OpenAI-compatible base URL.'"
            required
          >
            <UInput
              id="scan-endpoint"
              v-model="baseUrl"
              :placeholder="baseUrlPlaceholder"
              class="w-full"
              :disabled="submitting"
            />
          </UFormField>

          <UAlert
            v-if="claudeCliUnauthenticated"
            color="warning"
            variant="subtle"
            icon="i-lucide-alert-triangle"
            title="Server not logged in"
            description="This server's Claude CLI hasn't been authenticated yet — an admin needs to complete the login before this provider will work."
          />

          <UCollapsible
            v-model:open="advancedOpen"
            class="flex flex-col gap-3"
          >
            <UButton
              label="Advanced options"
              color="neutral"
              variant="link"
              size="xs"
              trailing-icon="i-lucide-chevron-down"
              class="self-start px-0"
              :ui="{ trailingIcon: 'transition-transform group-data-[state=open]:rotate-180' }"
            />

            <template #content>
              <div class="flex flex-col gap-3">
                <UFormField
                  v-if="provider !== 'claude_cli' && provider !== 'nv_build' && !needsEndpoint && customAiUrl"
                  label="Base URL"
                  description="Override for a proxy or an OpenAI-compatible endpoint."
                >
                  <UInput
                    id="scan-base-url"
                    v-model="baseUrl"
                    :placeholder="baseUrlPlaceholder"
                    class="w-full"
                    :disabled="submitting"
                  />
                </UFormField>

                <UFormField
                  :label="provider === 'azure_openai' ? 'Deployment' : 'Model'"
                  :description="provider === 'azure_openai'
                    ? 'The name of your Azure deployment. Leave empty to use one named after skillspector’s default model.'
                    : 'Pick one skillspector knows, or type any other. Leave empty for the provider’s recommended model.'"
                >
                  <USelectMenu
                    id="scan-model"
                    v-model="model"
                    :items="modelItems"
                    create-item
                    :placeholder="modelDefault ? `Default: ${modelDefault}` : 'Provider default'"
                    class="w-full"
                    :disabled="submitting"
                    @create="(item: string) => { model = item }"
                  />
                </UFormField>
              </div>
            </template>
          </UCollapsible>
        </div>
      </Transition>
    </FormRow>

    <FormRow
      v-if="!isMcpServer"
      number="3"
      title="Baseline and references"
      hint="Optional."
    >
      <UButton
        color="neutral"
        variant="link"
        size="sm"
        trailing-icon="i-lucide-chevron-down"
        class="self-start px-0 text-left"
        :aria-expanded="moreOpen"
        aria-controls="scan-more-options"
        :ui="{ trailingIcon: moreOpen ? 'transition-transform rotate-180' : 'transition-transform' }"
        @click="moreOpen = !moreOpen"
      >
        <span>
          More options<span
            v-if="moreSummary"
            class="font-normal text-muted"
          > · {{ moreSummary }}</span>
        </span>
      </UButton>
      <div
        v-if="moreOpen"
        id="scan-more-options"
      >
        <div class="flex flex-col gap-5">
          <div class="flex flex-col gap-1.5">
            <p class="flex items-center gap-1.5 font-semibold text-highlighted">
              Baseline
              <UTooltip text="What a baseline file looks like">
                <ULink
                  :to="BASELINE_FORMAT_DOCS"
                  target="_blank"
                  aria-label="What a baseline file looks like, in skillspector's documentation"
                  class="inline-flex text-muted hover:text-highlighted"
                >
                  <UIcon
                    name="i-lucide-info"
                    class="size-4"
                  />
                </ULink>
              </UTooltip>
            </p>
            <p class="text-sm text-muted">
              A <code class="font-mono text-xs">.skillspector-baseline.yaml</code> file: findings it accepts are
              suppressed and don’t count towards the score. Download one from an inspection’s report.
            </p>
            <div class="mt-1 flex flex-wrap items-center gap-2">
              <input
                ref="baselineInput"
                type="file"
                accept=".yaml,.yml,.json,application/json,application/yaml,text/yaml"
                class="sr-only"
                aria-label="Baseline file"
                :disabled="submitting"
                @change="pickBaseline"
              >
              <UButton
                :label="baseline ? 'Replace file' : 'Choose a file'"
                icon="i-lucide-file-check"
                size="sm"
                color="neutral"
                variant="outline"
                :disabled="submitting"
                @click="baselineInput?.click()"
              />
              <template v-if="baseline">
                <span class="font-mono text-xs text-highlighted">{{ baseline.name }}</span>
                <UButton
                  icon="i-lucide-x"
                  size="xs"
                  color="neutral"
                  variant="ghost"
                  aria-label="Remove the baseline"
                  :disabled="submitting"
                  @click="baseline = null"
                />
              </template>
            </div>
            <p
              v-if="baselineError"
              class="text-sm text-critical-ink"
            >
              {{ baselineError }}
            </p>
            <USwitch
              v-model="useShippedBaseline"
              label="Use the baseline the skill ships"
              :description="baseline
                ? 'Your baseline file is used instead.'
                : 'If the skill has its own .skillspector-baseline.yaml at its top, apply it. Its author wrote it, so it can hide real findings.'"
              class="mt-2"
              :disabled="submitting || !!baseline"
            />
          </div>

          <div
            v-if="maxReferenceDepth"
            class="flex flex-col gap-2"
          >
            <USwitch
              v-model="followReferences"
              label="Follow external references"
              description="Also inspect the Git repositories and raw files the skill links to, and mark what's found there. Slower."
              :disabled="submitting"
            />
            <USelect
              v-if="followReferences && maxReferenceDepth > 1"
              v-model="referenceDepth"
              :items="referenceDepthOptions"
              aria-label="How deep to follow references"
              class="w-full sm:max-w-xs"
              :disabled="submitting"
            />
          </div>
        </div>
      </div>
    </FormRow>

    <div
      v-if="errorMessage || target.trim() || file"
      class="flex flex-col gap-3 bg-muted px-5 py-4 sm:px-7"
    >
      <UAlert
        v-if="errorMessage"
        color="error"
        variant="subtle"
        icon="i-lucide-circle-alert"
        title="Couldn’t start the inspection"
        :description="errorMessage"
      />

      <div
        v-if="target.trim() || file"
        class="text-sm text-muted"
      >
        <p v-if="isMcpServer">
          Checks its MCP Registry entry: pinned packages, a source repository, an active status and
          HTTPS endpoints. Nothing is installed or run.
        </p>
        <p v-else>
          {{ durationHint }} You can leave the page meanwhile: the report is saved to your history.
        </p>
      </div>
    </div>
  </form>
</template>
