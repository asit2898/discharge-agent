import type { Flag, ReviewStatus } from '../types'
import { evidenceLinks, prettyType, SEVERITY_LABEL, STATUS_VERB } from '../recon'
import { Icon, type IconName } from './icons'

// Where to jump when a grounding link is clicked.
export interface SourceTarget {
  tab: string
  highlight: string
}

const CHIP_ICON: Record<string, IconName> = {
  order: 'pill',
  lab: 'flask',
  condition: 'clipboard',
}

// Which catches live ONLY in the journey (the conversation across days + the temporal
// trend) — invisible to a records *snapshot*, and to every FHIR-only tool. This is the
// wedge: Epic reconciles the snapshot; we reconcile the journey.
const JOURNEY_TYPES = new Set([
  'cross_prescriber_conflict', 'mentioned_not_recorded', 'discontinued_but_active',
  'adverse_drug_event', 'history_mismatch', 'orphaned_course', 'dropped_result',
])
const isJourney = (t: string) => JOURNEY_TYPES.has(t)

// A med can have several flags; group them so the panel shows ALL of a medication's
// issues (matching the tags on its table row), not just the one clicked.
const medKey = (f: Flag) => f.chart_evidence?.resource_id || f.med_name || f.id

function FlagCard({
  flag,
  status,
  onAct,
  onOpenSource,
  hideActions = false,
}: {
  flag: Flag
  status: ReviewStatus
  onAct: (id: string, s: ReviewStatus) => void
  onOpenSource?: (target: SourceTarget) => void
  hideActions?: boolean
}) {
  const sev = flag.severity === 'high' ? 'high' : 'moderate'
  const resolved = status !== 'pending'
  const links = evidenceLinks(flag)
  return (
    <div className={`flag-card ${sev} ${resolved ? 'resolved' : ''}`}>
      <div className="flag-top">
        <span className={`sev-pill ${sev}`}>{SEVERITY_LABEL[flag.severity]}</span>
        <span
          className={`catch-class ${isJourney(flag.type) ? 'journey' : 'snapshot'}`}
          title={
            isJourney(flag.type)
              ? 'Only detectable from the journey (the conversation + timeline) — invisible to a records snapshot'
              : 'Detectable from the discharge snapshot (the record alone)'
          }
        >
          {isJourney(flag.type) ? '◆ journey' : 'snapshot'}
        </span>
        <span className="flag-med">{flag.med_name ?? ''}</span>
      </div>
      <div className="flag-sub-row">
        <span className={`flag-tag ${sev}`}>{prettyType(flag.type)}</span>
      </div>
      <div className="flag-body">
        <div className="flag-expl">{flag.explanation}</div>

        {/* Grounding = links to the OTHER tabs where the reasons live. The spoken source
            (transcript) shows the quote; the chart reasons (ordered drug → Orders, cited
            lab → Results Review, condition → Problem List) are clickable chips. The flag's
            own med row is redundant, so it's never shown. */}
        {(flag.transcript_evidence || links.length > 0) && (
          <div className="grounded">
            <div className="grounded-head">Grounded in</div>

            {flag.transcript_evidence && (
              <button
                className={`ev-src transcript ${onOpenSource ? 'clickable' : ''}`}
                onClick={
                  onOpenSource
                    ? () =>
                        onOpenSource({ tab: 'Transcript', highlight: flag.transcript_evidence! })
                    : undefined
                }
                type="button"
              >
                <div className="ev-src-top">
                  <Icon name="mic" size={12} />
                  <span className="ev-src-label">Transcript</span>
                  {flag.transcript_speaker && (
                    <span className="ev-src-by">{flag.transcript_speaker}</span>
                  )}
                </div>
                <div className="ev-quote">“{flag.transcript_evidence}”</div>
                {onOpenSource && <div className="ev-open">Open in Transcript ›</div>}
              </button>
            )}

            {links.length > 0 && (
              <div className="ev-chips">
                {links.map((l, i) => (
                  <button
                    key={i}
                    className={`ev-chip ${l.kind}`}
                    onClick={
                      onOpenSource
                        ? () => onOpenSource({ tab: l.tab, highlight: l.highlight })
                        : undefined
                    }
                    title={`Open ${l.label} in ${l.tab}`}
                  >
                    <Icon name={CHIP_ICON[l.kind]} size={11} />
                    <span className="ev-chip-label">{l.label}</span>
                    <span className="ev-chip-tab">{l.tab} ›</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="fix">
          <span className="k">Suggested fix</span>
          <div>{flag.suggested_fix}</div>
        </div>
      </div>

      {hideActions ? null : resolved ? (
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
  statuses,
  onAct,
  onPend,
  selectedFlagId,
  onSelectFlag,
  onOpenSource,
}: {
  flags: Flag[]
  statuses: Record<string, ReviewStatus>
  onAct: (id: string, s: ReviewStatus) => void
  onPend: () => void
  selectedFlagId: string | null
  onSelectFlag: (id: string | null) => void
  onOpenSource?: (target: SourceTarget) => void
}) {
  const isPending = (f: Flag) => (statuses[f.id] ?? 'pending') === 'pending'
  const pending = flags.filter(isPending).length
  const journeyCount = flags.filter((f) => isJourney(f.type)).length
  const selected = flags.find((f) => f.id === selectedFlagId) ?? null

  // next unreviewed flag after `afterId`, wrapping around the queue
  const nextPending = (afterId: string | null): Flag | null => {
    const start = afterId ? flags.findIndex((f) => f.id === afterId) + 1 : 0
    const ordered = [...flags.slice(start), ...flags.slice(0, start)]
    return ordered.find(isPending) ?? null
  }

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

      {journeyCount > 0 && (
        <div className="journey-banner" title="These catches only exist in the conversation + timeline — a records snapshot, and every FHIR-only tool, is blind to them">
          <b>◆ {journeyCount} of {flags.length}</b> exist only in the <b>journey</b> — invisible to a records snapshot
        </div>
      )}

      {/* Detail-focused: only the alert being reviewed is expanded, never the whole wall */}
      <div className="copilot-detail">
        {flags.length === 0 ? (
          <div className="queue-empty">
            ✓ No discrepancies detected across sources for this encounter.
          </div>
        ) : selected ? (
          (() => {
            const key = medKey(selected)
            const group = flags.filter((f) => medKey(f) === key)
            // next pending issue on a DIFFERENT medication
            const nx = flags.find((f) => medKey(f) !== key && isPending(f))
            return (
              <>
                <button className="detail-back" onClick={() => onSelectFlag(null)}>
                  ✕ Close review
                </button>
                {group.length > 1 && (
                  <div className="detail-group-head">
                    <b>{group.length} issues</b> on {selected.med_name ?? 'this medication'} — all
                    fold into <b>one</b> disposition decision below.
                  </div>
                )}
                {group.map((f) => (
                  <FlagCard
                    key={f.id}
                    flag={f}
                    status={statuses[f.id] ?? 'pending'}
                    onAct={onAct}
                    onOpenSource={onOpenSource}
                    hideActions
                  />
                ))}
                {/* Decision controls always live at the end — same place whether the med
                    has one reason or several. */}
                <div className="med-decision">
                  <div className="med-decision-head">
                    {group.length > 1 ? 'One decision for this medication' : 'Your decision'}
                  </div>
                  <div className="flag-actions">
                    <button className="accept" onClick={() => group.forEach((f) => onAct(f.id, 'accepted'))}>
                      ✓ Accept {group.length > 1 ? 'plan' : 'fix'}
                    </button>
                    <button className="edit" onClick={() => group.forEach((f) => onAct(f.id, 'edited'))}>
                      ✎ Edit
                    </button>
                    <button className="reject" onClick={() => group.forEach((f) => onAct(f.id, 'rejected'))}>
                      ✕ Dismiss{group.length > 1 ? ' all' : ''}
                    </button>
                  </div>
                </div>
                {nx ? (
                  <button className="detail-next" onClick={() => onSelectFlag(nx.id)}>
                    Next medication ›
                  </button>
                ) : (
                  <div className="detail-done">✓ Nothing left to review</div>
                )}
              </>
            )
          })()
        ) : (
          <div className="detail-empty">
            <div className="de-icon">✦</div>
            <div className="de-title">
              {pending > 0
                ? `${pending} proposal${pending > 1 ? 's' : ''} to review`
                : 'All proposals reviewed'}
            </div>
            <div className="de-text">
              Select a flagged medication to see its grounded evidence and decide.
              Reviewing one at a time keeps the focus tight.
            </div>
            {pending > 0 && (
              <button
                className="de-btn"
                onClick={() => onSelectFlag(nextPending(null)?.id ?? null)}
              >
                Review next ›
              </button>
            )}
          </div>
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
