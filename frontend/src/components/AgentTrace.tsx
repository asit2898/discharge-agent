import { useState } from 'react'
import type { AgentEvent } from '../types'

// A readable label for each tool the agent can call.
const TOOL_LABEL: Record<string, string> = {
  get_medication_table: 'Read medication table',
  get_labs: 'Read labs',
  get_problem_list: 'Read problem list',
  get_allergies: 'Read allergies',
  search_transcript: 'Search transcript + note',
  run_safety_check: 'Run safety check',
  confirm_issue: 'Confirm issue + draft action',
  dismiss_issue: 'Dismiss (false positive)',
  finish: 'Finish reconciliation',
}

const toolLabel = (t: string | null) => (t ? TOOL_LABEL[t] ?? t : '')

// Show the salient argument inline (the check name, the search query, the disposition).
function argHint(ev: AgentEvent): string {
  const i = ev.input ?? {}
  const v = (i.check ?? i.query ?? i.disposition ?? i.candidate_id) as string | undefined
  return v ? ` · ${v}` : ''
}

// The orchestrator agent's step-by-step loop — the "agentic" receipt. This is what makes
// the difference from a fixed workflow visible: the model chose each of these steps.
export function AgentTrace({
  trace,
  mode,
  flagCount,
}: {
  trace: AgentEvent[]
  mode: 'agent' | 'workflow'
  flagCount: number
}) {
  const [open, setOpen] = useState(false)
  if (mode !== 'agent' || trace.length === 0) return null

  const actions = trace.filter((e) => e.kind === 'action')
  const checks = actions.filter((e) => e.tool === 'run_safety_check').length
  const investigations = actions.filter(
    (e) => e.tool === 'search_transcript' || e.tool?.startsWith('get_'),
  ).length

  return (
    <div className={`agent-trace ${open ? 'open' : ''}`}>
      <button className="agent-trace-head" onClick={() => setOpen((o) => !o)}>
        <span className="at-badge">✦ Agent</span>
        <span className="at-summary">
          Drove <b>{actions.length}</b> steps — {investigations} investigations, {checks} safety
          checks — to confirm <b>{flagCount}</b> issues
        </span>
        <span className="at-chevron">{open ? '▾' : '▸'}</span>
      </button>

      {open && (
        <ol className="agent-trace-steps">
          {trace.map((ev, i) =>
            ev.kind === 'thought' ? (
              <li key={i} className="at-thought">
                <span className="at-icon">💭</span>
                <span className="at-text">{ev.text}</span>
              </li>
            ) : (
              <li key={i} className="at-action">
                <span className="at-icon">▸</span>
                <span className="at-text">
                  <b>{toolLabel(ev.tool)}</b>
                  {argHint(ev)}
                  {ev.result && <span className="at-result"> → {ev.result}</span>}
                </span>
              </li>
            ),
          )}
        </ol>
      )}
    </div>
  )
}
