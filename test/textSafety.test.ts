import { describe, expect, it } from 'vitest'
import { inspectText, isSuspicious, suspiciousSummary, visibleText } from '../shared/utils/textSafety'

const flagged = (text: string) => inspectText(text).filter(part => part.kind).map(part => [part.kind, part.codePoint])

describe('inspectText', () => {
  it('leaves ordinary names alone, in any one alphabet', () => {
    for (const name of ['read_data', 'skills/pdf-tools', 'https://github.com/acme/skill', 'отчёт', 'Ελληνικά', '日本語のスキル', 'café']) {
      expect(isSuspicious(name)).toBe(false)
    }
    expect(inspectText('read_data')).toEqual([{ text: 'read_data' }])
  })

  it('finds a letter from another alphabet in a word: a Cyrillic \u0430 in “re\u0430d_data”', () => {
    expect(flagged('re\u0430d_data')).toEqual([['mixed-script', 'U+0430']])
    expect(flagged('P\u0430yp\u0430l')).toEqual([['mixed-script', 'U+0430'], ['mixed-script', 'U+0430']])
    // A Latin letter in a mostly Cyrillic word.
    expect(flagged('пaроль')).toEqual([['mixed-script', 'U+0061']])
  })

  it('finds right-to-left overrides and other reordering characters', () => {
    expect(flagged('invoice\u202Efdp.exe')).toEqual([['bidi', 'U+202E']])
    expect(flagged('a\u2066b\u2069')).toEqual([['bidi', 'U+2066'], ['bidi', 'U+2069']])
  })

  it('finds invisible characters', () => {
    expect(flagged('read\u200B_data')).toEqual([['invisible', 'U+200B']])
    expect(flagged('\uFEFFskill')).toEqual([['invisible', 'U+FEFF']])
    expect(flagged('a\u{E0041}b')).toEqual([['invisible', 'U+E0041']])
  })

  it('keeps the rest of the text, in order', () => {
    expect(inspectText('ab\u202Ecd').map(part => part.text).join('')).toBe('ab\u202Ecd')
  })
})

describe('what the UI shows', () => {
  it('says what was found', () => {
    expect(suspiciousSummary('re\u0430d\u202E')).toBe('U+0430 “\u0430” (from another alphabet), U+202E (reorders the text)')
  })

  it('writes invisible and reordering characters as code points where markup can’t go', () => {
    expect(visibleText('invoice\u202Efdp.exe')).toBe('invoice⟨U+202E⟩fdp.exe')
    expect(visibleText('read\u200B_data')).toBe('read⟨U+200B⟩_data')
  })
})
