import { describe, expect, it } from 'vitest'
import { isIndexable, robotsTxt, sitemapXml } from '../shared/utils/seo'

describe('isIndexable', () => {
  it('indexes the public pages only', () => {
    for (const path of ['/', '/signup', '/signup/']) expect(isIndexable(path)).toBe(true)
    for (const path of ['/login', '/forgot-password', '/reset-password', '/confirm-signup', '/history', '/account', '/admin', '/admin/users', '/scan/abc', '/shared/abc', '/nope', '/legal', '/privacy', '/terms']) {
      expect(isIndexable(path)).toBe(false)
    }
  })
})

describe('robotsTxt', () => {
  it('keeps crawlers out of the private pages', () => {
    const robots = robotsTxt(null)
    expect(robots).toMatch(/^User-agent: \*$/m)
    for (const path of ['/admin', '/account', '/history', '/scan/', '/api/']) expect(robots).toContain(`Disallow: ${path}\n`)
  })

  it('points to the sitemap only once the public address is set', () => {
    expect(robotsTxt(null)).not.toContain('Sitemap:')
    expect(robotsTxt('https://inskect.example.com')).toContain('Sitemap: https://inskect.example.com/sitemap.xml\n')
  })
})

describe('pages an extending app adds', () => {
  it('are indexable and listed in the sitemap', () => {
    expect(isIndexable('/terms', ['/terms'])).toBe(true)
    expect(isIndexable('/terms/', ['/terms'])).toBe(true)
    expect(isIndexable('/terms')).toBe(false)
    const locs = (xml: string) => [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map(m => m[1])
    expect(locs(sitemapXml({ siteUrl: 'https://s.example', signupOpen: false, publicPages: ['/terms'] })))
      .toEqual(['https://s.example/', 'https://s.example/terms'])
  })
})

describe('sitemapXml', () => {
  const locs = (xml: string) => [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map(match => match[1])

  it('lists the home page, and sign-up when it’s open', () => {
    expect(locs(sitemapXml({ siteUrl: 'https://s.example', signupOpen: false }))).toEqual(['https://s.example/'])
    expect(locs(sitemapXml({ siteUrl: 'https://s.example', signupOpen: true }))).toEqual(['https://s.example/', 'https://s.example/signup'])
  })

  it('is well-formed XML, escaped', () => {
    const xml = sitemapXml({ siteUrl: 'https://s.example/a&b', signupOpen: false })
    expect(xml.startsWith('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')).toBe(true)
    expect(xml).toContain('<loc>https://s.example/a&amp;b/</loc>')
  })
})
