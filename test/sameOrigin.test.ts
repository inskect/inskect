import { describe, expect, it } from 'vitest'
import { localPath } from '../shared/utils/redirect'
import { isCrossSiteRequest } from '../shared/utils/sameOrigin'

const post = { method: 'POST', path: '/api/account/tokens', hasApiToken: false, host: 'inskect.example.com' }

describe('isCrossSiteRequest', () => {
  it('refuses a state-changing request from another site, or a sibling subdomain', () => {
    expect(isCrossSiteRequest({ ...post, secFetchSite: 'cross-site' })).toBe(true)
    expect(isCrossSiteRequest({ ...post, secFetchSite: 'same-site' })).toBe(true)
    expect(isCrossSiteRequest({ ...post, origin: 'https://evil.example' })).toBe(true)
    expect(isCrossSiteRequest({ ...post, origin: 'https://other.example.com' })).toBe(true)
    expect(isCrossSiteRequest({ ...post, origin: 'null' })).toBe(true)
  })

  it('lets this site’s own pages through, over a proxy that changes the scheme too', () => {
    expect(isCrossSiteRequest({ ...post, secFetchSite: 'same-origin' })).toBe(false)
    expect(isCrossSiteRequest({ ...post, origin: 'https://inskect.example.com' })).toBe(false)
    expect(isCrossSiteRequest({ ...post, origin: 'http://inskect.example.com' })).toBe(false)
  })

  it('lets scripts with an API token through, from anywhere', () => {
    expect(isCrossSiteRequest({ ...post, path: '/api/scan', hasApiToken: true, secFetchSite: 'cross-site' })).toBe(false)
  })

  it('leaves reads, pages, CSP reports and non-browsers alone', () => {
    expect(isCrossSiteRequest({ ...post, method: 'GET', secFetchSite: 'cross-site' })).toBe(false)
    expect(isCrossSiteRequest({ ...post, path: '/scan/abc', secFetchSite: 'cross-site' })).toBe(false)
    expect(isCrossSiteRequest({ ...post, path: '/api/csp-report', secFetchSite: 'cross-site' })).toBe(false)
    expect(isCrossSiteRequest({ ...post })).toBe(false)
  })
})

describe('localPath', () => {
  it('keeps a path on this site', () => {
    expect(localPath('/history')).toBe('/history')
    expect(localPath('/scan/abc?skill=1#top')).toBe('/scan/abc?skill=1#top')
  })

  it('refuses anything that could lead to another site', () => {
    for (const target of ['https://evil.example', '//evil.example', '/\\evil.example', '/\\/evil.example', '/\t/evil.example', ' /x', 'history', '', undefined, ['/x']]) {
      expect(localPath(target)).toBeNull()
    }
  })
})
