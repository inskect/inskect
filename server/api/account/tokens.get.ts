import type { ApiToken } from '~~/shared/types/auth'

export default defineEventHandler(async (event) => {
  return await backendFetch<ApiToken[]>(event, '/account/tokens', { fallbackMessage: 'Failed to fetch your API tokens' })
})
