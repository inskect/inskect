export default defineEventHandler(async (event) => {
  const { email } = await readBody<{ email?: string }>(event)
  if (!email) {
    throw createError({ statusCode: 400, statusMessage: 'Enter your email address' })
  }
  return await backendFetch<{ accepted: boolean }>(event, '/auth/forgot', {
    method: 'POST',
    body: { email },
    fallbackMessage: 'Failed to request a reset email'
  })
})
