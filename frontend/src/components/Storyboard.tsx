import type { EncounterSummary, PatientHeader } from '../types'

// Epic Hyperdrive "Storyboard": the persistent vertical patient rail pinned to the
// far-left of the chart. Replaces the legacy horizontal banner. Each block reads like
// a Storyboard section — a small icon, a label, and a bold value — so the demo sits on
// top of something a clinician recognizes instantly as Epic.

function initials(name: string): string {
  const parts = name.trim().split(/\s+/)
  return ((parts[0]?.[0] ?? '') + (parts[parts.length - 1]?.[0] ?? '')).toUpperCase()
}

function Section({
  icon,
  label,
  children,
  tone,
}: {
  icon: string
  label: string
  children: React.ReactNode
  tone?: 'alert'
}) {
  return (
    <button className={`sb-section ${tone ?? ''}`} type="button">
      <span className="sb-ic">{icon}</span>
      <span className="sb-sec-body">
        <span className="sb-sec-label">{label}</span>
        <span className="sb-sec-value">{children}</span>
      </span>
    </button>
  )
}

export function Storyboard({
  header,
  current,
}: {
  header: PatientHeader
  current: EncounterSummary | null
}) {
  const sex = header.gender ? header.gender[0].toUpperCase() : '?'
  const hasAllergy = header.allergies.length > 0

  return (
    <aside className="storyboard">
      <div className="sb-status">{current?.visit_type ?? 'Inpatient'}</div>

      <div className="sb-identity">
        <div className="sb-avatar">{initials(header.name)}</div>
        <div className="sb-name">{header.name}</div>
        <div className="sb-demo">
          {header.age != null ? `${header.age} y.o.` : '—'} · {sex}
        </div>
        <div className="sb-ids">
          <span>MRN {header.mrn.replace(/^MRN\s*/i, '')}</span>
          {header.dob && <span>DOB {header.dob}</span>}
        </div>
      </div>

      <div className="sb-sections">
        <Section icon={hasAllergy ? '⚠' : '✓'} label="Allergies" tone={hasAllergy ? 'alert' : undefined}>
          {hasAllergy ? header.allergies.join(', ') : 'Not on File'}
        </Section>

        <Section icon="🛏" label="Location">
          {header.location ?? '—'}
        </Section>

        <Section icon="✚" label="Code Status">
          {header.code_status}
        </Section>

        {header.attending && (
          <Section icon="👤" label="Attending">
            {header.attending}
          </Section>
        )}

        <Section icon="🗓" label="Encounter">
          {current?.visit_title ?? 'Inpatient discharge'}
          {current?.date ? ` · ${current.date.slice(0, 10)}` : ''}
        </Section>

        <Section icon="🩺" label="Care Team">
          Ortho · Cardiology · ID · Hospitalist
        </Section>
      </div>
    </aside>
  )
}
