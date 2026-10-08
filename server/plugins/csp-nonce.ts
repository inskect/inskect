// The page's scripts carry the response's nonce, which its Content-Security-Policy allows
// (server/middleware/security-headers.ts): Nuxt writes its config, the import map and the color
// mode's script inline, and the policy refuses any other inline script.
export default defineNitroPlugin((nitro) => {
  nitro.hooks.hook('render:html', (html, { event }) => {
    const nonce = event.context.cspNonce as string | undefined
    if (!nonce) return
    for (const part of ['head', 'bodyPrepend', 'body', 'bodyAppend'] as const) {
      html[part] = html[part].map(chunk => addNonce(chunk, nonce))
    }
  })
})
