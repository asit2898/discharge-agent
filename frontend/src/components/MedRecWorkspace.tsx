import type { Flag, Med } from '../types'
import { flagForMed, prettyType, sigOf } from '../recon'

const SOURCE_LABEL: Record<string, string> = {
  home: 'Prior to Admission',
  inpatient: 'Hospital',
  discharge: 'Hospital',
  transcript: 'Spoken only',
}

function SourcePill({ source }: { source: Med['source'] }) {
  return <span className={`src-pill src-${source}`}>{SOURCE_LABEL[source] ?? source}</span>
}

// Epic discharge Med Rec disposition: every home/inpatient med is reconciled with one
// of three actions. Clean rows default to Continue; rows the copilot flagged are held
// as "unreconciled" (no action selected) with a review cue — that's the seam our
// copilot fills.
function Disposition({ flagged, moderate }: { flagged: boolean; moderate: boolean }) {
  return (
    <div className={`disp-seg ${flagged ? (moderate ? 'moderate' : 'high') : ''}`}>
      <span className={`seg ${flagged ? '' : 'on'}`}>Continue</span>
      <span className="seg">Modify</span>
      <span className="seg">Don't Continue</span>
    </div>
  )
}

export function MedRecWorkspace({
  meds,
  flags,
  title,
  subtitle,
  isHero,
}: {
  meds: Med[]
  flags: Flag[]
  title: string
  subtitle: string
  isHero: boolean
}) {
  return (
    <div className="work">
      <div className="work-head">
        <h2>Medication Reconciliation</h2>
        <span className="sub">{subtitle}</span>
      </div>
      <div className="work-note">
        {isHero ? (
          <>
            Draft reconciled list assembled from <b>4 prescribing teams</b>. Rows the
            copilot flagged are highlighted — resolve them in the panel on the right, then
            sign. {title}
          </>
        ) : (
          <>
            Pre-populated from the chart. This encounter has no planted discrepancies; the
            copilot queue is empty. Open the <b>hero discharge</b> from the top switcher to
            see multi-team conflict detection.
          </>
        )}
      </div>

      {meds.length === 0 ? (
        <div className="center-msg">No medications recorded for this encounter.</div>
      ) : (
        <table className="medrec">
          <thead>
            <tr>
              <th>Medication</th>
              <th>Sig</th>
              <th>Source</th>
              <th>Ordered By</th>
              <th className="th-disp">Discharge Disposition</th>
            </tr>
          </thead>
          <tbody>
            {meds.map((med) => {
              const flag = flagForMed(med, flags)
              const mod = flag?.severity === 'moderate'
              return (
                <tr key={med.id} className={flag ? `flagged ${mod ? 'moderate' : ''}` : ''}>
                  <td>
                    <div className="med-name">{med.name}</div>
                    {flag && (
                      <div className={`flag-inline ${mod ? 'moderate' : ''}`}>
                        ⚠ {prettyType(flag.type)} — see Copilot
                      </div>
                    )}
                  </td>
                  <td className="med-sig">{sigOf(med)}</td>
                  <td>
                    <SourcePill source={med.source} />
                  </td>
                  <td className="med-sig">{med.prescriber?.name ?? '—'}</td>
                  <td>
                    <Disposition flagged={!!flag} moderate={mod} />
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
}
