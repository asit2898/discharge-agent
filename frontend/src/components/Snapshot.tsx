import type { EncounterDetail, LabResult } from '../types'
import { Icon, type IconName } from './icons'

// Epic Snapshot = the single-screen chart summary a clinician opens a patient on:
// demographics + alerts, the active problem list, an order count, and the latest abnormal
// results. Every field here is read straight from the loaded encounter — this is the flat
// "current state" view that the Results Review flowsheet and the reconciliation deliberately
// go *deeper* than (the snapshot shows eGFR 24 now; only the flowsheet shows it fell there).

function Card({
  title,
  icon,
  children,
  alert,
}: {
  title: string
  icon: IconName
  children: React.ReactNode
  alert?: boolean
}) {
  return (
    <section className={`snap-card ${alert ? 'alert' : ''}`}>
      <h3 className="snap-card-head">
        <span className="snap-card-ic">
          <Icon name={icon} size={14} />
        </span>
        {title}
      </h3>
      <div className="snap-card-body">{children}</div>
    </section>
  )
}

// Latest value per abnormal component, newest draw wins.
function latestAbnormals(labs: LabResult[]): LabResult[] {
  const byName = new Map<string, LabResult>()
  for (const l of labs) {
    if (!l.abnormal) continue
    const prev = byName.get(l.name)
    if (!prev || (l.when ?? '') > (prev.when ?? '')) byName.set(l.name, l)
  }
  return Array.from(byName.values())
}

export function Snapshot({ detail }: { detail: EncounterDetail }) {
  const { header, problems, labs, meds, metadata } = detail
  const acute = problems.filter((p) => p.acute)
  const chronic = problems.filter((p) => !p.acute)
  const abnormals = latestAbnormals(labs)
  const teams = Array.isArray(metadata?.teams) ? (metadata.teams as string[]) : []
  const bySource = (s: string) => meds.filter((m) => m.source === s).length

  const demo = [
    header.gender ? header.gender[0].toUpperCase() + header.gender.slice(1) : null,
    header.age != null ? `${header.age} y.o.` : null,
    header.dob,
  ]
    .filter(Boolean)
    .join(', ')

  return (
    <div className="work">
      <div className="work-head">
        <h2>Snapshot</h2>
        <span className="sub">{header.name} · MRN {header.mrn.replace(/^MRN\s*/i, '')}</span>
      </div>

      <div className="snap-grid">
        <Card title="Patient" icon="user">
          <div className="snap-kv"><span>Demographics</span><b>{demo || '—'}</b></div>
          <div className="snap-kv"><span>Location</span><b>{header.location ?? '—'}</b></div>
          <div className="snap-kv"><span>Code status</span><b>{header.code_status}</b></div>
          <div className="snap-kv"><span>Attending</span><b>{header.attending ?? '—'}</b></div>
          {teams.length > 0 && (
            <div className="snap-kv"><span>Care teams</span><b>{teams.join(' · ')}</b></div>
          )}
        </Card>

        <Card title="Allergies" icon="allergy" alert={header.allergies.length > 0}>
          {header.allergies.length > 0 ? (
            <ul className="snap-list">
              {header.allergies.map((a) => (
                <li key={a} className="snap-alert-item">{a}</li>
              ))}
            </ul>
          ) : (
            <div className="snap-muted">No Known Allergies</div>
          )}
        </Card>

        <Card title="Medications" icon="pill">
          <div className="snap-kv"><span>Total on chart</span><b>{meds.length}</b></div>
          <div className="snap-kv"><span>Home (PTA)</span><b>{bySource('home')}</b></div>
          <div className="snap-kv"><span>Inpatient</span><b>{bySource('inpatient')}</b></div>
          <div className="snap-kv"><span>Discharge</span><b>{bySource('discharge')}</b></div>
        </Card>

        <Card title={`Problem List (${problems.length})`} icon="clipboard">
          {acute.length > 0 && (
            <>
              <div className="snap-sub">Active — this admission</div>
              <ul className="snap-list">
                {acute.map((p) => (
                  <li key={p.label}>
                    {p.label}
                    <span className="snap-badge acute">This admission</span>
                  </li>
                ))}
              </ul>
            </>
          )}
          {chronic.length > 0 && (
            <>
              <div className="snap-sub">Chronic / ongoing</div>
              <ul className="snap-list snap-list-muted">
                {chronic.map((p) => (
                  <li key={p.label}>{p.label}</li>
                ))}
              </ul>
            </>
          )}
        </Card>

        <Card title={`Latest Abnormal Results (${abnormals.length})`} icon="flask">
          {abnormals.length === 0 ? (
            <div className="snap-muted">No abnormal results resulted.</div>
          ) : (
            <ul className="snap-list">
              {abnormals.map((l) => (
                <li key={l.name} className="snap-lab">
                  <span className="snap-lab-name">{l.name}</span>
                  <span className="snap-lab-val abn">
                    {l.value}
                    {l.unit ? ` ${l.unit}` : ''}
                  </span>
                  {l.when && <span className="snap-lab-when">{l.when.slice(5)}</span>}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}
