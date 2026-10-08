// GitHub stops signing in to the account; never its last way in, which the API refuses.
export default defineEventHandler(async (event) => {
  await backendFetch(event, '/account/sign-in-methods/github', { method: 'DELETE', fallbackMessage: 'Couldn’t unlink GitHub' })
  return null
})
