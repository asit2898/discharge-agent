import { useEffect, useRef } from 'react'

// Ambient transcript rendered as a readable, screenplay-style conversation: day
// dividers, speaker names in a color-coded left column, and turns that wrap naturally —
// instead of a raw pre-formatted text dump.

type Block =
  | { kind: 'day'; title: string }
  | { kind: 'turn'; speaker: string; text: string }

function parse(text: string): Block[] {
  const blocks: Block[] = []
  let cur: Extract<Block, { kind: 'turn' }> | null = null

  for (const raw of text.split('\n')) {
    const line = raw.trim()
    if (!line) {
      cur = null
      continue
    }
    // Day separator, e.g. "═══ DAY 0 — 2026-07-13 · Admission … ═══" (any separator char)
    if (/(^|[\s=═━-])DAY\s+\d/.test(line)) {
      const title = line.replace(/[=═━]+/g, '').replace(/^[\s—-]+|[\s—-]+$/g, '').trim()
      blocks.push({ kind: 'day', title })
      cur = null
      continue
    }
    // Speaker turn: "SPEAKER: text" (speaker is a short leading label ending in a colon)
    const m = line.match(/^([A-Z][A-Za-z.,\s()/-]{0,42}?):\s*(.*)$/)
    if (m) {
      cur = { kind: 'turn', speaker: m[1].trim(), text: m[2] }
      blocks.push(cur)
    } else if (cur) {
      cur.text += ' ' + line
    } else {
      cur = { kind: 'turn', speaker: '', text: line }
      blocks.push(cur)
    }
  }
  return blocks
}

function roleOf(speaker: string): string {
  const s = speaker.toUpperCase()
  if (s.startsWith('DR')) return 'dr'
  if (s.startsWith('NURSE') || s.startsWith('RN')) return 'nurse'
  if (s.startsWith('PT') || s.includes('PATIENT')) return 'patient'
  if (s.includes('DAUGHTER') || s.includes('SON') || s.includes('FAMILY') || s.includes('WIFE') || s.includes('HUSBAND'))
    return 'family'
  return 'other'
}

function Speaker({ speaker }: { speaker: string }) {
  const i = speaker.indexOf('(')
  const name = i >= 0 ? speaker.slice(0, i).trim() : speaker
  const spec = i >= 0 ? speaker.slice(i).trim() : ''
  return (
    <div className={`tx-speaker role-${roleOf(speaker)}`}>
      <span className="tx-name">{name || '—'}</span>
      {spec && <span className="tx-spec">{spec}</span>}
    </div>
  )
}

const norm = (s: string) => s.replace(/\s+/g, ' ').trim().toLowerCase()

export function TranscriptView({ text, highlight }: { text: string; highlight?: string }) {
  const blocks = parse(text || '')
  const needle = highlight ? norm(highlight) : ''
  const hitRef = useRef<HTMLDivElement | null>(null)
  let hitMarked = false

  // scroll the highlighted turn into view when the highlight target changes
  useEffect(() => {
    if (highlight && hitRef.current) {
      hitRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [highlight, text])

  return (
    <div className="work">
      <div className="work-head">
        <h2>Ambient Transcript</h2>
        <span className="sub">Abridge · captured across the stay</span>
      </div>
      {blocks.length === 0 ? (
        <div className="center-msg">No transcript on file for this encounter.</div>
      ) : (
        <div className="tx">
          {blocks.map((b, i) => {
            if (b.kind === 'day') {
              return (
                <div className="tx-day" key={i}>
                  <span className="tx-day-label">{b.title}</span>
                </div>
              )
            }
            const isHit = !hitMarked && needle !== '' && norm(b.text).includes(needle)
            if (isHit) hitMarked = true
            return (
              <div
                className={`tx-turn ${isHit ? 'hit' : ''}`}
                key={i}
                ref={isHit ? hitRef : undefined}
              >
                <Speaker speaker={b.speaker} />
                <div className="tx-text">{b.text}</div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
