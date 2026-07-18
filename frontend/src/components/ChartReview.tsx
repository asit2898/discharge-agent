import type { EncounterDetail } from '../types'
import { Icon, type IconName } from './icons'

// Epic Chart Review = the encounter's document index: every note, result set, and summary
// filed against this admission, each a row you open. Here it's the manifest of sources the
// copilot reasons over — clicking a row jumps to that activity. Counts are read from the
// loaded encounter so the index can't drift from what's actually on the chart.

function words(s: string): number {
  return s.trim() ? s.trim().split(/\s+/).length : 0
}

export function ChartReview({
  detail,
  onOpen,
}: {
  detail: EncounterDetail
  onOpen: (activity: string) => void
}) {
  const abnormal = detail.labs.filter((l) => l.abnormal).length
  const drawSets = new Set(detail.labs.map((l) => l.when).filter(Boolean)).size

  const docs: {
    title: string
    kind: string
    icon: IconName
    meta: string
    activity: string
  }[] = [
    {
      title: 'Progress / Discharge Note',
      kind: 'Note',
      icon: 'note',
      meta: `${words(detail.note).toLocaleString()} words`,
      activity: 'Notes',
    },
    {
      title: 'Ambient Visit Transcript',
      kind: 'Ambient',
      icon: 'mic',
      meta: `${words(detail.transcript).toLocaleString()} words`,
      activity: 'Transcript',
    },
    {
      title: 'Laboratory Results',
      kind: 'Results',
      icon: 'flask',
      meta: `${detail.labs.length} results · ${drawSets} draw sets · ${abnormal} abnormal`,
      activity: 'Results Review',
    },
    {
      title: 'After-Visit Summary',
      kind: 'AVS',
      icon: 'note',
      meta: `${words(detail.after_visit_summary).toLocaleString()} words`,
      activity: 'Discharge Summary',
    },
  ]

  return (
    <div className="work">
      <div className="work-head">
        <h2>Chart Review</h2>
        <span className="sub">{docs.length} documents on this encounter</span>
      </div>
      <div className="work-note">
        Every source the copilot reasons over, filed against this admission. Open a row to read
        it — the reconciliation cross-references all of them at once.
      </div>

      <table className="chartrev">
        <thead>
          <tr>
            <th className="cr-type">Type</th>
            <th className="cr-title">Document</th>
            <th className="cr-meta">Detail</th>
            <th className="cr-open" />
          </tr>
        </thead>
        <tbody>
          {docs.map((d) => (
            <tr key={d.title} className="cr-row" onClick={() => onOpen(d.activity)}>
              <td className="cr-type">
                <span className="cr-kind">
                  <Icon name={d.icon} size={13} /> {d.kind}
                </span>
              </td>
              <td className="cr-title">{d.title}</td>
              <td className="cr-meta">{d.meta}</td>
              <td className="cr-open">
                <span className="cr-open-link">Open ›</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
