export default defineEventHandler(async (event) => {
  const { code } = await readBody<{ code?: string }>(event)

  if (!code) {
    throw createError({ statusCode: 400, statusMessage: 'Missing "code" in request body' })
  }

  return await backendFetch<{ success: boolean, output: string }>(event, '/admin/claude-login/complete', {
    method: 'POST',
    body: { code },
    fallbackMessage: 'Failed to complete login'
  })
})
