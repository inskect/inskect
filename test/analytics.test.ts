import { describe, expect, it } from 'vitest'
import { anonymousUrl, routePattern } from '../app/utils/analytics'

describe('routePattern', () => {
  it('names a route by its pattern, never its values', () => {
    expect(routePattern('/scan/:id()')).toBe('/scan/[id]')
    expect(routePattern('/scan/:id')).toBe('/scan/[id]')
    expect(routePattern('/shared/:token()')).toBe('/shared/[token]')
    expect(routePattern('/admin/users/:id()')).toBe('/admin/users/[id]')
    expect(routePattern('/:path(.*)*')).toBe('/[...path]')
    expect(routePattern('/history')).toBe('/history')
  })

  it('names a page that matched no route', () => {
    expect(routePattern(undefined)).toBe('/[not-found]')
  })
})

describe('anonymousUrl', () => {
  const patterns: Record<string, string> = { '/shared/abc123secret': '/shared/[token]', '/': '/' }
  const patternOf = (path: string) => patterns[path] ?? '/[not-found]'

  it('keeps the origin and the pattern, and drops the query and hash', () => {
    expect(anonymousUrl('https://s.example/shared/abc123secret#findings', patternOf)).toBe('https://s.example/shared/[token]')
    expect(anonymousUrl('https://s.example/?target=https%3A%2F%2Fgithub.com%2Facme%2Fprivate', patternOf)).toBe('https://s.example/')
  })

  it('sends nothing it can’t parse', () => {
    expect(anonymousUrl('not a url', patternOf)).toBe('/')
  })
})
