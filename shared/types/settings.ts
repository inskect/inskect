export interface SettingsResponse {
  scan_retention_days: number | null
  // Whether visitors may create their own account; always false without accounts.
  allow_signup: boolean
  // Whether new scans are refused, for everyone.
  scans_paused: boolean
  // Per signed-in user other than admins; null means no limit.
  daily_scan_quota: number | null
  concurrent_scan_quota: number | null
}

export interface UsageResponse {
  scans_paused: boolean
  // False for admins, and without accounts: no quota applies to them.
  quotas_apply: boolean
  // Scans started in the last 24 hours, including deleted ones.
  scans_today: number
  daily_scan_quota: number | null
  active_scans: number
  concurrent_scan_quota: number | null
  // Everyone's, without accounts.
  ai_usage: AIUsage
}

// AI tokens over the last `days` days, from scans still in history.
export interface AIUsage {
  days: number
  // Scans with AI usage recorded.
  scans: number
  input_tokens: number
  output_tokens: number
  cached_tokens: number
}
