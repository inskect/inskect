export type AuthMode = 'none' | 'accounts'

export type UserRole = 'admin' | 'user'

export type UserStatus = 'active' | 'suspended'

export interface User {
  id: string
  email: string
  role: UserRole
  status: UserStatus
  created_at: number
  last_login_at: number | null
}

export interface AuthSession {
  auth: AuthMode
  user: User | null
  needs_setup: boolean
  signup_allowed: boolean
  // "Forgot password?" by email is available.
  email_enabled: boolean
  // Users can save their own Claude key, and the signed-in user's saved key, if any.
  claude_key_available: boolean
  claude_key: ClaudeKeyStatus | null
  // What this server offers (backend/app/api/routes/auth.py's ServerFeatures).
  features: ServerFeatures
}

export interface ServerFeatures {
  uploads: boolean
  // Connecting GitHub to scan private repositories.
  github: boolean
  // Each user's scans per 24 hours and at once; null for no limit.
  daily_quota: number | null
  concurrent_quota: number | null
}

export interface ClaudeKeyStatus {
  provider: 'anthropic'
  // The last characters of the key, e.g. "…a1b2"; the key itself never comes back.
  hint: string
  updated_at: number
}

// A personal API token as listed (backend/app/auth/api_tokens.py): never the token itself.
export interface ApiToken {
  id: string
  name: string
  // Its first characters, e.g. "sst_a1B2c3", to tell tokens apart.
  prefix: string
  scopes: string[]
  created_at: number
  expires_at: number | null
  last_used_at: number | null
}

// Only the response that creates a token holds it, this once.
export interface CreatedApiToken extends ApiToken {
  token: string
}

// How the signed-in user can sign in (backend/app/api/routes/account.py's SignInMethods).
export interface SignInMethods {
  password: boolean
  // The login is only a label: GitHub's numeric ID is what signs in.
  github: { login: string | null, linked_at: number } | null
  github_available: boolean
}
