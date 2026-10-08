// A shared result's report as a download: skillspector's JSON, or SARIF (?format=sarif).
export default defineEventHandler(async (event) => {
  const token = getRouterParam(event, 'token')
  if (!token) {
    throw createError({ statusCode: 400, statusMessage: 'Missing link' })
  }
  const { format } = getQuery<{ format?: string }>(event)
  return await backendDownload(event, `/shared/${encodeURIComponent(token)}/export`, { format: format === 'sarif' ? 'sarif' : 'json' }, 'Failed to export the report')
})
