// Put the shared result on its target's status badge.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'Missing scan id' })
  }
  await backendFetch(event, `/scan/${encodeURIComponent(id)}/badge`, {
    method: 'POST',
    // A private repository's scan is only shared, or badged, once its owner confirms.
    body: { confirm_private: await confirmedPrivate(event) },
    fallbackMessage: 'Failed to add the result to the badge'
  })
  return { success: true }
})
