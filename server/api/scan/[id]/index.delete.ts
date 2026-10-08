export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'Missing scan id' })
  }

  await backendFetch(event, `/scan/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    fallbackMessage: 'Failed to delete scan'
  })

  return { success: true }
})
