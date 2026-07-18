import type { EncounterDetail, EncounterSummary, Reconciliation } from './types'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} — ${path}`)
  return res.json() as Promise<T>
}

export const api = {
  listEncounters: () => get<EncounterSummary[]>('/api/encounters'),
  getEncounter: (id: string) =>
    get<EncounterDetail>(`/api/encounters/${encodeURIComponent(id)}`),
  reconcile: (id: string) =>
    get<Reconciliation>(`/api/encounters/${encodeURIComponent(id)}/reconcile`),
}
