import type { AuthSession } from '../../shared/types/auth'

// One shared fetch of who's signed in, reused by the route guard, the header and the pages.
export function useAuth() {
  // useFetch forwards the browser's cookies on server-side renders.
  const { data: session, refresh } = useFetch<AuthSession>('/api/auth/session', { key: 'auth-session' })

  const accounts = computed(() => session.value?.auth === 'accounts')
  const user = computed(() => session.value?.user ?? null)
  // Without accounts every visitor has full access, admin page included.
  const isAdmin = computed(() => !accounts.value || user.value?.role === 'admin')

  // After signing in or out, what each page shows depends on who's looking: drop cached data.
  async function onSessionChange() {
    clearNuxtData(key => key !== 'auth-session')
    await refresh()
  }

  async function signOut() {
    await $fetch('/api/auth/logout', { method: 'POST' })
    await onSessionChange()
    await navigateTo('/login')
  }

  return { session, accounts, user, isAdmin, refresh, onSessionChange, signOut }
}
