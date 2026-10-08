// Send a test alert to every channel set up (backend/app/monitoring.py).
export default defineEventHandler(async (event) => {
  return await backendFetch<{ channels: string[] }>(event, '/admin/alerts/test', {
    method: 'POST',
    fallbackMessage: 'Failed to send the test alert'
  })
})
