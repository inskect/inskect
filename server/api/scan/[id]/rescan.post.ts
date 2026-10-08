// Scan a scan's target again, as it was scanned; the result is compared with this one.
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'Missing scan id' })
  }

  return await backendFetch<{ id: string, status: string }>(event, `/scan/${encodeURIComponent(id)}/rescan`, {
    method: 'POST',
    fallbackMessage: 'Failed to rescan'
  })
})
