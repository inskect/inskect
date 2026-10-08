import { describe, expect, it } from 'vitest'
import { addNonce, contentSecurityPolicy, cspViolations, securityHeaders } from '../shared/utils/securityHeaders'

const directives = (policy: string) => Object.fromEntries(policy.split('; ').map((part) => {
  const [name, ...values] = part.split(' ')
  return [name, values]
}))

describe('contentSecurityPolicy', () => {
  it('runs scripts from this server, or inline with the nonce, and nothing else', () => {
    const policy = directives(contentSecurityPolicy({ nonce: 'abc' }))
    expect(policy['script-src']).toEqual(['\'self\'', '\'nonce-abc\''])
    expect(policy['default-src']).toEqual(['\'self\''])
    expect(policy['object-src']).toEqual(['\'none\''])
    expect(policy['frame-ancestors']).toEqual(['\'none\''])
    expect(JSON.stringify(policy['script-src'])).not.toContain('unsafe')
  })

  it('lets requests reach this server, and only the origins configured besides', () => {
    expect(directives(contentSecurityPolicy({ nonce: 'abc' }))['connect-src']).toEqual(['\'self\''])
    expect(directives(contentSecurityPolicy({ nonce: 'abc', connectSources: ['https://files.example'] }))['connect-src']).toEqual(['\'self\'', 'https://files.example'])
  })
})

describe('securityHeaders', () => {
  const page = { nonce: 'abc', path: '/history', https: true, reportOnly: false }

  it('sends every header, and HSTS over HTTPS only', () => {
    const headers = securityHeaders(page)
    expect(Object.keys(headers).sort()).toEqual([
      'Content-Security-Policy', 'Permissions-Policy', 'Referrer-Policy', 'Reporting-Endpoints',
      'Strict-Transport-Security', 'X-Content-Type-Options', 'X-Frame-Options'
    ])
    expect(headers['X-Frame-Options']).toBe('DENY')
    expect(securityHeaders({ ...page, https: false })).not.toHaveProperty('Strict-Transport-Security')
  })

  it('only reports the policy when asked', () => {
    const headers = securityHeaders({ ...page, reportOnly: true })
    expect(headers).toHaveProperty('Content-Security-Policy-Report-Only')
    expect(headers).not.toHaveProperty('Content-Security-Policy')
  })

  it('sends no referrer from a shared result, and none to other sites from anywhere', () => {
    expect(securityHeaders({ ...page, path: '/shared/token' })['Referrer-Policy']).toBe('no-referrer')
    expect(securityHeaders(page)['Referrer-Policy']).toBe('same-origin')
  })
})

describe('addNonce', () => {
  it('marks every script tag, and nothing that only looks like one', () => {
    const html = '<script>a()</script><script type="module" src="/x.js"></script><scripts></scripts><noscript>no</noscript>'
    expect(addNonce(html, 'n')).toBe('<script nonce="n">a()</script><script nonce="n" type="module" src="/x.js"></script><scripts></scripts><noscript>no</noscript>')
  })
})

describe('cspViolations', () => {
  it('reads report-uri reports, keeping only origins and paths', () => {
    const body = { 'csp-report': { 'effective-directive': 'script-src-elem', 'blocked-uri': 'https://evil.example/x.js?k=1', 'document-uri': 'https://s.example/scan/abc?x=1' } }
    expect(cspViolations(body)).toEqual([{ directive: 'script-src-elem', blocked: 'https://evil.example', page: '/scan/abc' }])
  })

  it('reads Reporting API reports, and never logs a shared result’s token', () => {
    const body = [{ type: 'csp-violation', body: { effectiveDirective: 'script-src-elem', blockedURL: 'inline', documentURL: 'https://s.example/shared/secret-token' } }]
    expect(cspViolations(body)).toEqual([{ directive: 'script-src-elem', blocked: 'inline', page: '/shared/…' }])
  })

  it('ignores anything else', () => {
    expect(cspViolations(null)).toEqual([])
    expect(cspViolations('nope')).toEqual([])
    expect(cspViolations([1, null])).toEqual([])
  })
})
