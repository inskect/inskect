import type { ScanReport } from '../types/scan'

// Gaps that rarely matter: a path the skill mentions but doesn't ship, most often a file it writes
// while it runs. skillspector doesn't count them against installing either.
const MINOR_REASONS = new Set(['reference_missing'])

// Short names for the reasons skillspector reports most; others fall back to their code.
const REASON_LABELS: Record<string, string> = {
  reference_missing: 'Referenced files not in the skill',
  reference_unresolved: 'References that couldn\'t be resolved',
  static_parse_limit: 'Too long to parse',
  runtime_limit: 'Ran out of time',
  runtime_seconds_limit: 'Ran out of time',
  size_limit: 'File too large',
  total_bytes_limit: 'Skill too large',
  input_bytes_limit: 'Skill too large',
  artifact_count_limit: 'Too many files',
  traversal_depth_limit: 'Folders nested too deep',
  archive_depth_limit: 'Archives nested too deep',
  archive_member_limit: 'Too many files in an archive',
  archive_size_limit: 'Archive too large',
  read_error: 'Couldn\'t be read',
  syntax_error: 'Couldn\'t be parsed',
  analyzer_load_error: 'An analyzer couldn\'t start',
  analyzer_runtime_error: 'An analyzer failed',
  llm_batch_failed: 'AI review failed',
  transitive_child_scan_failed: 'A referenced target couldn\'t be scanned'
}

export interface GapLocation {
  path: string | null
  line: number | null
}

export interface GapGroup {
  reason: string
  label: string
  // skillspector's own explanation of the reason.
  message: string
  minor: boolean
  locations: GapLocation[]
}

export interface InspectionGaps {
  totalFiles: number
  fullyInspected: number
  partiallyInspected: number
  uninspected: number
  // Most significant first: real gaps, then minor ones; within each, the most locations first.
  groups: GapGroup[]
  // Whether anything beyond minor gaps is missing.
  significant: boolean
}

export function reasonLabel(reason: string): string {
  if (REASON_LABELS[reason]) return REASON_LABELS[reason]
  const words = reason.replace(/_/g, ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/** What a scan couldn't fully inspect, grouped by reason; null when it inspected everything. */
export function inspectionGaps(report: ScanReport): InspectionGaps | null {
  const completeness = report.analysis_completeness
  if (!completeness) return null
  const groups = new Map<string, GapGroup>()
  for (const exception of completeness.ledger_exceptions ?? []) {
    const reason = exception.reason_code || 'unknown'
    let group = groups.get(reason)
    if (!group) {
      group = { reason, label: reasonLabel(reason), message: exception.message ?? '', minor: MINOR_REASONS.has(reason), locations: [] }
      groups.set(reason, group)
    }
    const location = { path: exception.path ?? null, line: exception.start_line ?? null }
    // skillspector records one exception per occurrence; the same line can repeat.
    if (!group.locations.some(l => l.path === location.path && l.line === location.line)) group.locations.push(location)
  }
  const partiallyInspected = completeness.partially_inspected_files ?? 0
  const uninspected = completeness.entirely_uninspected_files ?? 0
  if (!groups.size && !partiallyInspected && !uninspected) return null
  const sorted = [...groups.values()].sort((a, b) => Number(a.minor) - Number(b.minor) || b.locations.length - a.locations.length)
  return {
    totalFiles: completeness.total_components ?? 0,
    fullyInspected: completeness.fully_inspected_files ?? 0,
    partiallyInspected,
    uninspected,
    groups: sorted,
    significant: uninspected > 0 || sorted.some(group => !group.minor)
  }
}

/** "README.md:12", "README.md", or "the skill" for gaps with no file. */
export function gapLocationLabel(location: GapLocation): string {
  if (!location.path) return 'the skill'
  return location.line ? `${location.path}:${location.line}` : location.path
}
