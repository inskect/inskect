export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  const tokenId = getRouterParam(event, 'tokenId')
  if (!id || !tokenId) {
    throw createError({ statusCode: 400, statusMessage: 'Missing user or token id' })
  }
  await backendFetch(event, `/admin/users/${encodeURIComponent(id)}/tokens/${encodeURIComponent(tokenId)}`, {
    method: 'DELETE',
    fallbackMessage: 'Failed to revoke the API token'
  })
  return { success: true }
})
