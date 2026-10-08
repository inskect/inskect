// A read-only link to the result: the same one when it's shared already and kept, a new one with
// `renew` (backend/app/sharing.py).
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, 'id')
  if (!id) {
    throw createError({ statusCode: 400, statusMessage: 'Missing scan id' })
  }
  const body = await readBody<{ renew?: unknown } | undefined>(event).catch(() => undefined)
  return await backendFetch<{ token: string | null, kept: boolean }>(event, `/scan/${encodeURIComponent(id)}/share`, {
    method: 'POST',
    body: {
      // A private repository's scan is only shared, or badged, once its owner confirms.
      confirm_private: await confirmedPrivate(event),
      renew: body?.renew === true
    },
    fallbackMessage: 'Failed to share the result'
  })
})
