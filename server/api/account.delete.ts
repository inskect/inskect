// Delete the signed-in user's account and everything of theirs (backend/app/accounts.py), once they
// confirm with their password. The session cookie goes with it.
export default defineEventHandler(async (event) => {
  const { password } = await readBody<{ password?: string }>(event)
  await backendFetch(event, '/account', {
    method: 'DELETE',
    body: { password: typeof password === 'string' ? password : '' },
    fallbackMessage: 'Couldn’t delete your account'
  })
  clearSessionToken(event)
  return { success: true }
})
