export default defineEventHandler(async (event) => {
  const { target, ...options } = await readBody<ScanOptionsBody & { target?: string }>(event)
  if (!target || typeof target !== 'string') {
    throw createError({ statusCode: 400, statusMessage: 'Missing "target" in request body' })
  }

  return await backendFetch<{ id: string, status: string }>(event, '/scan', {
    method: 'POST',
    body: { target, ...toApiScanOptions(options) },
    fallbackMessage: 'Failed to queue scan'
  })
})
