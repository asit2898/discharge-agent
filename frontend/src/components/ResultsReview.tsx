import type { LabResult } from '../types'

// Epic Results Review = a flowsheet: rows are lab components, columns are draw dates
// (oldest → newest, so a trend reads left-to-right), abnormal cells flagged H/L. This is
// the *journey* the discharge snapshot flattens away — the eGFR falling 42 → 24 is what
// makes the home metformin unsafe, visible here in one glance.

const ROW_ORDER = [
  'Creatinine', 'eGFR', 'Urea nitrogen', 'Sodium', 'Potassium',
  'Glucose', 'Hemoglobin A1c', 'Hemoglobin',
]

function rank(name: string): number {
  const i = ROW_ORDER.findIndex((r) => name.toLowerCase().startsWith(r.toLowerCase()))
  return i === -1 ? 99 : i
}

function refText(l: LabResult): string {
  if (l.ref_low != null && l.ref_high != null) return `${l.ref_low}–${l.ref_high}`
  if (l.ref_high != null) return `≤ ${l.ref_high}`
  if (l.ref_low != null) return `≥ ${l.ref_low}`
  return ''
}

function hl(l: LabResult): '' | 'H' | 'L' {
  if (!l.abnormal) return ''
  const v = parseFloat(l.value)
  if (l.ref_high != null && v > l.ref_high) return 'H'
  if (l.ref_low != null && v < l.ref_low) return 'L'
  if (l.interpretation && /high/i.test(l.interpretation)) return 'H'
  if (l.interpretation && /low/i.test(l.interpretation)) return 'L'
  return 'H'
}

const norm = (s: string) => s.replace(/\s+/g, ' ').trim().toLowerCase()

export function ResultsReview({ labs, highlight }: { labs: LabResult[]; highlight?: string }) {
  const needle = highlight ? norm(highlight) : ''
  const dates = Array.from(new Set(labs.map((l) => l.when).filter(Boolean))).sort() as string[]
  const byName = new Map<string, LabResult[]>()
  for (const l of labs) {
    if (!byName.has(l.name)) byName.set(l.name, [])
    byName.get(l.name)!.push(l)
  }
  const rows = Array.from(byName.entries()).sort((a, b) => rank(a[0]) - rank(b[0]))

  return (
    <div className="work">
      <div className="work-head">
        <h2>Results Review</h2>
        <span className="sub">Lab flowsheet · {dates.length} result sets · abnormals flagged</span>
      </div>
      <div className="work-note">
        The <b>journey</b>, not the snapshot: creatinine and eGFR trend across the stay.
        The post-op AKI (eGFR 42 → 24) is exactly what turns the home metformin into a
        contraindication — a snapshot of the final value alone wouldn't tell that story.
      </div>

      {rows.length === 0 ? (
        <div className="center-msg">No resulted labs for this encounter.</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="flowsheet">
            <thead>
              <tr>
                <th className="fs-comp">Component</th>
                <th className="fs-ref">Ref. range</th>
                {dates.map((d) => (
                  <th key={d} className="fs-date">{d.slice(5)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map(([name, series]) => {
                const byDate = new Map(series.map((l) => [l.when, l]))
                const unit = series[0].unit
                const hit = needle !== '' && needle.includes(name.toLowerCase())
                return (
                  <tr key={name} className={hit ? 'hit' : ''}>
                    <td className="fs-comp">
                      {name}
                      {unit && <span className="fs-unit"> ({unit})</span>}
                    </td>
                    <td className="fs-ref">{refText(series[0])}</td>
                    {dates.map((d) => {
                      const l = byDate.get(d)
                      if (!l) return <td key={d} className="fs-cell empty">—</td>
                      const flag = hl(l)
                      return (
                        <td key={d} className={`fs-cell ${flag ? 'abn ' + flag : ''}`}>
                          {l.value}
                          {flag && <span className="fs-hl">{flag}</span>}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
