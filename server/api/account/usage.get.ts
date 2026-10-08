import type { UsageResponse } from '~~/shared/types/settings'

export default defineEventHandler(async (event) => {
  return await backendFetch<UsageResponse>(event, '/account/usage', { fallbackMessage: 'Failed to load your usage' })
})
