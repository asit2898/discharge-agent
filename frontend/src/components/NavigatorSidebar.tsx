// Epic-style Discharge Navigator: the ordered activity list a clinician walks through
// at discharge. Medication Reconciliation is the step our copilot plugs into.

export interface NavStep {
  key: string
  label: string
  state: 'done' | 'current' | 'todo'
  group: string
  badge?: number
}

// Grouped under small-caps category headers, matching Epic's Discharge Navigator
// section list (REVIEW / ORDERS / PATIENT).
export const DISCHARGE_STEPS: NavStep[] = [
  { key: 'readiness', label: 'Discharge Readiness', state: 'done', group: 'Review' },
  { key: 'problems', label: 'Problem List Review', state: 'done', group: 'Review' },
  { key: 'medrec', label: 'Med Rec and Orders', state: 'current', group: 'Orders' },
  { key: 'orders', label: 'Discharge Orders', state: 'todo', group: 'Orders' },
  { key: 'rx', label: 'Rx Routing', state: 'todo', group: 'Orders' },
  { key: 'avs', label: 'Patient Instructions (AVS)', state: 'todo', group: 'Patient' },
  { key: 'followup', label: 'Follow-up & Referrals', state: 'todo', group: 'Patient' },
  { key: 'education', label: 'Patient Education', state: 'todo', group: 'Patient' },
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
        const firstOfGroup = DISCHARGE_STEPS.findIndex((x) => x.group === s.group) === i
        return (
          <div key={s.key}>
            {firstOfGroup && <div className="nav-group">{s.group}</div>}
            <button
              className={`nav-step ${s.state} ${active === s.key ? 'active' : ''}`}
              onClick={() => onSelect(s.key)}
            >
              <span className="dot">{s.state === 'done' ? '✓' : ''}</span>
              <span className="nav-label">{s.label}</span>
              {badge ? <span className="badge">{badge}</span> : null}
            </button>
          </div>
        )
      })}
    </nav>
  )
}
