import type { ClaudeKeyStatus } from '../../../shared/types/auth'

export default defineEventHandler(async (event) => {
  return await backendFetch<ClaudeKeyStatus | null>(event, '/account/claude', { fallbackMessage: 'Failed to load your Claude key' })
})
