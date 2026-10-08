import type { Severity } from '../../shared/types/scan'

export const SEVERITY_LABEL: Record<Severity, string> = {
  CRITICAL: 'Critical',
  HIGH: 'High',
  MEDIUM: 'Medium',
  LOW: 'Low'
}

export const SEVERITIES: Severity[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']

export const SEVERITY_RANK: Record<Severity, number> = {
  CRITICAL: 0,
  HIGH: 1,
  MEDIUM: 2,
  LOW: 3
}

// Written out in full so Tailwind can see every class.
export const SEVERITY_CLASSES: Record<Severity, { dot: string, stroke: string, ink: string, chip: string }> = {
  CRITICAL: { dot: 'bg-critical', stroke: 'stroke-critical', ink: 'text-critical-ink', chip: 'bg-critical-tint text-critical-ink ring-1 ring-critical-line' },
  HIGH: { dot: 'bg-high', stroke: 'stroke-high', ink: 'text-high-ink', chip: 'bg-high-tint text-high-ink ring-1 ring-high-line' },
  MEDIUM: { dot: 'bg-medium', stroke: 'stroke-medium', ink: 'text-medium-ink', chip: 'bg-medium-tint text-medium-ink ring-1 ring-medium-line' },
  LOW: { dot: 'bg-low', stroke: 'stroke-low', ink: 'text-low-ink', chip: 'bg-low-tint text-low-ink ring-1 ring-low-line' }
}
