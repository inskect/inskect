import type { Finding, ScanReport, ScanStatus } from '../types/scan'

// Families of skillspector graph nodes, in the order a scan roughly runs them. Matched on the
// node name each "<node> completed" log line carries.
const STAGE_GROUPS: { label: string, match: (node: string) => boolean }[] = [
  { label: 'Fetch & prepare', match: node => ['resolve_input', 'build_context', 'structured_skill_roles'].includes(node) },
  { label: 'Static patterns', match: node => node.startsWith('static_patterns_') },
  { label: 'YARA signatures', match: node => node === 'static_yara' },
  { label: 'Behavioral analysis', match: node => node.startsWith('behavioral_') || node === 'bundled_execution_surface' },
  { label: 'MCP tool checks', match: node => node.startsWith('mcp_') },
  { label: 'AI review', match: node => node.startsWith('semantic_') },
  { label: 'Integrity & scoring', match: () => true }
]

export interface StageGroup {
  label: string
  completed: number
}

/** Counts completed graph steps per analyzer family, keeping only families that have started. */
export function groupCompletedStages(lines: string[]): StageGroup[] {
  const counts = new Map<string, number>()
  for (const line of lines) {
    const node = line.match(/^(\S+) completed$/)?.[1]
    if (!node) continue
    const group = STAGE_GROUPS.find(g => g.match(node))!
    counts.set(group.label, (counts.get(group.label) ?? 0) + 1)
  }
  return STAGE_GROUPS
    .filter(group => counts.has(group.label))
    .map(group => ({ label: group.label, completed: counts.get(group.label)! }))
}

/**
 * A finding's headline. skillspector puts the matched text in `finding` and a generic
 * description in `explanation`, so the rule name (`pattern`) or `category` reads best.
 */
export function findingTitle(finding: Finding): string {
  return finding.pattern ?? finding.category ?? finding.explanation ?? 'Finding'
}

/**
 * A stable key per finding. skillspector repeats the same `finding_id` for each occurrence of a
 * rule, so the location tells occurrences apart.
 */
export function findingKey(finding: Finding): string {
  const { file, start_line: line } = finding.location
  return `${finding.finding_id}@${file}:${line}`
}

export function findingLocation(finding: Finding): string {
  const { file, start_line: start, end_line: end } = finding.location
  if (!start) return file
  return end && end !== start ? `${file}:${start}–${end}` : `${file}:${start}`
}

/** Wall-clock seconds the scan took, or null while it's still running. */
export function scanDurationSeconds(status: Pick<ScanStatus, 'created_at' | 'finished_at'>): number | null {
  if (status.finished_at === null) return null
  return Math.max(0, Math.round(status.finished_at - status.created_at))
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds} s`
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return rest ? `${minutes} min ${rest} s` : `${minutes} min`
}

/** 950 → "950", 48_200 → "48.2k", 1_250_000 → "1.25M". */
export function formatTokens(count: number): string {
  if (count < 1000) return String(count)
  if (count < 1_000_000) return `${Number((count / 1000).toPrecision(3))}k`
  return `${Number((count / 1_000_000).toPrecision(3))}M`
}

/** "48.2k input (12.1k cached) · 3.4k output", leaving out counters nobody reported. */
export function formatTokenUsage(tokens: { input: number | null, output: number | null, cached: number | null }): string {
  const parts = []
  if (tokens.input !== null) parts.push(`${formatTokens(tokens.input)} input${tokens.cached ? ` (${formatTokens(tokens.cached)} cached)` : ''}`)
  if (tokens.output !== null) parts.push(`${formatTokens(tokens.output)} output`)
  return parts.join(' · ')
}

/** The models the AI review used, as skillspector recorded them, without repeats. */
export function aiReviewModels(report: ScanReport): string[] {
  const analyzers = report.metadata?.llm_provenance?.analyzers ?? []
  return [...new Set(analyzers.map(analyzer => analyzer.model).filter((model): model is string => !!model))]
}

/** "3 of 5 AI calls succeeded", when skillspector counted them. */
export function aiReviewCallSummary(report: ScanReport): string | null {
  const attempted = report.metadata?.llm_calls_attempted
  if (!attempted) return null
  const succeeded = report.metadata?.llm_calls_succeeded ?? 0
  return `${succeeded} of ${attempted} AI call${attempted === 1 ? '' : 's'} succeeded`
}

/** 950 → "950 B", 48_200 → "47.1 KB", 3_500_000 → "3.3 MB". */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Number((bytes / 1024).toFixed(1))} KB`
  return `${Number((bytes / (1024 * 1024)).toFixed(1))} MB`
}

/** An inspection report's label, from its number among its owner's: INS-0001, INS-0412, INS-12345. */
export function reportLabel(reportNo: number | null | undefined): string | null {
  return reportNo ? `INS-${String(reportNo).padStart(4, '0')}` : null
}
