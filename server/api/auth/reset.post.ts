export default defineEventHandler(async (event) => {
  const { token, password } = await readBody<{ token?: string, password?: string }>(event)
  if (!token || !password) {
    throw createError({ statusCode: 400, statusMessage: 'Enter a new password' })
  }
  return await startSession(event, '/auth/reset', { token, password }, 'Failed to reset the password')
})
