// Names from a scanned skill (its name, file paths, the target) can be made to read as something
// else: an invisible character, a right-to-left override, or a letter from another alphabet that
// looks the same (a Cyrillic а in "reаd_data"). These find them, for the UI to show them
// (app/components/UntrustedText.vue). skillspector flags them in a skill's content; this is for the
// names around it.

export type SuspiciousKind = 'bidi' | 'invisible' | 'mixed-script'

export interface TextPart {
  text: string
  // Set on a character to show for what it is.
  kind?: SuspiciousKind
  codePoint?: string
}

// Characters that reorder the text around them: embeddings, overrides, isolates, marks.
const BIDI = /^[\u061C\u200E\u200F\u202A-\u202E\u2066-\u2069]$/u
// Characters that show as nothing, or join or vary their neighbours unseen.
// eslint-disable-next-line no-misleading-character-class -- matched one character at a time, variation selectors on their own included
const INVISIBLE = /^[\u00AD\u034F\u115F\u1160\u17B4\u17B5\u180B-\u180F\u200B-\u200D\u2060-\u2064\u3164\uFE00-\uFE0F\uFEFF\uFFA0\u{E0000}-\u{E007F}\u{E0100}-\u{E01EF}]$/u
// Alphabets whose letters pass for each other.
const SCRIPTS = [
  ['Latin', /\p{Script=Latin}/u],
  ['Cyrillic', /\p{Script=Cyrillic}/u],
  ['Greek', /\p{Script=Greek}/u]
] as const

export function codePointOf(char: string): string {
  return `U+${char.codePointAt(0)!.toString(16).toUpperCase().padStart(4, '0')}`
}

function scriptOf(char: string): string | null {
  return SCRIPTS.find(([, pattern]) => pattern.test(char))?.[0] ?? null
}

/**
 * The text in parts, the suspicious characters on their own: bidirectional controls, invisible
 * characters, and in a word mixing alphabets, the letters not from its main one.
 */
export function inspectText(text: string): TextPart[] {
  const parts: TextPart[] = []
  const push = (part: TextPart) => {
    const last = parts.at(-1)
    if (!part.kind && last && !last.kind) last.text += part.text
    else parts.push(part)
  }
  // Words (runs of letters and marks), and what's between them.
  for (const [segment] of text.matchAll(/[\p{L}\p{M}]+|[^\p{L}\p{M}]+/gu)) {
    const chars = [...segment]
    const counts = new Map<string, number>()
    for (const char of chars) {
      const script = scriptOf(char)
      if (script) counts.set(script, (counts.get(script) ?? 0) + 1)
    }
    // The word's main alphabet; with a tie, Latin, which the others imitate.
    const main = counts.size > 1
      ? [...counts.entries()].sort((a, b) => b[1] - a[1] || (a[0] === 'Latin' ? -1 : 1))[0]![0]
      : null
    for (const char of chars) {
      if (BIDI.test(char)) push({ text: char, kind: 'bidi', codePoint: codePointOf(char) })
      else if (INVISIBLE.test(char)) push({ text: char, kind: 'invisible', codePoint: codePointOf(char) })
      else if (main && scriptOf(char) && scriptOf(char) !== main) push({ text: char, kind: 'mixed-script', codePoint: codePointOf(char) })
      else push({ text: char })
    }
  }
  return parts
}

export function isSuspicious(text: string): boolean {
  return inspectText(text).some(part => part.kind)
}

const LABELS: Record<SuspiciousKind, string> = {
  'bidi': 'reorders the text',
  'invisible': 'invisible',
  'mixed-script': 'from another alphabet'
}

/** What a warning says about the text's suspicious characters, e.g. "U+202E (reorders the text)". */
export function suspiciousSummary(text: string): string {
  const flagged = inspectText(text).filter(part => part.kind)
  return [...new Set(flagged.map(part => `${part.codePoint} ${part.text.trim() && part.kind === 'mixed-script' ? `“${part.text}” ` : ''}(${LABELS[part.kind!]})`))].join(', ')
}

/** The text for where markup can't go (a page title): invisible and reordering characters written
 * as their code points, so they read as what they are. */
export function visibleText(text: string): string {
  return inspectText(text).map(part => part.kind && part.kind !== 'mixed-script' ? `⟨${part.codePoint}⟩` : part.text).join('')
}
