import type { SignInMethods } from '~~/shared/types/auth'

// How the signed-in user can sign in: a password, GitHub (backend/app/auth/github_sign_in.py).
export default defineEventHandler(event => backendFetch<SignInMethods>(event, '/account/sign-in-methods', {
  fallbackMessage: 'Failed to load your sign-in methods'
}))
