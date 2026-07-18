import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import type {
  EncounterDetail,
  EncounterSummary,
  Flag,
  Reconciliation,
  ReviewStatus,
} from './types'
import { Storyboard } from './components/Storyboard'
import { NavigatorSidebar, DISCHARGE_STEPS } from './components/NavigatorSidebar'
import { MedRecWorkspace } from './components/MedRecWorkspace'
import { CopilotPanel } from './components/CopilotPanel'
import { ResultsReview } from './components/ResultsReview'
import { ProblemList } from './components/ProblemList'
import { TranscriptView } from './components/TranscriptView'
import { Snapshot } from './components/Snapshot'
import { ChartReview } from './components/ChartReview'
import { OrdersView } from './components/OrdersView'
import { Icon, type IconName } from './components/icons'

// Epic Hyperdrive activity toolbar — the row of chart activities, each with its own
// icon. Every source the copilot reasons over is a first-class top-level tab here:
// Notes, Results Review (labs), Transcript (ambient), and Discharge Summary (AVS).
// "Discharge" is the reconciliation activity where the copilot lives.
const ACTIVITIES: { label: string; icon: IconName }[] = [
  { label: 'Snapshot', icon: 'grid' },
  { label: 'Chart Review', icon: 'clipboard' },
  { label: 'Results Review', icon: 'flask' },
  { label: 'Notes', icon: 'note' },
  { label: 'Transcript', icon: 'mic' },
  { label: 'Orders', icon: 'list' },
  { label: 'Discharge', icon: 'home' },
  { label: 'Discharge Summary', icon: 'note' },
]

// Full-view reader for a text source (note / transcript / AVS) shown as a top-level tab.
function SourceView({
  title,
  subtitle,
  text,
}: {
  title: string
  subtitle?: string
  text: string
}) {
  return (
    <div className="work">
      <div className="work-head">
        <h2>{title}</h2>
        {subtitle && <span className="sub">{subtitle}</span>}
      </div>
      <div className="source-pane">{text || '(none on file for this encounter)'}</div>
    </div>
  )
}

export default function App() {
  const [encounters, setEncounters] = useState<EncounterSummary[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<EncounterDetail | null>(null)
  const [recon, setRecon] = useState<Reconciliation | null>(null)
  const [statuses, setStatuses] = useState<Record<string, ReviewStatus>>({})
  const [selectedFlagId, setSelectedFlagId] = useState<string | null>(null)
  const [evidence, setEvidence] = useState<{ text: string } | null>(null)
  const [activeStep, setActiveStep] = useState('medrec')
  const [activeActivity, setActiveActivity] = useState('Discharge')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Load the encounter list once; default-select the hero.
  useEffect(() => {
    api
      .listEncounters()
      .then((list) => {
        setEncounters(list)
        const hero = list.find((e) => e.is_hero) ?? list[0]
        setSelectedId(hero?.id ?? null)
      })
      .catch((e) => setError(String(e)))
  }, [])

  // Load detail + reconciliation whenever the selection changes.
  useEffect(() => {
    if (!selectedId) return
    setLoading(true)
    setStatuses({})
    setSelectedFlagId(null)
    setEvidence(null)
    Promise.all([api.getEncounter(selectedId), api.reconcile(selectedId)])
      .then(([d, r]) => {
        setDetail(d)
        setRecon(r)
        setError(null)
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
  }, [selectedId])

  const current = useMemo(
    () => encounters.find((e) => e.id === selectedId) ?? null,
    [encounters, selectedId],
  )

  const flags = recon?.flags ?? []
  const openCount = flags.filter((f) => (statuses[f.id] ?? 'pending') === 'pending').length

  const act = (id: string, s: ReviewStatus) =>
    setStatuses((prev) => ({ ...prev, [id]: s }))

  const pend = () =>
    alert(
      'Draft pended into Epic’s discharge Med Rec activity.\n\n' +
        'In production this writes the reconciled orders back through the Abridge/Epic ' +
        'embed as a pended draft — the physician reviews and signs. We never sign.',
    )

  // Jump from a flag's grounding to the tab that holds its proof, and highlight it there.
  const openSource = (flag: Flag, which: 'transcript' | 'chart') => {
    if (which === 'transcript' && flag.transcript_evidence) {
      setActiveActivity('Transcript')
      setEvidence({ text: flag.transcript_evidence })
      return
    }
    const ce = flag.chart_evidence
    if (!ce) return
    if (ce.resource_type === 'Observation') {
      setActiveActivity('Results Review')
      setEvidence({ text: ce.display ?? '' })
    } else if (ce.resource_type === 'Condition') {
      setActiveActivity('Discharge')
      setActiveStep('problems')
      setEvidence({ text: ce.display ?? '' })
    } else {
      // MedicationRequest / AllergyIntolerance → the Med Rec row (already highlighted)
      setActiveActivity('Discharge')
      setActiveStep('medrec')
      setEvidence(null)
    }
  }

  if (error) {
    return (
      <div className="center-msg">
        <p>⚠ Could not reach the backend.</p>
        <pre style={{ fontSize: 12 }}>{error}</pre>
        <p>
          Start it: <code>uvicorn discharge_agent.main:app --reload</code> (port 8000)
        </p>
      </div>
    )
  }

  return (
    <div className="epic-app">
      <div className="epic-menubar">
        <span className="brand">
          <span className="epic-mark">✚</span> Epic
        </span>
        <span className="mb-item">Hyperdrive</span>
        <span className="mb-item">Inpatient</span>
        <span className="mb-item">Discharge</span>
        <label className="mb-search">
          <Icon name="search" size={13} />
          <select
            className="mb-switch"
            value={selectedId ?? ''}
            onChange={(e) => setSelectedId(e.target.value)}
          >
            {encounters.map((e) => (
              <option key={e.id} value={e.id}>
                {e.visit_title ?? e.id}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="epic-activities">
        <div className="activity-nav">
          <button title="Back">
            <Icon name="back" size={14} />
          </button>
          <button title="Forward">
            <Icon name="forward" size={14} />
          </button>
        </div>
        {ACTIVITIES.map((a) => (
          <button
            key={a.label}
            className={`activity ${a.label === activeActivity ? 'active' : ''}`}
            onClick={() => {
              setActiveActivity(a.label)
              setEvidence(null)
            }}
          >
            <Icon name={a.icon} size={13} />
            {a.label}
          </button>
        ))}
        <button className="activity-tool" title="Personalize activity toolbar">
          <Icon name="wrench" size={15} />
        </button>
      </div>

      <div className="epic-body">
        {detail && <Storyboard header={detail.header} current={current} />}

        {loading || !detail || !recon ? (
          <div className="work">
            <div className="center-msg">Loading encounter…</div>
          </div>
        ) : activeActivity === 'Results Review' ? (
          <ResultsReview labs={detail.labs} highlight={evidence?.text} />
        ) : activeActivity === 'Notes' ? (
          <SourceView title="Progress Notes" text={detail.note} />
        ) : activeActivity === 'Transcript' ? (
          <TranscriptView text={detail.transcript} highlight={evidence?.text} />
        ) : activeActivity === 'Discharge Summary' ? (
          <SourceView title="After-Visit Summary" text={detail.after_visit_summary} />
        ) : activeActivity === 'Snapshot' ? (
          <Snapshot detail={detail} />
        ) : activeActivity === 'Chart Review' ? (
          <ChartReview detail={detail} onOpen={setActiveActivity} />
        ) : activeActivity === 'Orders' ? (
          <OrdersView
            meds={detail.meds}
            title="Orders"
            note="The active order profile grouped by origin. Read-only here — the editable reconciliation lives in the Discharge → Med Rec activity."
          />
        ) : activeActivity !== 'Discharge' ? (
          <div className="work">
            <div className="center-msg">
              <p style={{ fontWeight: 600 }}>{activeActivity}</p>
              <p style={{ fontSize: 13, color: '#64748b' }}>
                Chart context that grounds the demo. The copilot lives in the{' '}
                <strong>Discharge</strong> activity; every source it reasons over is a
                top-level tab (Notes · Results Review · Transcript · Discharge Summary).
              </p>
            </div>
          </div>
        ) : (
          <>
            <NavigatorSidebar
              active={activeStep}
              medrecBadge={openCount}
              onSelect={setActiveStep}
            />
            {activeStep === 'problems' ? (
              <ProblemList problems={detail.problems} highlight={evidence?.text} />
            ) : activeStep === 'orders' ? (
              <OrdersView
                meds={detail.meds}
                title="Discharge Orders"
                subtitle="Home-going medication list"
                sources={['home', 'discharge']}
                note="The reconciled list the patient goes home on — home meds continued plus new discharge orders. Finalize the proposals in Med Rec and Orders to lock this list."
              />
            ) : activeStep === 'avs' ? (
              <SourceView
                title="Patient Instructions (AVS)"
                subtitle="After-Visit Summary — printed for the patient"
                text={detail.after_visit_summary}
              />
            ) : activeStep !== 'medrec' ? (
              <div className="work">
                <div className="center-msg">
                  <p style={{ fontWeight: 600 }}>
                    {DISCHARGE_STEPS.find((s) => s.key === activeStep)?.label}
                  </p>
                  <p style={{ fontSize: 13, color: '#64748b' }}>
                    This Navigator step isn’t part of the copilot demo. Select{' '}
                    <strong>Med Rec and Orders</strong> to return to the reconciliation view.
                  </p>
                </div>
              </div>
            ) : (
              <>
                <div className="work" style={{ padding: 0 }}>
                  <MedRecWorkspace
                    meds={recon.draft_meds}
                    flags={flags}
                    statuses={statuses}
                    onAct={act}
                    selectedFlagId={selectedFlagId}
                    onSelectFlag={setSelectedFlagId}
                    title={(current?.visit_title as string) ?? ''}
                    subtitle={`${detail.header.name} · ${current?.date ?? ''}`}
                    isHero={!!current?.is_hero}
                  />

                  {/* Epic activity footer — the native action bar that closes a Navigator step */}
                  <div className="work-actionbar">
                    <button className="wa-btn" onClick={() => setStatuses({})}>
                      <Icon name="x" size={13} /> Cancel
                    </button>
                    <div className="wa-spacer" />
                    <span className="wa-hint">
                      {openCount > 0
                        ? `${openCount} proposal${openCount === 1 ? '' : 's'} left to review`
                        : 'All proposals reviewed — ready to reconcile'}
                    </span>
                    <button className="wa-btn primary" disabled={openCount > 0} onClick={pend}>
                      <Icon name="check" size={14} /> Reconcile — Close (F9)
                    </button>
                  </div>
                </div>

                {selectedFlagId && (
                  <CopilotPanel
                    flags={flags}
                    statuses={statuses}
                    onAct={act}
                    onPend={pend}
                    selectedFlagId={selectedFlagId}
                    onSelectFlag={setSelectedFlagId}
                    onOpenSource={openSource}
                  />
                )}
              </>
            )}
          </>
        )}
      </div>

      <div className="epic-footer">
        <span className="ef-env">PRD</span>
        <span>{detail ? detail.header.name : '—'}</span>
        <span className="ef-sep">·</span>
        <span>Encounter: Inpatient Discharge</span>
        <span className="ef-right">
          <Icon name="printer" size={13} /> Ready
          <span className="ef-sep">·</span>
          A. Neema, MD · WROC
        </span>
      </div>
    </div>
  )
}
