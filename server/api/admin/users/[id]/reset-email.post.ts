export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'Missing user id' })
  }
  await backendFetch(event, `/admin/users/${encodeURIComponent(id)}/reset-email`, {
    method: 'POST',
    fallbackMessage: 'Failed to send the reset email'
  })
  return { success: true }
})
