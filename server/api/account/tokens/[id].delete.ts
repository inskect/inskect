export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'Missing token id' })
  }
  await backendFetch(event, `/account/tokens/${encodeURIComponent(id)}`, { method: 'DELETE', fallbackMessage: 'Failed to revoke the API token' })
  return { success: true }
})
