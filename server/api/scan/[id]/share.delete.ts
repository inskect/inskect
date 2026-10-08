// Revoke the result's link.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'Missing scan id' })
  }
  await backendFetch(event, `/scan/${encodeURIComponent(id)}/share`, {
    method: 'DELETE',
    fallbackMessage: 'Failed to revoke the link'
  })
  return { success: true }
})
