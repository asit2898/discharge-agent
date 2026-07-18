"""Pydantic models = the API contract shared with the React frontend.

Two families:
  * Normalized clinical objects (Med) — what the Chart Compiler produces.
  * Reconciliation output (Flag, Reconciliation) — what the copilot panel renders.

`Flag` mirrors the labeled eval taxonomy (`data/*.labels.jsonl`) so the deterministic
stub and the future neuro-symbolic engine are interchangeable behind one shape.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel

# ---- normalized medication ---------------------------------------------------

MedSource = Literal["home", "inpatient", "discharge", "transcript"]
MedCategory = Literal["home", "inpatient", "outpatient", "community", "unknown"]


class Prescriber(BaseModel):
    name: Optional[str] = None
    npi: Optional[str] = None


class Med(BaseModel):
    """One medication normalized to a common shape, source-tagged."""
    id: str
    name: str
    dose: Optional[str] = None
    route: Optional[str] = None
    frequency: Optional[str] = None
    status: Optional[str] = None          # active | completed | stopped | ...
    intent: Optional[str] = None          # order | plan | ...
    category: MedCategory = "unknown"
    source: MedSource = "inpatient"
    prescriber: Prescriber = Prescriber()
    authored_on: Optional[str] = None


# ---- reconciliation flags (safety-catch output) ------------------------------

FlagType = Literal[
    "drug_allergy_conflict",
    "renal_dose_conflict",
    "drug_drug_interaction",
    "duplicate_therapy",
    "dropped_home_med",
    "history_mismatch",
    "drug_condition_conflict",
    "dropped_result",
    "adverse_drug_event",
    # med-rec disposition flags (surfaced in the Navigator med-rec step)
    "discontinued_but_active",
    "mentioned_not_recorded",
    "cross_prescriber_conflict",
    "orphaned_course",
]
Severity = Literal["high", "moderate", "low"]
ReviewStatus = Literal["pending", "accepted", "edited", "rejected"]


class ChartEvidence(BaseModel):
    resource_type: str
    resource_id: Optional[str] = None
    display: Optional[str] = None


class Flag(BaseModel):
    """A grounded safety catch: both-sided evidence + a drafted fix + disposition.

    The clinician decides. `recommended_resolution` defaults to the signed record
    (authority order: signed order/note > transcript), per the project's safety rule.
    """
    id: str
    type: FlagType
    severity: Severity
    med_name: Optional[str] = None
    explanation: str
    transcript_evidence: Optional[str] = None
    transcript_speaker: Optional[str] = None
    chart_evidence: Optional[ChartEvidence] = None
    prescriber: Prescriber = Prescriber()
    suggested_fix: str
    recommended_resolution: str          # what we default the disposition to
    status: ReviewStatus = "pending"
    grounding: Optional[Literal["real", "injected"]] = None  # real Synthea resource vs planted


class ReconStats(BaseModel):
    total_meds: int
    agree_count: int
    flag_count: int
    high_severity_count: int


class Reconciliation(BaseModel):
    """Everything the copilot panel needs for one encounter."""
    encounter_id: str
    draft_meds: list[Med]                 # the pre-populated reconciled list
    flags: list[Flag]                     # the ranked "needs a decision" queue
    stats: ReconStats


# ---- encounter list / detail -------------------------------------------------

class EncounterSummary(BaseModel):
    id: str
    patient_id: str
    date: Optional[str] = None
    visit_title: Optional[str] = None
    visit_type: Optional[str] = None
    gender: Optional[str] = None
    age: Optional[int] = None
    is_inpatient: bool = False
    med_count: int = 0
    flag_count: int = 0
    is_hero: bool = False


class PatientHeader(BaseModel):
    """Epic-style patient banner data."""
    name: str
    mrn: str
    gender: Optional[str] = None
    age: Optional[int] = None
    dob: Optional[str] = None
    code_status: str = "Full Code"
    location: Optional[str] = None
    allergies: list[str] = []
    attending: Optional[str] = None


class Problem(BaseModel):
    """One problem-list entry (Epic Problem List row)."""
    label: str
    code: Optional[str] = None
    system: Optional[str] = None       # ICD-10 / SNOMED
    onset: Optional[str] = None
    acute: bool = False                # this-admission vs chronic


class LabResult(BaseModel):
    """One resulted lab component (a cell in Epic's Results Review flowsheet)."""
    name: str
    loinc: Optional[str] = None
    value: str
    unit: Optional[str] = None
    when: Optional[str] = None          # YYYY-MM-DD
    interpretation: Optional[str] = None
    ref_low: Optional[float] = None
    ref_high: Optional[float] = None
    abnormal: bool = False


class EncounterDetail(BaseModel):
    id: str
    header: PatientHeader
    metadata: dict
    transcript: str
    note: str
    after_visit_summary: str
    meds: list[Med]
    problems: list[Problem] = []
    labs: list[LabResult] = []
