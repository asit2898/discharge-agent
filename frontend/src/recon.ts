import type { Flag, Med, ReviewStatus, Severity } from './types'

// Associate a flag with the med it concerns. Two passes so an exact resource_id match
// always wins over a looser name prefix (e.g. amlodipine 2.5 vs amlodipine 5) — otherwise
// a flag whose med_name prefixes multiple rows would mislabel the wrong one.
export function flagForMed(med: Med, flags: Flag[]): Flag | undefined {
  const byId = flags.find((f) => f.chart_evidence?.resource_id === med.id)
  if (byId) return byId
  // don't let a name-prefix flag claim a row that another flag owns by resource_id
  const claimed = new Set(
    flags.map((f) => f.chart_evidence?.resource_id).filter((x): x is string => !!x),
  )
  if (claimed.has(med.id)) return undefined
  return flags.find(
    (f) => f.med_name && med.name.toLowerCase().startsWith(f.med_name.toLowerCase()),
  )
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

// The copilot's proposed discharge disposition for a flag, derived from its own
// recommendation text so the marker is grounded in the auditable reason (not a guess).
export type Disp = 'continue' | 'modify' | 'discontinue'

const DISC = /\b(stop|discontinue|hold|do not|don't|dont|avoid|remove|de-?prescribe|not give|not start)\b/
const MOD = /\b(reduce|adjust|dose|space|switch|consolidate|modif|change|end date|stop date|verify|evaluate|reassess|reconcile|confirm|watch|renally)\b/
const CONT = /\b(continue|resume|keep|add|restart|start|order|give)\b/

export function proposedDisp(flag: Flag): Disp {
  // The recommendation's leading directive is the primary signal (so the shown reason and
  // the color agree); only fall back to the suggested_fix text if it's ambiguous.
  const rec = (flag.recommended_resolution ?? '').toLowerCase()
  const fix = (flag.suggested_fix ?? '').toLowerCase()
  if (DISC.test(rec)) return 'discontinue'
  if (MOD.test(rec)) return 'modify'
  if (CONT.test(rec)) return 'continue'
  if (DISC.test(fix)) return 'discontinue'
  if (MOD.test(fix)) return 'modify'
  if (CONT.test(fix)) return 'continue'
  return 'modify'
}

export const DISP_LABEL: Record<Disp, string> = {
  continue: 'Continue',
  modify: 'Modify',
  discontinue: "Don't Continue",
}

export function truncate(s: string | null, n = 120): string {
  if (!s) return ''
  return s.length > n ? s.slice(0, n - 1).trimEnd() + '…' : s
}

export const STATUS_VERB: Record<ReviewStatus, string> = {
  pending: 'Pending',
  accepted: 'Accepted',
  edited: 'Edited',
  rejected: 'Dismissed',
}
