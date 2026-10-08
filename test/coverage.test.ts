import { describe, expect, it } from 'vitest'
import type { LedgerException, ScanReport } from '../shared/types/scan'
import { gapLocationLabel, inspectionGaps, reasonLabel } from '../shared/utils/coverage'

const MISSING = 'A local path-like reference does not match any bundled artifact, such as a file the skill writes at runtime.'

function exception(reason_code: string, path: string | null, start_line: number | null = null, message = ''): LedgerException {
  return { outcome: 'partial', phase: 'static', reason_code, message, path, start_line, end_line: start_line, fatal: false }
}

function report(completeness: Partial<NonNullable<ScanReport['analysis_completeness']>> | undefined): ScanReport {
  return {
    skill: { name: 'pdf', source: '', scanned_at: '' },
    risk_assessment: { score: 15, severity: 'LOW', recommendation: 'CAUTION', max_issue_severity: 'MEDIUM' },
    issues: [],
    suppressed_count: 0,
    execution_successful: true,
    analysis_completeness: completeness && {
      status: 'partial',
      is_complete: false,
      execution_successful: true,
      total_components: 12,
      fully_inspected_files: 11,
      partially_inspected_files: 1,
      entirely_uninspected_files: 0,
      ...completeness
    }
  }
}

describe('inspectionGaps', () => {
  // As skillspector 2.12.0 reports the anthropics/skills pdf skill.
  const pdf = report({
    ledger_exceptions: [
      exception('reference_missing', 'SKILL.md', 19, MISSING),
      exception('reference_missing', 'SKILL.md', 37, MISSING),
      exception('reference_missing', 'SKILL.md', 37, MISSING),
      exception('static_parse_limit', 'reference.md', null, 'A security-relevant expression exceeded a bounded static parser\'s span limit.')
    ]
  })

  it('groups gaps by reason, real ones before minor ones', () => {
    const gaps = inspectionGaps(pdf)!
    expect(gaps.groups.map(g => [g.reason, g.minor, g.locations.length])).toEqual([
      ['static_parse_limit', false, 1],
      ['reference_missing', true, 2]
    ])
    expect(gaps.significant).toBe(true)
    expect(gaps).toMatchObject({ totalFiles: 12, fullyInspected: 11, partiallyInspected: 1, uninspected: 0 })
  })

  it('keeps skillspector\'s explanation of each reason', () => {
    expect(inspectionGaps(pdf)!.groups[1]!.message).toBe(MISSING)
  })

  it('counts only missing references as minor', () => {
    const gaps = inspectionGaps(report({ partially_inspected_files: 0, ledger_exceptions: [exception('reference_missing', 'SKILL.md', 3)] }))!
    expect(gaps.significant).toBe(false)
  })

  it('counts files nothing inspected as significant', () => {
    expect(inspectionGaps(report({ entirely_uninspected_files: 2, ledger_exceptions: [] }))!.significant).toBe(true)
  })

  it('is null for a complete scan, and for reports from before skillspector recorded it', () => {
    expect(inspectionGaps(report({ partially_inspected_files: 0, ledger_exceptions: [] }))).toBeNull()
    expect(inspectionGaps(report(undefined))).toBeNull()
  })
})

describe('reasonLabel', () => {
  it('names known reasons and spells out the rest', () => {
    expect(reasonLabel('runtime_limit')).toBe('Ran out of time')
    expect(reasonLabel('manifest_parse_error')).toBe('Manifest parse error')
  })
})

describe('gapLocationLabel', () => {
  it('shows the file and line when known', () => {
    expect(gapLocationLabel({ path: 'SKILL.md', line: 19 })).toBe('SKILL.md:19')
    expect(gapLocationLabel({ path: 'reference.md', line: null })).toBe('reference.md')
    expect(gapLocationLabel({ path: null, line: null })).toBe('the skill')
  })
})
