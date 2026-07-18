import type { Flag, Med, ReviewStatus, Severity } from './types'

// Associate a flag with the med it concerns: prefer a chart_evidence resource_id that
// matches a med id, else fall back to a med_name prefix match.
export function flagForMed(med: Med, flags: Flag[]): Flag | undefined {
  return flags.find((f) => {
    if (f.chart_evidence?.resource_id && f.chart_evidence.resource_id === med.id) return true
    if (f.med_name && med.name.toLowerCase().startsWith(f.med_name.toLowerCase())) return true
    return false
  })
}

export function sigOf(med: Med): string {
  return [med.dose, med.route, med.frequency].filter(Boolean).join(' · ') || '—'
}

export const SEVERITY_LABEL: Record<Severity, string> = {
  high: 'High',
  moderate: 'Moderate',
  low: 'Low',
}

export function prettyType(t: string): string {
  return t.replace(/_/g, ' ')
}

export const STATUS_VERB: Record<ReviewStatus, string> = {
  pending: 'Pending',
  accepted: 'Accepted',
  edited: 'Edited',
  rejected: 'Dismissed',
}
