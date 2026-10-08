// This server's public address, for URLs that must be absolute, like the link preview image's:
// NUXT_PUBLIC_SITE_URL when set, otherwise the address the page was requested at. Behind a trusted
// reverse proxy (NUXT_TRUST_PROXY), that's the host and protocol it forwarded, not its own.
export function useSiteUrl(): string {
  const config = useRuntimeConfig()
  if (config.public.siteUrl) return config.public.siteUrl.replace(/\/+$/, '')
  const trusted = import.meta.server && !!config.trustProxy
  return useRequestURL({ xForwardedHost: trusted, xForwardedProto: trusted }).origin
}
