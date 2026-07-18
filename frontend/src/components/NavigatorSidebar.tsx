// Epic-style Discharge Navigator: the ordered activity list a clinician walks through
// at discharge. Medication Reconciliation is the step our copilot plugs into.

export interface NavStep {
  key: string
  label: string
  state: 'done' | 'current' | 'todo'
  badge?: number
}

export const DISCHARGE_STEPS: NavStep[] = [
  { key: 'readiness', label: 'Discharge Readiness', state: 'done' },
  { key: 'problems', label: 'Problem List Review', state: 'done' },
  { key: 'medrec', label: 'Medication Reconciliation', state: 'current' },
  { key: 'orders', label: 'Discharge Orders', state: 'todo' },
  { key: 'avs', label: 'Patient Instructions (AVS)', state: 'todo' },
  { key: 'followup', label: 'Follow-up & Referrals', state: 'todo' },
  { key: 'education', label: 'Patient Education', state: 'todo' },
]

export function NavigatorSidebar({
  active,
  medrecBadge,
  onSelect,
}: {
  active: string
  medrecBadge: number
  onSelect: (key: string) => void
}) {
  return (
    <nav className="nav">
      <div className="nav-head">
        <span className="nav-title">Discharge</span>
        <span className="nav-sub">Navigator</span>
      </div>
      {DISCHARGE_STEPS.map((s, i) => {
        const badge = s.key === 'medrec' ? medrecBadge : undefined
        return (
          <button
            key={s.key}
            className={`nav-step ${s.state} ${active === s.key ? 'active' : ''}`}
            onClick={() => onSelect(s.key)}
          >
            <span className="dot">{s.state === 'done' ? '✓' : i + 1}</span>
            <span className="nav-label">{s.label}</span>
            {badge ? <span className="badge">{badge}</span> : null}
          </button>
        )
      })}
    </nav>
  )
}
