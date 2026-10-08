import type { Recommendation } from '../types/scan'

// A target's status badge (server/routes/badge.get.ts): the verdict of the latest inspection its
// owner put on it, drawn as Inskect's inspection tag: square, monospace, an ink label and the
// verdict in its stamp colour.

export interface BadgeData {
  recommendation: Recommendation | null
  risk_score: number | null
  scanned_at: number | null
  share_token: string | null
}

const BADGE_LABEL = 'inskect'

const VERDICTS: Record<Recommendation, { text: string, color: string }> = {
  SAFE: { text: 'passed', color: '#1E7A3C' },
  CAUTION: { text: 'review first', color: '#A35200' },
  DO_NOT_INSTALL: { text: 'rejected', color: '#B3261E' }
}
const UNKNOWN = { text: 'not inspected', color: '#5A5F6B' }
const INK = '#14171F'

// A monospace font at 11px: every character is as wide as the next.
const CHAR_WIDTH = 6.7

function textWidth(text: string): number {
  return Math.ceil([...text].length * CHAR_WIDTH)
}

function escapeXml(text: string): string {
  return text.replace(/[<>&"']/g, char => `&#${char.charCodeAt(0)};`)
}

/** What the badge says: the verdict and the scan's date, or "unknown" without a scan on it. */
export function badgeMessage(data: Partial<BadgeData>): { text: string, color: string } {
  const verdict = data.recommendation ? VERDICTS[data.recommendation] : undefined
  if (!verdict) return UNKNOWN
  const date = data.scanned_at ? ` · ${new Date(data.scanned_at * 1000).toISOString().slice(0, 10)}` : ''
  return { text: `${verdict.text}${date}`, color: verdict.color }
}

export function renderBadge(data: Partial<BadgeData>): string {
  const message = badgeMessage(data)
  const labelWidth = textWidth(BADGE_LABEL) + 14
  const messageWidth = textWidth(message.text) + 14
  const width = labelWidth + messageWidth
  const title = escapeXml(`${BADGE_LABEL}: ${message.text}`)
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="20" role="img" aria-label="${title}">`
    + `<title>${title}</title>`
    + `<rect x=".5" y=".5" width="${width - 1}" height="19" fill="#fff" stroke="${INK}"/>`
    + `<rect width="${labelWidth}" height="20" fill="${INK}"/>`
    + '<g text-anchor="middle" font-family="DejaVu Sans Mono,Menlo,Consolas,monospace" font-size="11">'
    + `<text x="${labelWidth / 2}" y="14" fill="#fff">${escapeXml(BADGE_LABEL)}</text>`
    + `<text x="${labelWidth + messageWidth / 2}" y="14" fill="${message.color}">${escapeXml(message.text)}</text>`
    + '</g></svg>'
}

/** The Markdown a README shows the badge with, linking to the result it shows. */
export function badgeMarkdown(origin: string, target: string): string {
  const query = `target=${encodeURIComponent(target)}`
  return `[![Inskect verdict](${origin}/badge?${query})](${origin}/badge/report?${query})`
}
