import type { AIUsage } from './settings'
import type { Recommendation } from './scan'
import type { User } from './auth'

export interface DirectoryUser extends User {
  scan_count: number
}

export interface ActivityEntry {
  id: number
  created_at: number
  actor_id: string | null
  actor_email: string | null
  action: string
  target_id: string | null
  target_email: string | null
  detail: string | null
}

export interface UserDetail {
  user: DirectoryUser
  recent_scans: {
    id: string
    target: string
    status: string
    created_at: number
    recommendation: Recommendation | null
    risk_score: number | null
    report_no?: number | null
  }[]
  activity: ActivityEntry[]
  ai_usage: AIUsage
  quotas: UserQuotas
}

// A user's scan quotas (backend/app/quotas.py): their own (null follows the server's, 0 is no
// limit), the server's as it applies now (null: no limit), and today's use.
export interface UserQuotas {
  daily_scan_quota: number | null
  concurrent_scan_quota: number | null
  server_daily_scan_quota: number | null
  server_concurrent_scan_quota: number | null
  // False for an admin: quotas don't apply to them.
  applies: boolean
  scans_today: number
  active_scans: number
}

export interface Overview {
  auth: 'none' | 'accounts'
  email_enabled: boolean
  signup_allowed: boolean
  // "new" and "recent" count the last 7 days.
  users: { total: number, admins: number, suspended: number, new: number }
  scans: { total: number, recent: number, do_not_install: number, caution: number, safe: number, failed: number, active: number }
  recent_activity: ActivityEntry[]
  health: Health
}

// What went wrong over the last `hours` (backend/app/monitoring.py).
export interface Health {
  hours: number
  finished: number
  failed: number
  last_error: { kind: 'scan_failed', message: string | null, at: number, scan_id: string | null } | null
  // Where alerts go; empty when they aren't set up.
  alert_channels: ('webhook' | 'email')[]
  // The web app is behind a proxy it doesn't trust: every visitor shares its rate limits.
  proxy_warning: string | null
  last_alert: { rule: string | null, title: string | null, at: number } | null
  // Events of the kinds an extension's alert rules label, over the same hours.
  events: { kind: string, label: string, count: number }[]
}

export interface ActivityPage {
  items: ActivityEntry[]
  total: number
}

// The monitoring page (backend/app/api/routes/backoffice.py).
export interface AlertRule {
  name: string
  title: string
  // The event that makes it check, and what an extension's rule calls those events.
  kind: string
  label: string | null
  condition: string
  cooldown_minutes: number
  // False for a rule that doesn't apply here, such as one about accounts without them.
  applies: boolean
  tripped: boolean
  current: string | null
  last_alert_at: number | null
  // Set while the rule waits out its cooldown after an alert.
  quiet_until: number | null
}

export interface Monitoring {
  health: Health
  rules: AlertRule[]
  // The webhook by its host only: its path is its secret.
  channels: { webhook_host: string | null, emails: string[], email_ready: boolean }
}

// Built in; an extension records kinds of its own.
export type MonitorEventKind = 'scan_failed' | 'sign_in_locked' | 'alert_sent' | (string & {})
// Built in, or a kind an extension's alert rule labels.
export type MonitorEventFilter = 'all' | 'failures' | 'lockouts' | 'alerts' | (string & {})

export interface MonitorEvent {
  id: number
  created_at: number
  kind: MonitorEventKind
  message: string | null
  scan_id: string | null
  count: number
}

export interface MonitorEventPage {
  items: MonitorEvent[]
  total: number
}
