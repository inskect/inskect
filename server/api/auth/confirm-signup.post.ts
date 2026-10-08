export default defineEventHandler(async (event) => {
  const { token } = await readBody<{ token?: string }>(event)
  if (!token) {
    throw createError({ statusCode: 400, statusMessage: 'Open the full link you were emailed' })
  }
  return await startSession(event, '/auth/confirm-signup', { token }, 'Failed to create your account')
})
