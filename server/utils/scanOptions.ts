import type { LLMConfig } from '~~/shared/types/scan'

export interface ScanOptionsBody {
  llm?: LLMConfig
  baseline?: string
  useShippedBaseline?: boolean
  transitiveDepth?: number
}

/** The scan form's options, as the API takes them (ScanOptions in backend/app/api/routes/scan.py). */
export function toApiScanOptions({ llm, baseline, useShippedBaseline, transitiveDepth }: ScanOptionsBody) {
  return {
    llm: llm
      ? {
          provider: llm.provider,
          use_saved_key: llm.useSavedKey ?? false,
          api_key: llm.useSavedKey ? undefined : llm.apiKey,
          base_url: llm.baseUrl,
          model: llm.model
        }
      : null,
    // Checked by the API, which explains what's wrong with it.
    baseline: typeof baseline === 'string' ? baseline : null,
    use_shipped_baseline: useShippedBaseline === true,
    transitive_depth: typeof transitiveDepth === 'number' ? transitiveDepth : null
  }
}
