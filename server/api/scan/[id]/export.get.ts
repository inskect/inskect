// The report as a download: skillspector's JSON, or SARIF (?format=sarif).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'Missing scan id' })
  }
  const { format } = getQuery<{ format?: string }>(event)
  return await backendDownload(event, `/scan/${encodeURIComponent(id)}/export`, { format: format === 'sarif' ? 'sarif' : 'json' }, 'Failed to export the report')
})
