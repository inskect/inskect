import type { LLMProvider } from '../../shared/types/scan'

const NAMES: Record<LLMProvider, string> = {
  anthropic: 'Claude',
  openai: 'OpenAI',
  azure_openai: 'Azure OpenAI',
  openai_compatible: 'OpenAI-compatible APIs',
  nv_build: 'NVIDIA build',
  ollama: 'Ollama',
  claude_cli: 'Claude'
}

// The landing page's description of AI review, as this server allows it (/health's ai_providers and
// allow_custom_ai_url). Unknown, the providers most installs offer.
export function aiReviewText(providers: readonly string[] | undefined, customUrl = true): string {
  const keyed = providers?.filter(provider => provider !== 'claude_cli')
  if (keyed && keyed.length === 1 && keyed[0] === 'anthropic' && !customUrl) {
    return 'A deeper, semantic read of the skill with your own Claude key, saved to your account or pasted once. The skill’s content goes to Anthropic, and only when you ask.'
  }
  const names = keyed?.length ? [...new Set(keyed.map(provider => NAMES[provider as LLMProvider] ?? provider))] : ['Claude', 'OpenAI', 'Ollama']
  const list = names.length === 1 ? names[0] : `${names.slice(0, -1).join(', ')} or ${names.at(-1)}`
  return `A deeper, semantic read of the skill with ${list}, through your own key${customUrl ? ' or endpoint' : ''}. The skill’s content goes to that provider, and only when you ask.`
}
