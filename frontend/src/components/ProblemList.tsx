import type { Problem } from '../types'

// Epic Problem List = coded problems with noted date + chronic/acute status. Acute
// (this-admission) problems are what the discharge orders are reconciled against;
// chronic problems are the patient's standing context.

const words = (s: string) =>
  s.toLowerCase().replace(/[()]/g, ' ').split(/\s+/).filter((w) => w.length > 2)

export function ProblemList({
  problems,
  highlight,
}: {
  problems: Problem[]
  highlight?: string
}) {
  const acute = problems.filter((p) => p.acute)
  const chronic = problems.filter((p) => !p.acute)
  // Token-overlap match — robust to word-order differences between the FHIR display
  // ("Diabetes mellitus type 2") and the problem-list label ("Type 2 diabetes mellitus").
  const needleWords = new Set(highlight ? words(highlight) : [])
  const isHit = (label: string) => {
    if (needleWords.size === 0) return false
    const lw = words(label)
    if (lw.length === 0) return false
    const overlap = lw.filter((w) => needleWords.has(w)).length
    return overlap / lw.length >= 0.6
  }

  const Table = ({ rows }: { rows: Problem[] }) => (
    <table className="problems">
      <thead>
        <tr>
          <th>Problem</th>
          <th className="pl-code">Code</th>
          <th className="pl-date">Noted</th>
          <th className="pl-tag">Status</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((p) => (
          <tr key={p.label} className={`${p.acute ? 'acute' : ''} ${isHit(p.label) ? 'hit' : ''}`}>
            <td className="pl-name">{p.label}</td>
            <td className="pl-code">
              {p.code ? <code>{p.code}</code> : '—'}
              {p.system && <span className="pl-sys"> {p.system}</span>}
            </td>
            <td className="pl-date">{p.onset ?? '—'}</td>
            <td className="pl-tag">
              <span className={`pl-badge ${p.acute ? 'acute' : 'chronic'}`}>
                {p.acute ? 'This admission' : 'Chronic'}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )

  return (
    <div className="work">
      <div className="work-head">
        <h2>Problem List</h2>
        <span className="sub">
          {acute.length} active this admission · {chronic.length} chronic
        </span>
      </div>
      <div className="work-note">
        The four teams are each treating a different problem below — the reconciliation
        has to fold all of their orders into one home list.
      </div>

      {acute.length > 0 && (
        <>
          <h3 className="pl-section">Active — this admission</h3>
          <Table rows={acute} />
        </>
      )}
      <h3 className="pl-section">Chronic / ongoing</h3>
      <Table rows={chronic} />
    </div>
  )
}
