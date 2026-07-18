import type { Flag, Med, ReviewStatus } from '../types'
import { DISP_LABEL, prettyType, proposedDisp, sigOf, type Disp } from '../recon'
import { Icon, type IconName } from './icons'

// Med Rec, matched to Epic's discharge reconciliation activity — but arriving already
// drafted by the copilot. ONE decision per medication (a clinician sets a single
// disposition per drug even when there are several reasons); the row shows the copilot's
// proposal vs. the default, and the full grounding opens in the side panel on click.
// Findings with no order line split out: "Medications to Add" (spoken but never ordered)
// and a slim "Other catches" note (non-medication: a history fix, a lab recheck).

interface Group {
  key: string
  title: string
  icon: IconName
  sources: Med['source'][]
}

const GROUPS: Group[] = [
  { key: 'pta', title: 'Prior to Admission', icon: 'home', sources: ['home'] },
  { key: 'hosp', title: 'Hospital Orders', icon: 'bed', sources: ['inpatient', 'discharge'] },
]

// --- flag ↔ med matching (a med can own several flags) -----------------------
function medMatches(flag: Flag, med: Med): boolean {
  if (flag.chart_evidence?.resource_id && flag.chart_evidence.resource_id === med.id) return true
  if (flag.med_name && med.name.toLowerCase().startsWith(flag.med_name.toLowerCase())) return true
  return false
}
function medFlagsFor(med: Med, flags: Flag[]): Flag[] {
  return flags.filter((f) => medMatches(f, med))
}

// The status-quo disposition (what happens without the copilot). Active orders default to
// Continue; a dropped home med defaults to "Don't continue" (it fell off the draft).
function defaultDisp(flag: Flag): Disp {
  if (flag.type === 'dropped_home_med') return 'discontinue'
  return 'continue'
}
const DEFAULT_LABEL: Record<Disp, string> = {
  continue: 'Continue',
  modify: 'Modify',
  discontinue: "Don't continue",
}

// resolve the effective button selection + review state from the copilot proposal + action
function resolve(flag: Flag | undefined, status: ReviewStatus) {
  if (!flag) return { sel: 'continue' as Disp, state: 'reconciled' as const }
  const proposed = proposedDisp(flag)
  if (status === 'pending') return { sel: proposed, state: 'proposed' as const }
  if (status === 'edited') return { sel: 'modify' as Disp, state: 'confirmed' as const }
  if (status === 'rejected') return { sel: 'continue' as Disp, state: 'confirmed' as const }
  return { sel: proposed, state: 'confirmed' as const } // accepted
}

function ActionIcons({
  sel,
  state,
  onPick,
}: {
  sel: Disp
  state: 'reconciled' | 'proposed' | 'confirmed'
  onPick?: (d: Disp) => void
}) {
  const cls = (d: Disp) => (sel === d ? `on ${state}` : '')
  const pick = (d: Disp) => (onPick ? () => onPick(d) : undefined)
  return (
    <div className={`med-actions ${onPick ? 'live' : ''}`}>
      <button className={`act cont ${cls('continue')}`} title="Continue" onClick={pick('continue')}>
        <Icon name="check" size={15} />
      </button>
      <button className={`act mod ${cls('modify')}`} title="Modify" onClick={pick('modify')}>
        <Icon name="pencil" size={14} />
      </button>
      <button className={`act dc ${cls('discontinue')}`} title="Don't Continue" onClick={pick('discontinue')}>
        <Icon name="x" size={15} />
      </button>
    </div>
  )
}

// Map a physician's disposition click to the shared review status.
function statusForPick(flag: Flag, picked: Disp): ReviewStatus {
  const proposed = proposedDisp(flag)
  if (picked === proposed) return 'accepted'
  if (picked === 'modify') return 'edited'
  if (picked === 'continue') return 'rejected'
  return 'edited'
}

// The "Copilot proposes" cell — the DEFAULT selection → the copilot's PROPOSED
// disposition, then the catch-type tag(s) for every issue on this med (a med can have
// several). The reason sentence + full grounding live in the evidence panel on click.
function CopilotCell({
  flags,
  status,
  addMode = false,
}: {
  flags: Flag[]
  status: ReviewStatus
  addMode?: boolean
}) {
  const primary = flags[0]
  const proposed = proposedDisp(primary)
  const def = defaultDisp(primary)
  const proposedLabel = addMode ? 'Add order' : DISP_LABEL[proposed]
  const defaultLabel = addMode ? 'Not ordered' : DEFAULT_LABEL[def]
  const showDelta = addMode || def !== proposed
  const statusLabel =
    status === 'accepted'
      ? 'Confirmed'
      : status === 'edited'
        ? 'Edited'
        : status === 'rejected'
          ? 'Dismissed'
          : null
  return (
    <span className={`cop-cell ${status}`}>
      <span className="cop-cell-top">
        {showDelta && (
          <>
            <span className="cop-disp-default">{defaultLabel}</span>
            <span className="cop-arrow">→</span>
          </>
        )}
        <span className={`cop-disp ${proposed}`}>◆ {proposedLabel}</span>
        {statusLabel && <span className={`cop-cell-status ${status}`}>{statusLabel}</span>}
      </span>
      <span className="cop-cell-tags">
        {flags.map((f) => (
          <span key={f.id} className={`cop-tag sev-${f.severity}`}>
            {prettyType(f.type)}
          </span>
        ))}
        <span className="cop-cell-link">View evidence ›</span>
      </span>
    </span>
  )
}

const COLHEAD = (byLabel: string, actLabel: string) => (
  <div className="med-colhead">
    <span className="mc mc-pill" />
    <span className="mc mc-name">Medication</span>
    <span className="mc mc-sig">Sig</span>
    <span className="mc mc-by">{byLabel}</span>
    <span className="mc mc-cop">Copilot proposes</span>
    <span className="mc mc-act">{actLabel}</span>
  </div>
)

function MedRow({
  med,
  medFlags,
  statuses,
  onAct,
  selectedFlagId,
  onSelect,
}: {
  med: Med
  medFlags: Flag[]
  statuses: Record<string, ReviewStatus>
  onAct: (id: string, s: ReviewStatus) => void
  selectedFlagId: string | null
  onSelect: (id: string | null) => void
}) {
  const primary = medFlags[0]
  const anyPending = medFlags.some((f) => (statuses[f.id] ?? 'pending') === 'pending')
  const medStatus: ReviewStatus = !primary
    ? 'pending'
    : anyPending
      ? 'pending'
      : (statuses[primary.id] ?? 'pending')
  // Inpatient-only orders (IV fluids, stress-ulcer/nausea prophylaxis) don't go home —
  // they default to "Don't continue" at discharge, not "Continue".
  const inpatientStop = !primary && med.source === 'inpatient'
  const { sel, state } = primary
    ? resolve(primary, medStatus)
    : { sel: (inpatientStop ? 'discontinue' : 'continue') as Disp, state: 'reconciled' as const }
  const rowCls = primary && anyPending ? `flagged disp-${proposedDisp(primary)}` : ''
  // One decision per med: acting on the row applies to ALL of the med's flags.
  const onPick = primary
    ? (d: Disp) => {
        const s = statusForPick(primary, d)
        medFlags.forEach((f) => onAct(f.id, s))
      }
    : undefined
  const selected = !!primary && primary.id === selectedFlagId
  return (
    <div className={`med-item ${rowCls} ${selected ? 'selected' : ''}`}>
      <div
        className={`med-line ${primary ? 'clickable' : ''}`}
        onClick={primary ? () => onSelect(primary.id) : undefined}
        title={primary ? 'Review this proposal — evidence opens in the copilot panel' : undefined}
      >
        <span className="mc mc-pill">
          <Icon name="pill" size={14} />
        </span>
        <span className="mc mc-name">{med.name}</span>
        <span className="mc mc-sig">{sigOf(med)}</span>
        <span className="mc mc-by">{med.prescriber?.name ?? '—'}</span>
        <span className="mc mc-cop">
          {primary ? (
            <CopilotCell flags={medFlags} status={medStatus} />
          ) : inpatientStop ? (
            <span className="cop-none">Stop · inpatient order (routine)</span>
          ) : (
            <span className="cop-none">Continue · no change</span>
          )}
        </span>
        <span className="mc mc-act" onClick={(e) => e.stopPropagation()}>
          <ActionIcons sel={sel} state={state} onPick={onPick} />
        </span>
      </div>
    </div>
  )
}

function GroupCard({
  group,
  meds,
  flags,
  statuses,
  onAct,
  selectedFlagId,
  onSelectFlag,
}: {
  group: Group
  meds: Med[]
  flags: Flag[]
  statuses: Record<string, ReviewStatus>
  onAct: (id: string, s: ReviewStatus) => void
  selectedFlagId: string | null
  onSelectFlag: (id: string | null) => void
}) {
  if (meds.length === 0) return null
  const pendingIds = meds
    .flatMap((m) => medFlagsFor(m, flags))
    .filter((f) => (statuses[f.id] ?? 'pending') === 'pending')
    .map((f) => f.id)
  const medsToReview = meds.filter((m) =>
    medFlagsFor(m, flags).some((f) => (statuses[f.id] ?? 'pending') === 'pending'),
  ).length
  const acceptGroup = () => pendingIds.forEach((id) => onAct(id, 'accepted'))
  return (
    <div className="grp-card">
      <div className="grp-head">
        <span className="grp-ic">
          <Icon name={group.icon} size={15} />
        </span>
        <span className="grp-title">{group.title}</span>
        <span className="grp-count">{meds.length}</span>
        {medsToReview > 0 && <span className="grp-review">{medsToReview} to review</span>}
        <button
          className="grp-action"
          onClick={acceptGroup}
          disabled={pendingIds.length === 0}
          title="Accept all copilot proposals in this group"
        >
          Accept all proposals <Icon name="chevron" size={13} />
        </button>
      </div>
      <div className="grp-body">
        {COLHEAD('Ordered by', 'Disposition')}
        {meds.map((med) => (
          <MedRow
            key={med.id}
            med={med}
            medFlags={medFlagsFor(med, flags)}
            statuses={statuses}
            onAct={onAct}
            selectedFlagId={selectedFlagId}
            onSelect={onSelectFlag}
          />
        ))}
      </div>
    </div>
  )
}

// Medications discussed in the visit but never ordered — the copilot proposes ADDING them.
function AddMedsCard({
  flags,
  statuses,
  onAct,
  selectedFlagId,
  onSelectFlag,
}: {
  flags: Flag[]
  statuses: Record<string, ReviewStatus>
  onAct: (id: string, s: ReviewStatus) => void
  selectedFlagId: string | null
  onSelectFlag: (id: string | null) => void
}) {
  if (flags.length === 0) return null
  return (
    <div className="grp-card">
      <div className="grp-head add">
        <span className="grp-ic">
          <Icon name="list" size={15} />
        </span>
        <span className="grp-title">Medications to Add</span>
        <span className="grp-count">{flags.length}</span>
        <span className="grp-note">Discussed in the visit but never ordered — the copilot proposes adding</span>
      </div>
      <div className="grp-body">
        {COLHEAD('Proposed by', 'Action')}
        {flags.map((flag) => {
          const status = statuses[flag.id] ?? 'pending'
          const selected = flag.id === selectedFlagId
          const rowCls = status === 'pending' ? 'flagged disp-continue' : ''
          return (
            <div key={flag.id} className={`med-item ${rowCls} ${selected ? 'selected' : ''}`}>
              <div
                className="med-line clickable"
                onClick={() => onSelectFlag(flag.id)}
                title="Review this recommendation — evidence opens in the copilot panel"
              >
                <span className="mc mc-pill">
                  <Icon name="list" size={13} />
                </span>
                <span className="mc mc-name">{flag.med_name ?? prettyType(flag.type)}</span>
                <span className="mc mc-sig">—</span>
                <span className="mc mc-by">{flag.prescriber?.name ?? '—'}</span>
                <span className="mc mc-cop">
                  <CopilotCell flags={[flag]} status={status} addMode />
                </span>
                <span className="mc mc-act" onClick={(e) => e.stopPropagation()}>
                  <div className="med-actions live">
                    <button
                      className={`act cont ${status === 'accepted' ? 'on confirmed' : ''}`}
                      title="Add order"
                      onClick={() => onAct(flag.id, 'accepted')}
                    >
                      <Icon name="check" size={15} />
                    </button>
                    <button
                      className={`act dc ${status === 'rejected' ? 'on confirmed' : ''}`}
                      title="Dismiss"
                      onClick={() => onAct(flag.id, 'rejected')}
                    >
                      <Icon name="x" size={15} />
                    </button>
                  </div>
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// Non-medication catches (a charted-history mismatch, a dropped lab result). Slim, and
// reviewed in the side panel — deliberately kept out of the medication table.
function OtherCatchesCard({
  flags,
  statuses,
  selectedFlagId,
  onSelectFlag,
}: {
  flags: Flag[]
  statuses: Record<string, ReviewStatus>
  selectedFlagId: string | null
  onSelectFlag: (id: string | null) => void
}) {
  if (flags.length === 0) return null
  return (
    <div className="other-catches">
      <div className="oc-head">
        <span className="cop-star">✦</span> Other catches — not medications
        <span className="oc-count">{flags.length}</span>
      </div>
      {flags.map((f) => {
        const status = statuses[f.id] ?? 'pending'
        return (
          <button
            key={f.id}
            className={`oc-row ${f.id === selectedFlagId ? 'selected' : ''} ${status !== 'pending' ? 'done' : ''}`}
            onClick={() => onSelectFlag(f.id)}
          >
            <span className="oc-type">{prettyType(f.type)}</span>
            <span className="oc-text">{f.recommended_resolution}</span>
            <span className="oc-view">Review ›</span>
          </button>
        )
      })}
    </div>
  )
}

export function MedRecWorkspace({
  meds,
  flags,
  statuses,
  onAct,
  selectedFlagId,
  onSelectFlag,
  title,
  subtitle,
  isHero,
}: {
  meds: Med[]
  flags: Flag[]
  statuses: Record<string, ReviewStatus>
  onAct: (id: string, s: ReviewStatus) => void
  selectedFlagId: string | null
  onSelectFlag: (id: string | null) => void
  title: string
  subtitle: string
  isHero: boolean
}) {
  // Flags that reference an existing med stay on its row; the rest split by kind.
  const attached = new Set(
    flags.filter((f) => meds.some((m) => medMatches(f, m))).map((f) => f.id),
  )
  const looseFlags = flags.filter((f) => !attached.has(f.id))
  const addMeds = looseFlags.filter((f) => f.type === 'mentioned_not_recorded')
  const otherCatches = looseFlags.filter((f) => f.type !== 'mentioned_not_recorded')

  // Decision-based counts: one decision per flagged med + each loose finding.
  const flaggedMeds = meds.filter((m) => medFlagsFor(m, flags).length > 0)
  const totalDecisions = flaggedMeds.length + looseFlags.length
  const isPending = (f: Flag) => (statuses[f.id] ?? 'pending') === 'pending'
  const pendingDecisions =
    flaggedMeds.filter((m) => medFlagsFor(m, flags).some(isPending)).length +
    looseFlags.filter(isPending).length
  const reviewed = totalDecisions - pendingDecisions

  return (
    <div className="work">
      <div className="work-head">
        <h2>Medication Reconciliation</h2>
        <span className="sub">{subtitle}</span>
      </div>

      <div className="adt-tabs">
        <span className="adt">Admission</span>
        <span className="adt">Transfer</span>
        <span className="adt active">Discharge</span>
      </div>

      <div className="medrec-status">
        <span className={`mr-badge ${pendingDecisions ? 'open' : 'ok'}`}>
          <span className="cop-star">✦</span>{' '}
          {pendingDecisions ? 'Copilot draft — review proposals' : 'All proposals reviewed'}
        </span>
        <span className="mr-meta">{meds.length} medications</span>
        <span className="mr-meta">·</span>
        <span className="mr-meta">{totalDecisions} proposals</span>
        <span className="mr-meta">·</span>
        <span className="mr-meta">
          {reviewed}/{totalDecisions} confirmed
        </span>
        {isHero && <span className="mr-title">{title}</span>}
      </div>

      {meds.length === 0 ? (
        <div className="center-msg">No medications recorded for this encounter.</div>
      ) : (
        <>
          {GROUPS.map((g) => (
            <GroupCard
              key={g.key}
              group={g}
              meds={meds.filter((m) => g.sources.includes(m.source))}
              flags={flags}
              statuses={statuses}
              onAct={onAct}
              selectedFlagId={selectedFlagId}
              onSelectFlag={onSelectFlag}
            />
          ))}
          <AddMedsCard
            flags={addMeds}
            statuses={statuses}
            onAct={onAct}
            selectedFlagId={selectedFlagId}
            onSelectFlag={onSelectFlag}
          />
          <OtherCatchesCard
            flags={otherCatches}
            statuses={statuses}
            selectedFlagId={selectedFlagId}
            onSelectFlag={onSelectFlag}
          />
        </>
      )}
    </div>
  )
}
