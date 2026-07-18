import type { Flag, ReconStats, ReviewStatus } from '../types'
import { prettyType, SEVERITY_LABEL, STATUS_VERB } from '../recon'

function FlagCard({
  flag,
  status,
  onAct,
}: {
  flag: Flag
  status: ReviewStatus
  onAct: (id: string, s: ReviewStatus) => void
}) {
  const sev = flag.severity === 'high' ? 'high' : 'moderate'
  const resolved = status !== 'pending'
  return (
    <div className={`flag-card ${sev} ${resolved ? 'resolved' : ''}`}>
      <div className="flag-top">
        <span className={`sev-pill ${sev}`}>{SEVERITY_LABEL[flag.severity]}</span>
        <span className="flag-type">{prettyType(flag.type)}</span>
        <span className="flag-med">{flag.med_name ?? ''}</span>
      </div>
      <div className="flag-body">
        <div className="flag-expl">{flag.explanation}</div>

        {flag.transcript_evidence && (
          <div className="evidence">
            <div className="who">🎙 {flag.transcript_speaker ?? 'Transcript'}</div>
            <div className="quote">“{flag.transcript_evidence}”</div>
          </div>
        )}

        {flag.chart_evidence && (
          <div className="chart-ev">
            📋 <b>{flag.chart_evidence.resource_type}</b>
            {flag.chart_evidence.display ? ` — ${flag.chart_evidence.display}` : ''}
          </div>
        )}

        <div className="fix">
          <span className="k">Suggested fix</span>
          <div>{flag.suggested_fix}</div>
        </div>
      </div>

      {resolved ? (
        <div className="resolved-note">
          <b className={status}>{STATUS_VERB[status]}</b>
          {' — '}
          {status === 'accepted'
            ? flag.recommended_resolution
            : status === 'rejected'
              ? 'Flag dismissed; no change to the order.'
              : 'Sent to the order editor for manual change.'}
          {'  '}
          <button
            className="edit"
            style={{ border: 'none', background: 'none', color: 'var(--epic-blue)', padding: 0 }}
            onClick={() => onAct(flag.id, 'pending')}
          >
            undo
          </button>
        </div>
      ) : (
        <div className="flag-actions">
          <button className="accept" onClick={() => onAct(flag.id, 'accepted')}>
            ✓ Accept fix
          </button>
          <button className="edit" onClick={() => onAct(flag.id, 'edited')}>
            ✎ Edit
          </button>
          <button className="reject" onClick={() => onAct(flag.id, 'rejected')}>
            ✕ Dismiss
          </button>
        </div>
      )}
    </div>
  )
}

export function CopilotPanel({
  flags,
  stats,
  statuses,
  onAct,
  onPend,
}: {
  flags: Flag[]
  stats: ReconStats
  statuses: Record<string, ReviewStatus>
  onAct: (id: string, s: ReviewStatus) => void
  onPend: () => void
}) {
  const pending = flags.filter((f) => (statuses[f.id] ?? 'pending') === 'pending').length
  return (
    <aside className="copilot">
      <div className="copilot-head">
        <div className="row1">
          <span className="logo">✦</span>
          <span className="title">Reconciliation Copilot</span>
          <span className="smart">SMART on FHIR</span>
        </div>
        <div className="tag">Abridge safety-catch · pends a draft for you to sign</div>
      </div>

      <div className="copilot-stats">
        <div className="stat">
          <div className="n">{stats.total_meds}</div>
          <div className="l">Meds</div>
        </div>
        <div className="stat">
          <div className="n">{stats.agree_count}</div>
          <div className="l">Agree</div>
        </div>
        <div className="stat high">
          <div className="n">{stats.flag_count}</div>
          <div className="l">To decide</div>
        </div>
      </div>

      <div className="queue">
        {flags.length === 0 ? (
          <div className="queue-empty">
            ✓ No discrepancies detected across sources for this encounter.
          </div>
        ) : (
          flags.map((f) => (
            <FlagCard
              key={f.id}
              flag={f}
              status={statuses[f.id] ?? 'pending'}
              onAct={onAct}
            />
          ))
        )}
      </div>

      {flags.length > 0 && (
        <div className="copilot-foot">
          <button className="pend-btn" disabled={pending > 0} onClick={onPend}>
            {pending > 0 ? `${pending} left to review` : 'Pend draft into Epic'}
          </button>
          <span className="pend-hint">
            Physician signs.
            <br />
            We never sign.
          </span>
        </div>
      )}
    </aside>
  )
}
