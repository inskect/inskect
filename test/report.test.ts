import { describe, expect, it } from 'vitest'
import type { Finding, ScanReport } from '../shared/types/scan'
import { aiReviewCallSummary, aiReviewModels, findingKey, formatBytes, formatTokenUsage, formatTokens, findingLocation, findingTitle, formatDuration, groupCompletedStages, reportLabel, scanDurationSeconds } from '../shared/utils/report'

function finding(overrides: Partial<Finding> = {}): Finding {
  return {
    id: 'E1',
    finding_id: 'finding-1',
    category: 'Data Exfiltration',
    pattern: 'External Transmission',
    severity: 'MEDIUM',
    confidence: 0.5,
    location: { file: 'SKILL.md', start_line: 64, end_line: null },
    finding: 'https://api.github.com/',
    explanation: 'Data is being sent to an external URL.',
    remediation: null,
    code_snippet: null,
    intent: null,
    tags: [],
    ...overrides
  }
}

describe('groupCompletedStages', () => {
  it('counts completed steps per analyzer family, in scan order', () => {
    const lines = [
      'Starting the inspection of https://github.com/acme/skill',
      'resolve_input completed',
      'static_patterns_ssrf completed',
      'WARNING something odd',
      'static_patterns_anti_refusal completed',
      'mcp_rug_pull completed',
      'static_yara completed',
      'report completed'
    ]
    expect(groupCompletedStages(lines)).toEqual([
      { label: 'Fetch & prepare', completed: 1 },
      { label: 'Static patterns', completed: 2 },
      { label: 'YARA signatures', completed: 1 },
      { label: 'MCP tool checks', completed: 1 },
      { label: 'Integrity & scoring', completed: 1 }
    ])
  })

  it('returns nothing before any step completes', () => {
    expect(groupCompletedStages(['Starting the inspection of x'])).toEqual([])
  })
})

describe('findingTitle', () => {
  it('prefers the rule name over the matched text', () => {
    expect(findingTitle(finding())).toBe('External Transmission')
  })

  it('falls back to the category, then the explanation', () => {
    expect(findingTitle(finding({ pattern: null }))).toBe('Data Exfiltration')
    expect(findingTitle(finding({ pattern: null, category: null }))).toBe('Data is being sent to an external URL.')
  })
})

describe('findingKey', () => {
  it('tells apart occurrences that share a finding_id', () => {
    const a = finding()
    const b = finding({ location: { file: 'SKILL.md', start_line: 253, end_line: null } })
    expect(findingKey(a)).not.toBe(findingKey(b))
  })
})

describe('findingLocation', () => {
  it('shows a line range only when it spans several lines', () => {
    expect(findingLocation(finding())).toBe('SKILL.md:64')
    expect(findingLocation(finding({ location: { file: 'a.py', start_line: 3, end_line: 7 } }))).toBe('a.py:3–7')
    expect(findingLocation(finding({ location: { file: 'a.py', start_line: 0, end_line: null } }))).toBe('a.py')
  })
})

describe('scan duration', () => {
  it('is null while the scan runs, then rounded seconds', () => {
    expect(scanDurationSeconds({ created_at: 100, finished_at: null })).toBeNull()
    expect(scanDurationSeconds({ created_at: 100, finished_at: 114.6 })).toBe(15)
  })

  it('formats seconds and minutes', () => {
    expect(formatDuration(14)).toBe('14 s')
    expect(formatDuration(120)).toBe('2 min')
    expect(formatDuration(75)).toBe('1 min 15 s')
  })
})

function report(metadata: ScanReport['metadata']): ScanReport {
  return {
    skill: { name: 'pdf', source: 'https://github.com/acme/skill', scanned_at: '' },
    risk_assessment: { score: 8, severity: 'LOW', recommendation: 'CAUTION', max_issue_severity: 'MEDIUM' },
    issues: [],
    suppressed_count: 0,
    execution_successful: true,
    metadata
  }
}

describe('aiReviewModels', () => {
  it('lists each model the analyzers used once', () => {
    const analyzers = [
      { analyzer_id: 'semantic_developer_intent', model: 'claude-opus-4-6' },
      { analyzer_id: 'semantic_quality_policy', model: 'claude-opus-4-6' },
      { analyzer_id: 'meta_analyzer', model: 'claude-sonnet-4-6' }
    ]
    const metadata = { llm_requested: true, llm_available: true, meta_analysis_applied: true, llm_provenance: { provider: { configured_adapter: 'anthropic' }, analyzers } }
    expect(aiReviewModels(report(metadata))).toEqual(['claude-opus-4-6', 'claude-sonnet-4-6'])
  })

  it('is empty for reports without provenance', () => {
    expect(aiReviewModels(report(undefined))).toEqual([])
  })
})

describe('aiReviewCallSummary', () => {
  it('counts the calls that succeeded', () => {
    const metadata = { llm_requested: true, llm_available: false, meta_analysis_applied: false, llm_calls_attempted: 5, llm_calls_succeeded: 0 }
    expect(aiReviewCallSummary(report(metadata))).toBe('0 of 5 AI calls succeeded')
  })

  it('is null when skillspector made no call', () => {
    expect(aiReviewCallSummary(report({ llm_requested: true, llm_available: false, meta_analysis_applied: false }))).toBeNull()
  })
})

describe('formatTokens', () => {
  it('shortens large counts to three significant digits', () => {
    expect([950, 1000, 48_210, 125_000, 1_250_000].map(formatTokens)).toEqual(['950', '1k', '48.2k', '125k', '1.25M'])
  })
})

describe('formatTokenUsage', () => {
  it('lists input with its cached part, then output', () => {
    expect(formatTokenUsage({ input: 48_210, output: 3_400, cached: 12_100 })).toBe('48.2k input (12.1k cached) · 3.4k output')
  })

  it('leaves out counters the provider didn\'t report', () => {
    expect(formatTokenUsage({ input: 500, output: null, cached: null })).toBe('500 input')
  })
})

describe('formatBytes', () => {
  it('uses the largest unit under 1024', () => {
    expect([950, 1467, 48_200, 3_500_000].map(formatBytes)).toEqual(['950 B', '1.4 KB', '47.1 KB', '3.3 MB'])
  })
})

describe('reportLabel', () => {
  it('pads a report number to four digits, and grows past them', () => {
    expect(reportLabel(1)).toBe('INS-0001')
    expect(reportLabel(412)).toBe('INS-0412')
    expect(reportLabel(12345)).toBe('INS-12345')
  })

  it('has no label without a number', () => {
    expect(reportLabel(null)).toBeNull()
    expect(reportLabel(undefined)).toBeNull()
  })
})
