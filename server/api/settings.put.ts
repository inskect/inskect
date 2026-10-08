import type { SettingsResponse } from '../../shared/types/settings'

export default defineEventHandler(async (event) => {
  const body = await readBody<{
    scanRetentionDays?: number | null
    allowSignup?: boolean
    scansPaused?: boolean
    dailyScanQuota?: number | null
    concurrentScanQuota?: number | null
  }>(event)

  // Only what was sent changes. A quota sent as null means no limit.
  const update: Record<string, unknown> = {}
  if ('scanRetentionDays' in body) update.scan_retention_days = body.scanRetentionDays ?? null
  if (typeof body.allowSignup === 'boolean') update.allow_signup = body.allowSignup
  if (typeof body.scansPaused === 'boolean') update.scans_paused = body.scansPaused
  if ('dailyScanQuota' in body) update.daily_scan_quota = body.dailyScanQuota ?? null
  if ('concurrentScanQuota' in body) update.concurrent_scan_quota = body.concurrentScanQuota ?? null

  return await backendFetch<SettingsResponse>(event, '/settings', {
    method: 'PUT',
    body: update,
    fallbackMessage: 'Failed to update settings'
  })
})
