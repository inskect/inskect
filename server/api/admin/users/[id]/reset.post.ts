export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'Missing user id' })
  }

  const { path, expires_at: expiresAt } = await backendFetch<{ path: string, expires_at: number }>(
    event,
    `/admin/users/${encodeURIComponent(id)}/reset`,
    { method: 'POST', fallbackMessage: 'Failed to create a reset link' }
  )
  // The address the admin is using right now, so the link opens this same site.
  const { origin } = getRequestURL(event, { xForwardedHost: true, xForwardedProto: true })
  return { url: new URL(path, origin).toString(), expiresAt }
})
