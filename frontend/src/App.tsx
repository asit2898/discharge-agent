import { useEffect, useMemo, useState } from 'react'
import { api } from './api'
import type {
  EncounterDetail,
  EncounterSummary,
  Reconciliation,
  ReviewStatus,
} from './types'
import { Storyboard } from './components/Storyboard'
import { NavigatorSidebar } from './components/NavigatorSidebar'
import { MedRecWorkspace } from './components/MedRecWorkspace'
import { CopilotPanel } from './components/CopilotPanel'

type Drawer = 'transcript' | 'note' | 'avs'

// Epic Hyperdrive activity toolbar — the row of chart activities. "Discharge" is the
// open activity; the rest are chrome that grounds the demo in a real inpatient chart.
const ACTIVITIES = [
  'Snapshot',
  'Chart Review',
  'Results Review',
  'Notes',
  'Orders',
  'MAR',
  'Discharge',
  'Discharge Summary',
]

export default function App() {
  const [encounters, setEncounters] = useState<EncounterSummary[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<EncounterDetail | null>(null)
  const [recon, setRecon] = useState<Reconciliation | null>(null)
  const [statuses, setStatuses] = useState<Record<string, ReviewStatus>>({})
  const [activeStep, setActiveStep] = useState('medrec')
  const [drawer, setDrawer] = useState<Drawer>('transcript')
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
        <select
          className="mb-switch"
          value={selectedId ?? ''}
          onChange={(e) => setSelectedId(e.target.value)}
        >
          {encounters.map((e) => (
            <option key={e.id} value={e.id}>
              {e.is_hero ? '★ ' : ''}
              {e.visit_title ?? e.id}
              {e.flag_count ? ` — ${e.flag_count} flags` : ''}
            </option>
          ))}
        </select>
      </div>

      <div className="epic-activities">
        {ACTIVITIES.map((a) => (
          <button key={a} className={`activity ${a === 'Discharge' ? 'active' : ''}`}>
            {a}
          </button>
        ))}
      </div>

      <div className="epic-body">
        {detail && <Storyboard header={detail.header} current={current} />}

        <NavigatorSidebar
          active={activeStep}
          medrecBadge={openCount}
          onSelect={setActiveStep}
        />

        {loading || !detail || !recon ? (
          <div className="work">
            <div className="center-msg">Loading encounter…</div>
          </div>
        ) : (
          <>
            <div className="work" style={{ padding: 0 }}>
              <MedRecWorkspace
                meds={recon.draft_meds}
                flags={flags}
                title={(current?.visit_title as string) ?? ''}
                subtitle={`${detail.header.name} · ${current?.date ?? ''}`}
                isHero={!!current?.is_hero}
              />

              <div style={{ padding: '0 20px 20px' }}>
                <div className="drawer-tabs">
                  {(['transcript', 'note', 'avs'] as Drawer[]).map((d) => (
                    <button
                      key={d}
                      className={drawer === d ? 'active' : ''}
                      onClick={() => setDrawer(d)}
                    >
                      {d === 'avs' ? 'After-Visit Summary' : d[0].toUpperCase() + d.slice(1)}
                    </button>
                  ))}
                </div>
                <div className="drawer-pane">
                  {drawer === 'transcript'
                    ? detail.transcript || '(no transcript)'
                    : drawer === 'note'
                      ? detail.note || '(no note)'
                      : detail.after_visit_summary || '(no summary)'}
                </div>
              </div>
            </div>

            <CopilotPanel
              flags={flags}
              stats={recon.stats}
              statuses={statuses}
              onAct={act}
              onPend={pend}
            />
          </>
        )}
      </div>
    </div>
  )
}
