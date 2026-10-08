import type { Recommendation } from '~~/shared/types/scan'

// What an inspection report's stamp says (VerdictStamp).
export const RECOMMENDATION_LABEL: Record<Recommendation, string> = {
  SAFE: 'Passed',
  CAUTION: 'Review first',
  DO_NOT_INSTALL: 'Rejected'
}

// For tight spots: tables and the recent-inspections list.
export const RECOMMENDATION_SHORT_LABEL: Record<Recommendation, string> = RECOMMENDATION_LABEL

// What each verdict means, for whoever reads a stamp for the first time.
export const RECOMMENDATION_MEANING: Record<Recommendation, string> = {
  SAFE: 'Nothing the checks know of was found: safe to install, once you’ve read the findings.',
  CAUTION: 'Read the findings before you install it.',
  DO_NOT_INSTALL: 'Don’t install it.'
}

// Written out in full so Tailwind can see every class.
export const RECOMMENDATION_CLASSES: Record<Recommendation, { dot: string, ink: string, chip: string, panel: string, rule: string }> = {
  SAFE: {
    dot: 'bg-safe',
    ink: 'text-safe-ink',
    chip: 'bg-safe-tint text-safe-ink ring-1 ring-safe-line',
    panel: 'bg-safe-tint border-safe-line',
    rule: 'border-safe-line'
  },
  CAUTION: {
    dot: 'bg-medium',
    ink: 'text-medium-ink',
    chip: 'bg-medium-tint text-medium-ink ring-1 ring-medium-line',
    panel: 'bg-medium-tint border-medium-line',
    rule: 'border-medium-line'
  },
  DO_NOT_INSTALL: {
    dot: 'bg-critical',
    ink: 'text-critical-ink',
    chip: 'bg-critical-tint text-critical-ink ring-1 ring-critical-line',
    panel: 'bg-critical-tint border-critical-line',
    rule: 'border-critical-line'
  }
}
