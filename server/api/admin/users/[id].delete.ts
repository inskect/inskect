export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'Missing user id' })
  }

  await backendFetch(event, `/admin/users/${encodeURIComponent(id)}`, {
    method: 'DELETE',
    fallbackMessage: 'Failed to remove the user'
  })
  return { success: true }
})
