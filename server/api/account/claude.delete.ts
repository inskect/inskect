export default defineEventHandler(async (event) => {
  await backendFetch(event, '/account/claude', { method: 'DELETE', fallbackMessage: 'Failed to disconnect your Claude key' })
  return { success: true }
})
