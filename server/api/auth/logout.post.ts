export default defineEventHandler(async (event) => {
  // Sign out locally even if the API is unreachable: the cookie is what keeps the session.
  await backendFetch(event, '/auth/logout', { method: 'POST', fallbackMessage: 'Failed to sign out' }).catch(() => {})
  clearSessionToken(event)
  return { success: true }
})
