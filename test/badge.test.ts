import { describe, expect, it } from 'vitest'
import { badgeMarkdown, badgeMessage, renderBadge } from '../shared/utils/badge'

// 2026-10-02T09:00:00Z
const SCANNED_AT = 1790931600

describe('badgeMessage', () => {
  it('shows the verdict and the inspection’s date, in its stamp colour', () => {
    expect(badgeMessage({ recommendation: 'SAFE', scanned_at: SCANNED_AT })).toEqual({ text: 'passed · 2026-10-02', color: '#1E7A3C' })
    expect(badgeMessage({ recommendation: 'CAUTION', scanned_at: SCANNED_AT }).text).toBe('review first · 2026-10-02')
    expect(badgeMessage({ recommendation: 'DO_NOT_INSTALL', scanned_at: SCANNED_AT })).toEqual({ text: 'rejected · 2026-10-02', color: '#B3261E' })
  })

  it('reads not inspected without an inspection on the badge', () => {
    expect(badgeMessage({})).toEqual({ text: 'not inspected', color: '#5A5F6B' })
    expect(badgeMessage({ recommendation: null, scanned_at: SCANNED_AT }).text).toBe('not inspected')
  })
})

describe('renderBadge', () => {
  it('is an SVG with the label and message, sized to them', () => {
    const svg = renderBadge({ recommendation: 'DO_NOT_INSTALL', scanned_at: SCANNED_AT })
    expect(svg.startsWith('<svg xmlns="http://www.w3.org/2000/svg"')).toBe(true)
    expect(svg).toContain('aria-label="inskect: rejected · 2026-10-02"')
    expect(svg).toContain('fill="#B3261E"')
    const width = Number(svg.match(/width="(\d+)"/)?.[1])
    expect(width).toBeGreaterThan(Number(renderBadge({}).match(/width="(\d+)"/)?.[1]))
  })

  it('never lets anything but its own text in', () => {
    // Its text is fixed words and a date; this only guards the escaping.
    const svg = renderBadge({ recommendation: '<script>' as never })
    expect(svg).not.toContain('<script>')
  })
})

describe('badgeMarkdown', () => {
  it('shows the badge and links it to the result it shows', () => {
    expect(badgeMarkdown('https://s.example', 'https://github.com/acme/skills/tree/main/pdf')).toBe(
      '[![Inskect verdict](https://s.example/badge?target=https%3A%2F%2Fgithub.com%2Facme%2Fskills%2Ftree%2Fmain%2Fpdf)]'
      + '(https://s.example/badge/report?target=https%3A%2F%2Fgithub.com%2Facme%2Fskills%2Ftree%2Fmain%2Fpdf)'
    )
  })
})
