// Take the result off its target's status badge.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'Missing scan id' })
  }
  await backendFetch(event, `/scan/${encodeURIComponent(id)}/badge`, {
    method: 'DELETE',
    fallbackMessage: 'Failed to take the result off the badge'
  })
  return { success: true }
})
