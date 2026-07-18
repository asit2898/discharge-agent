// TS mirror of backend/discharge_agent/schemas.py — the API contract.

export type MedSource = 'home' | 'inpatient' | 'discharge' | 'transcript'
export type MedCategory = 'home' | 'inpatient' | 'outpatient' | 'community' | 'unknown'

export interface Prescriber {
  name: string | null
  npi: string | null
}

export interface Med {
  id: string
  name: string
  dose: string | null
  route: string | null
  frequency: string | null
  status: string | null
  intent: string | null
  category: MedCategory
  source: MedSource
  prescriber: Prescriber
  authored_on: string | null
}

export type FlagType =
  | 'drug_allergy_conflict'
  | 'renal_dose_conflict'
  | 'drug_drug_interaction'
  | 'duplicate_therapy'
  | 'dropped_home_med'
  | 'history_mismatch'
  | 'drug_condition_conflict'
  | 'dropped_result'
  | 'adverse_drug_event'
  | 'discontinued_but_active'
  | 'mentioned_not_recorded'
  | 'cross_prescriber_conflict'
  | 'orphaned_course'

export type Severity = 'high' | 'moderate' | 'low'
export type ReviewStatus = 'pending' | 'accepted' | 'edited' | 'rejected'

export interface ChartEvidence {
  resource_type: string
  resource_id: string | null
  display: string | null
}

export interface Flag {
  id: string
  type: FlagType
  severity: Severity
  med_name: string | null
  explanation: string
  transcript_evidence: string | null
  transcript_speaker: string | null
  chart_evidence: ChartEvidence | null
  prescriber: Prescriber
  suggested_fix: string
  recommended_resolution: string
  status: ReviewStatus
}

export interface ReconStats {
  total_meds: number
  agree_count: number
  flag_count: number
  high_severity_count: number
}

export interface Reconciliation {
  encounter_id: string
  draft_meds: Med[]
  flags: Flag[]
  stats: ReconStats
}

export interface EncounterSummary {
  id: string
  patient_id: string
  date: string | null
  visit_title: string | null
  visit_type: string | null
  gender: string | null
  age: number | null
  is_inpatient: boolean
  med_count: number
  flag_count: number
  is_hero: boolean
}

export interface PatientHeader {
  name: string
  mrn: string
  gender: string | null
  age: number | null
  dob: string | null
  code_status: string
  location: string | null
  allergies: string[]
  attending: string | null
}

export interface EncounterDetail {
  id: string
  header: PatientHeader
  metadata: Record<string, unknown>
  transcript: string
  note: string
  after_visit_summary: string
  meds: Med[]
}
