import { createHash, randomBytes } from 'node:crypto'

// Off to GitHub to sign in or up (?intent=sign_in), or to link it to the signed-in account
// (?intent=link): the nonce stays here, in a cookie, and only its hash goes into GitHub's state.
export default defineEventHandler(async (event) => {
  const link = getQuery(event).intent === 'link'
  const nonce = randomBytes(32).toString('base64url')
  setGitHubNonce(event, nonce)
  try {
    const { url } = await backendFetch<{ url: string }>(event, link ? '/account/sign-in-methods/github/start' : '/auth/github/start', {
      method: 'POST',
      body: { nonce_hash: createHash('sha256').update(nonce).digest('hex') },
      fallbackMessage: 'Couldn’t start signing in with GitHub'
    })
    return sendRedirect(event, url, 302)
  } catch (error) {
    return gitHubFailure(event, (error as { statusMessage?: string }).statusMessage || 'Couldn’t start signing in with GitHub')
  }
})
