import { useEffect, useRef } from 'react'
import type { Med } from '../types'
import { sigOf } from '../recon'
import { Icon, type IconName } from './icons'

const norm = (s: string) => s.replace(/\s+/g, ' ').trim().toLowerCase()
const orderHit = (name: string, needle: string) => {
  if (!needle) return false
  const a = norm(name)
  const b = norm(needle)
  return a.includes(b) || b.includes(a)
}

// Epic Orders activity = the active order profile, grouped by where the order originated
// (home/PTA, inpatient, discharge). Read-only here — the *editable* reconciliation lives in
// the Discharge → Med Rec activity. This view is just the chart context the copilot reasons
// over, rendered straight from the same Med records.

const SECTIONS: { key: Med['source']; title: string; icon: IconName }[] = [
  { key: 'home', title: 'Prior to Admission (Home)', icon: 'home' },
  { key: 'inpatient', title: 'Inpatient Orders', icon: 'bed' },
  { key: 'discharge', title: 'Discharge Orders', icon: 'note' },
]

function OrderTable({ meds, highlight = '' }: { meds: Med[]; highlight?: string }) {
  return (
    <table className="orders">
      <thead>
        <tr>
          <th className="ord-name">Medication</th>
          <th className="ord-sig">Sig</th>
          <th className="ord-status">Status</th>
          <th className="ord-by">Ordered by</th>
          <th className="ord-date">Authored</th>
        </tr>
      </thead>
      <tbody>
        {meds.map((m) => (
          <tr key={m.id} className={orderHit(m.name, highlight) ? 'hit' : ''}>
            <td className="ord-name">
              <span className="ord-ic">
                <Icon name="pill" size={13} />
              </span>
              {m.name}
            </td>
            <td className="ord-sig">{sigOf(m)}</td>
            <td className="ord-status">
              <span className={`ord-badge ${(m.status ?? '').toLowerCase()}`}>
                {m.status ?? '—'}
              </span>
            </td>
            <td className="ord-by">{m.prescriber?.name ?? '—'}</td>
            <td className="ord-date">{m.authored_on ? m.authored_on.slice(0, 10) : '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function OrdersView({
  meds,
  title = 'Orders',
  subtitle,
  note,
  sources,
  highlight,
}: {
  meds: Med[]
  title?: string
  subtitle?: string
  note?: string
  sources?: Med['source'][]
  highlight?: string
}) {
  const sections = SECTIONS.filter((s) => !sources || sources.includes(s.key))
  const shown = sections
    .map((s) => ({ ...s, rows: meds.filter((m) => m.source === s.key) }))
    .filter((s) => s.rows.length > 0)
  const total = shown.reduce((n, s) => n + s.rows.length, 0)

  // scroll the highlighted order into view when the target changes
  const rootRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (highlight) rootRef.current?.querySelector('tr.hit')?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [highlight])

  return (
    <div className="work" ref={rootRef}>
      <div className="work-head">
        <h2>{title}</h2>
        <span className="sub">{subtitle ?? `${total} active orders`}</span>
      </div>
      {note && <div className="work-note">{note}</div>}

      {shown.length === 0 ? (
        <div className="center-msg">No orders on file for this encounter.</div>
      ) : (
        shown.map((s) => (
          <div key={s.key} className="ord-section">
            <h3 className="ord-section-head">
              <span className="ord-section-ic">
                <Icon name={s.icon} size={14} />
              </span>
              {s.title}
              <span className="ord-section-count">{s.rows.length}</span>
            </h3>
            <OrderTable meds={s.rows} highlight={highlight} />
          </div>
        ))
      )}
    </div>
  )
}
