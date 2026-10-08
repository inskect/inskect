import type { SettingsResponse } from '../../shared/types/settings'

export default defineEventHandler(async (event) => {
  return await backendFetch<SettingsResponse>(event, '/settings', { fallbackMessage: 'Failed to fetch settings' })
})
