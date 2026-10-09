// Pages a signed-out visitor may open when accounts are on, besides app.config's site.publicPages.
// `/` shows the landing page to them.
const PUBLIC_PATHS = new Set(['/', '/login', '/signup', '/forgot-password', '/reset-password', '/confirm-signup'])
// Pages meant only for signed-out visitors: signed-in users go back to where they were heading.
const SIGNED_OUT_ONLY = new Set(['/login', '/signup', '/forgot-password'])

// With accounts on, everything but the public pages needs a session, and /admin needs the admin role.
export default defineNuxtRouteMiddleware(async (to) => {
  const { session, accounts, user, isAdmin, refresh } = useAuth()
  const { site } = useAppConfig()
  if (!session.value) await refresh()
  if (!session.value) return // API unreachable: let the page show its own error.
  // No such page: a 404 for everyone, not a redirect to sign in.
  if (to.matched.length === 0) return

  if (SIGNED_OUT_ONLY.has(to.path)) {
    if (!accounts.value || user.value) return navigateTo(localPath(to.query.redirect) ?? '/')
    return
  }
  // A shared result is for anyone with its link.
  if (accounts.value && !user.value && !PUBLIC_PATHS.has(to.path) && !site.publicPages.includes(to.path) && !to.path.startsWith('/shared/')) {
    return navigateTo({ path: '/login', query: { redirect: to.fullPath } })
  }
  if (to.path.startsWith('/admin') && !isAdmin.value) return navigateTo('/')
})
