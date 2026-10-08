// Ends every other session of the signed-in user and revokes their API tokens; this session stays.
export default defineEventHandler(event => backendFetch<{ tokens_revoked: number }>(event, '/auth/sign-out-everywhere', {
  method: 'POST',
  fallbackMessage: 'Couldn’t sign out everywhere'
}))
