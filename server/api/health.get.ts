// Fetched on every home page and scan form view: answered from a cache of a few seconds.
// ?fresh=1 skips it, for the backoffice right after it changed the server's Claude login.
export default defineCachedEventHandler(async () => {
  const { apiBase } = useRuntimeConfig()

  return await $fetch<{
    status: string
    // This server's Inskect release, from its tag; "dev" when built from a checkout.
    version: string
    auth: 'none' | 'accounts' | null
    skillspector_version: string
    llm_available: boolean
    claude_cli_available: boolean
    // The AI providers scans may use, and whether a scan may set its own endpoint.
    ai_providers: string[]
    allow_custom_ai_url: boolean
    // The deepest a scan may follow a skill's external references; 0 when it can't.
    transitive_max_depth: number
    // Where an uploaded file goes (backend/app/uploads.py); null when uploads are off.
    upload_store: 'local' | null
    max_upload_bytes: number
  }>('/health', { baseURL: apiBase, headers: apiHeaders() }).catch(() => ({
    status: 'down',
    version: 'unknown',
    auth: null,
    skillspector_version: 'unknown',
    llm_available: false,
    claude_cli_available: false,
    ai_providers: [] as string[],
    allow_custom_ai_url: true,
    transitive_max_depth: 0,
    upload_store: null,
    max_upload_bytes: 0
  }))
}, {
  name: 'health',
  getKey: () => 'health',
  maxAge: 5,
  shouldBypassCache: event => getQuery(event).fresh !== undefined
})
