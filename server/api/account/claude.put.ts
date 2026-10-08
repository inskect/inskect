import type { ClaudeKeyStatus } from '~~/shared/types/auth'

export default defineEventHandler(async (event) => {
  const { apiKey } = await readBody<{ apiKey?: string }>(event)
  if (!apiKey) {
    throw createError({ statusCode: 400, statusMessage: 'Paste your Anthropic API key' })
  }
  return await backendFetch<ClaudeKeyStatus>(event, '/account/claude', {
    method: 'PUT',
    body: { api_key: apiKey },
    fallbackMessage: 'Failed to save your Claude key'
  })
})
