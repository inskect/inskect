export default defineEventHandler(async (event) => {
  const { currentPassword, newPassword, revokeTokens } = await readBody<{ currentPassword?: string, newPassword?: string, revokeTokens?: boolean }>(event)

  await backendFetch(event, '/auth/password', {
    method: 'POST',
    // The API tokens go too, unless kept.
    body: { current_password: currentPassword, new_password: newPassword, revoke_tokens: revokeTokens !== false },
    fallbackMessage: 'Failed to change the password'
  })
  return { success: true }
})
