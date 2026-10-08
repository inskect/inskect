// Connect GitHub: the browser goes on to GitHub to authorize the app, which sends it back to the
// callback (callback.get.ts) with a state only this user's session can redeem.
export default defineEventHandler(async (event) => {
  try {
    const { url } = await backendFetch<{ url: string }>(event, '/account/connections/github/start', {
      fallbackMessage: 'Couldn’t start connecting GitHub'
    })
    return sendRedirect(event, url, 302)
  } catch (error) {
    const message = (error as { statusMessage?: string }).statusMessage ?? 'Couldn’t start connecting GitHub'
    return sendRedirect(event, `/account?connection_error=${encodeURIComponent(message)}`, 302)
  }
})
