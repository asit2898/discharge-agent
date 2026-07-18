import type { EncounterSummary, PatientHeader } from '../types'
import { Icon, type IconName } from './icons'

// Epic Hyperspace/Hyperdrive "Storyboard": the persistent left patient rail. Rebuilt to
// Epic's real density from a live reference — Last-First name, compact "label: value"
// rows, small-caps section headers, red-accented alerts (isolation/allergies/precautions),
// New Results dot-counts, Active Meds, and a Chart Search box.

function lastFirst(name: string): string {
  const parts = name.trim().split(/\s+/)
  if (parts.length < 2) return name
  const last = parts.pop() as string
  return `${last}, ${parts.join(' ')}`
}

function Row({
  icon,
  k,
  children,
  alert,
}: {
  icon?: IconName
  k: string
  children: React.ReactNode
  alert?: boolean
}) {
  return (
    <div className={`sb-row ${alert ? 'alert' : ''}`}>
      {icon ? (
        <span className="sb-row-ic">
          <Icon name={icon} size={12} />
        </span>
      ) : (
        <span className="sb-row-ic" />
      )}
      <span className="sb-k">{k}:</span> <span className="sb-v">{children}</span>
    </div>
  )
}

function Head({ children, alert }: { children: React.ReactNode; alert?: boolean }) {
  return <div className={`sb-hd ${alert ? 'alert' : ''}`}>{children}</div>
}

export function Storyboard({
  header,
  current,
}: {
  header: PatientHeader
  current: EncounterSummary | null
}) {
  const sex = header.gender ? header.gender[0].toUpperCase() + header.gender.slice(1) : '—'
  const hasAllergy = header.allergies.length > 0
  const bed = header.location ?? '—'
  const admitDate = current?.date ? current.date.slice(0, 10) : '2026-07-13'

  return (
    <aside className="storyboard">
      <div className="sb-identity">
        <div className="sb-avatar" aria-hidden="true">
          <svg viewBox="0 0 48 48" width="48" height="48">
            <circle cx="24" cy="18" r="9" fill="#9fb0c0" />
            <path d="M8 44c0-9 7.2-15 16-15s16 6 16 15z" fill="#9fb0c0" />
          </svg>
        </div>
        <div className="sb-name">{lastFirst(header.name)}</div>
        <div className="sb-demo">
          {sex}, {header.age != null ? `${header.age} y.o.` : '—'}
          {header.dob ? `, ${header.dob}` : ''}
        </div>
        <div className="sb-mrn">MRN: {header.mrn.replace(/^MRN\s*/i, '')}</div>
      </div>

      <label className="sb-search">
        <Icon name="search" size={12} />
        <input placeholder="Search chart…" readOnly />
      </label>

      <div className="sb-sections">
        <Row icon="globe" k="Language">
          English
        </Row>
        <Row icon="bed" k="Bed">
          {bed}
        </Row>
        <Row icon="code" k="Code">
          {header.code_status}
        </Row>
        <Row icon="user" k="Isolation">
          Standard
        </Row>
        <Row icon="allergy" k="Allergies" alert={hasAllergy}>
          {hasAllergy ? header.allergies.join(', ') : 'No Known Allergies'}
        </Row>

        <Head>Admission</Head>
        <Row k="Admitted">
          {admitDate} <span className="sb-muted">(Day 5)</span>
        </Row>
        <Row k="Exp. Discharge">
          <span className="sb-link">Today</span>
        </Row>
        {header.attending && <Row k="Attending">{header.attending}</Row>}
        <Row k="Care Team">Ortho · Cardiology · ID</Row>

        <Head>Principal Problem</Head>
        <div className="sb-free">Intertrochanteric fracture of right femur</div>

        <Head>New Results</Head>
        <div className="sb-dots">
          <span className="dot lab">Lab 12</span>
          <span className="dot micro">Micro 2</span>
          <span className="dot img">Imaging 1</span>
        </div>

        <Head>Active Meds ({current?.med_count ?? 12})</Head>
        <div className="sb-free">Scheduled 7 · PRN 5</div>

        <Row k="PCP">Dr. Lin</Row>
        <Row k="Dosing Wt">68 kg</Row>

        <Head alert>Precautions</Head>
        <div className="sb-free alert">Fall Risk · Anticoagulation</div>
      </div>
    </aside>
  )
}
