// Disconnect GitHub: its tokens are deleted, and revoked at GitHub.
export default defineEventHandler(async (event) => {
  await backendFetch(event, '/account/connections/github', { method: 'DELETE', fallbackMessage: 'Couldn’t disconnect GitHub' })
  return { success: true }
})
