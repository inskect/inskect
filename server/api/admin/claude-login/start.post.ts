export default defineEventHandler(async (event) => {
  return await backendFetch<{ url: string }>(event, '/admin/claude-login/start', {
    method: 'POST',
    fallbackMessage: 'Failed to start login'
  })
})
