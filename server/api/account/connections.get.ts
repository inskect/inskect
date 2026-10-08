// The user's code host connections, to scan private repositories (backend/app/repo_connections.py).
export default defineEventHandler(async (event) => {
  return await backendFetch(event, '/account/connections', { fallbackMessage: 'Failed to load your connections' })
})
