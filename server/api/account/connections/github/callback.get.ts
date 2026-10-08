// Where GitHub sends the browser back after authorizing the app (PUBLIC_URL + this path is the
// GitHub App's callback URL). The API checks the state is this session's, and keeps the tokens.
export default defineEventHandler(async (event) => {
  const { code, state, error, error_description: description } = getQuery<Record<string, string | undefined>>(event)
  const back = (query: string) => sendRedirect(event, `/account?${query}`, 302)
  if (error || !code || !state) {
    return back(`connection_error=${encodeURIComponent(description || 'GitHub didn’t connect: try again')}`)
  }
  try {
    await backendFetch(event, '/account/connections/github/callback', {
      method: 'POST',
      body: { code, state },
      fallbackMessage: 'Couldn’t connect GitHub'
    })
    return back('connected=github')
  } catch (failure) {
    const message = (failure as { statusMessage?: string }).statusMessage ?? 'Couldn’t connect GitHub'
    return back(`connection_error=${encodeURIComponent(message)}`)
  }
})
