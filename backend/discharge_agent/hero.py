"""The grounded, multi-day, multi-specialist inpatient "hero" case.

Why this exists: the provided Abridge dataset is one encounter per patient and its
inpatient med names don't resolve — so a true multi-specialist inpatient->discharge
journey does not exist natively (PROJECT.md, "Point 4"). We construct one as a proper
FHIR-shaped bundle, recorded the way a real EHR would record it: each `MedicationRequest`
carries an `authoredOn` date, a per-specialist `requester`, a `category` lane
(community / inpatient / discharge), a `status`, and a resolvable
`medicationCodeableConcept`. The medication inconsistencies are *in the data* — an order
placed on day 1 and never discontinued, a verbal stop never written back, an order that
predates allergy reconciliation — so the safety-catch engine can DETECT them, not just
be told about them.

Scenario — Margaret Alvarez, 74F. Mechanical fall -> right intertrochanteric hip
fracture, ORIF (Ortho). 5-day stay complicated by new-onset atrial fibrillation
(Cardiology), a UTI (Infectious Disease), and post-op acute kidney injury with
hyperkalemia (Hospitalist). Four teams prescribe in their own silos; at discharge one
clinician must reconcile everyone's orders — and twelve things need a decision.
"""
from __future__ import annotations

from typing import Any

from .normalize import normalize_meds
from .schemas import (
    ChartEvidence,
    EncounterDetail,
    Flag,
    PatientHeader,
    Prescriber,
    Reconciliation,
    ReconStats,
)

HERO_ID = "hero::margaret-alvarez-discharge"

ADMIT = "2026-07-13"
DISCHARGE_DATE = "2026-07-17"

# --- prescribers (the multi-specialist silos) --------------------------------
DR_LIN = Prescriber(name="Dr. Lin (PCP)", npi="1990000000")
DR_CHEN = Prescriber(name="Dr. Chen (Hospitalist)", npi="1990000001")
DR_OKAFOR = Prescriber(name="Dr. Okafor (Orthopedic Surgery)", npi="1990000002")
DR_PATEL = Prescriber(name="Dr. Patel (Cardiology)", npi="1990000003")
DR_REYES = Prescriber(name="Dr. Reyes (Infectious Disease)", npi="1990000004")

# --- verbatim transcript lines (single source of truth: reused in the flags) -
Q_STOP_LOVENOX = "Now that she's therapeutic on the apixaban, we can stop the Lovenox — she doesn't need both."
Q_HOLD_ASPIRIN = "Let's hold her baby aspirin while she's on the apixaban — no need to stack the bleeding risk without a stent indication."
Q_START_METOPROLOL = "Start her on metoprolol 25 twice a day for rate control, and her PCP can titrate up as needed."
Q_RENAL = "Her kidneys took a hit from the contrast and the surgery — her eGFR is down around 28, so hold anything renally cleared."
Q_POTASSIUM = "Her potassium came back at 5.8 this morning; let's just recheck it as an outpatient."
Q_LOSARTAN = "Her pressures are still running high, so let's add losartan 50 daily on top of what she's on."
Q_COUGH = "She's had this dry, hacking cough for a few weeks now — chest film's clean, so it's not the pneumonia."
Q_NO_DIABETES = "And she's never had diabetes, right? Nothing like that in her history."
Q_IBUPROFEN = "Keep the oxycodone for breakthrough pain, and add ibuprofen 600 three times a day for the swelling."
Q_AMP_SULBACTAM = "We started her on ampicillin-sulbactam empirically the night she came in febrile."
Q_CEPHALEXIN = "Urine culture's sensitive to cephalexin. Seven days total — she'll finish it on Saturday, then it stops."


# --- FHIR resource builders --------------------------------------------------
def _npi_ref(p: Prescriber) -> dict[str, Any]:
    return {"reference": f"Practitioner?identifier=http://hl7.org/fhir/sid/us-npi|{p.npi}", "display": p.name}


def _mr(
    rid: str, name: str, dose_val: float, dose_unit: str, route: str, freq: str,
    category: str, requester: Prescriber, authored: str, status: str = "active",
    end: str | None = None,
) -> dict[str, Any]:
    di: dict[str, Any] = {
        "text": f"{dose_val} {dose_unit} {route} {freq}",
        "route": {"text": route},
        "timing": {"code": {"text": freq}},
        "doseAndRate": [{"doseQuantity": {"value": dose_val, "unit": dose_unit}}],
    }
    mr: dict[str, Any] = {
        "resourceType": "MedicationRequest",
        "id": rid,
        "status": status,
        "intent": "order",
        "category": [{"coding": [{
            "system": "http://terminology.hl7.org/CodeSystem/medicationrequest-category",
            "code": category, "display": category.capitalize()}], "text": category.capitalize()}],
        "medicationCodeableConcept": {"text": name},
        "authoredOn": f"{authored}T09:00:00-07:00",
        "requester": _npi_ref(requester),
        "dosageInstruction": [di],
    }
    if end:
        mr["dispenseRequest"] = {"validityPeriod": {"end": end}}
    return mr


def _condition(cid: str, label: str, onset: str, status: str = "active") -> dict[str, Any]:
    return {
        "resourceType": "Condition", "id": cid,
        "clinicalStatus": {"coding": [{"code": status}]},
        "code": {"text": label}, "onsetDateTime": onset,
    }


def _observation(oid: str, label: str, value: float, unit: str, when: str, interp: str) -> dict[str, Any]:
    return {
        "resourceType": "Observation", "id": oid, "status": "final",
        "code": {"text": label},
        "valueQuantity": {"value": value, "unit": unit},
        "interpretation": [{"text": interp}],
        "effectiveDateTime": f"{when}T07:00:00-07:00",
    }


def _allergy(aid: str, label: str, reaction: str) -> dict[str, Any]:
    return {
        "resourceType": "AllergyIntolerance", "id": aid,
        "clinicalStatus": {"coding": [{"code": "active"}]},
        "code": {"text": label},
        "reaction": [{"manifestation": [{"text": reaction}]}],
    }


def _medication_requests() -> list[dict[str, Any]]:
    return [
        # -- home / prior-to-admission (community lane) --
        _mr("mr-lisinopril", "Lisinopril 20 mg Oral Tablet", 20, "mg", "PO", "daily", "community", DR_LIN, "2025-11-01"),
        _mr("mr-metformin", "Metformin 1000 mg Oral Tablet", 1000, "mg", "PO", "twice daily", "community", DR_LIN, "2025-11-01"),
        _mr("mr-atorvastatin", "Atorvastatin 40 mg Oral Tablet", 40, "mg", "PO", "daily", "community", DR_LIN, "2025-11-01"),
        _mr("mr-aspirin", "Aspirin 81 mg Oral Tablet", 81, "mg", "PO", "daily", "community", DR_LIN, "2025-11-01"),
        _mr("mr-levothyroxine", "Levothyroxine 75 mcg Oral Tablet", 75, "mcg", "PO", "daily", "community", DR_LIN, "2025-11-01"),
        # -- day 0 (admission) --
        _mr("mr-ampsulbactam", "Ampicillin-sulbactam 3 g IV", 3, "g", "IV", "every 6 hours", "inpatient", DR_REYES, "2026-07-13", status="stopped"),
        _mr("mr-enoxaparin", "Enoxaparin 40 mg/0.4 mL SC Injection", 40, "mg", "SC", "daily", "discharge", DR_OKAFOR, "2026-07-13"),
        _mr("mr-oxycodone", "Oxycodone 5 mg Oral Tablet", 5, "mg", "PO", "every 4 hours PRN pain", "discharge", DR_OKAFOR, "2026-07-13"),
        # -- day 1 (post-op, cardiology) --
        _mr("mr-apixaban", "Apixaban 5 mg Oral Tablet", 5, "mg", "PO", "twice daily", "discharge", DR_PATEL, "2026-07-14"),
        # -- day 2 (hospitalist) --
        _mr("mr-losartan", "Losartan 50 mg Oral Tablet", 50, "mg", "PO", "daily", "discharge", DR_CHEN, "2026-07-15"),
        _mr("mr-ibuprofen", "Ibuprofen 600 mg Oral Tablet", 600, "mg", "PO", "three times daily PRN", "discharge", DR_OKAFOR, "2026-07-15"),
        # -- day 3 (ID) — no end date on the order = orphaned course --
        _mr("mr-cephalexin", "Cephalexin 500 mg Oral Capsule", 500, "mg", "PO", "every 6 hours", "discharge", DR_REYES, "2026-07-16"),
    ]


def hero_record() -> dict[str, Any]:
    """The full Abridge-schema record for the stay (what a live FHIR token would yield)."""
    return {
        "id": HERO_ID,
        "metadata": {
            "patient_id": "hero-margaret-alvarez",
            "encounter_id": "hero-enc-1",
            "date": f"{DISCHARGE_DATE}T11:00:00-07:00",
            "status": "finished",
            "visit_type": "Inpatient discharge (multi-specialist)",
            "visit_title": "Inpatient discharge — hip fracture ORIF with new AF and UTI",
            "teams": ["Hospitalist", "Orthopedic Surgery", "Cardiology", "Infectious Disease"],
            "is_hero": True,
        },
        "patient_context": {
            "patient": {
                "resourceType": "Patient",
                "name": [{"given": ["Margaret"], "family": "Alvarez"}],
                "gender": "female",
                "birthDate": "1951-11-03",
            },
            "longitudinal_summary": {
                "resource_counts": {"Condition": 10, "MedicationRequest": 12, "Observation": 2, "AllergyIntolerance": 1},
                "condition_labels": [
                    "Essential hypertension", "Type 2 diabetes mellitus", "Hypothyroidism",
                    "Hyperlipidemia", "Chronic kidney disease stage 3",
                ],
                "medication_labels": [],  # home meds are FHIR resources below, not labels
                "allergy_labels": ["Penicillin (rash)"],
            },
        },
        "encounter_fhir": {
            "encounter": {
                "resourceType": "Encounter", "id": "hero-enc-1", "status": "finished",
                "class": {"code": "IMP", "display": "inpatient encounter"},
                "period": {"start": f"{ADMIT}T22:10:00-07:00", "end": f"{DISCHARGE_DATE}T11:00:00-07:00"},
            },
            "related_resources": {
                "Condition": [
                    _condition("cond-htn", "Essential hypertension (disorder)", "2014-03-02"),
                    _condition("cond-t2dm", "Type 2 diabetes mellitus (disorder)", "2016-06-19"),
                    _condition("cond-hypothyroid", "Hypothyroidism (disorder)", "2012-01-10"),
                    _condition("cond-hld", "Hyperlipidemia (disorder)", "2013-08-21"),
                    _condition("cond-ckd", "Chronic kidney disease stage 3 (disorder)", "2021-05-04"),
                    _condition("cond-hipfx", "Fracture of intertrochanteric section of femur", "2026-07-13"),
                    _condition("cond-afib", "Atrial fibrillation (disorder)", "2026-07-14"),
                    _condition("cond-uti", "Urinary tract infection (disorder)", "2026-07-13"),
                    _condition("cond-aki", "Acute kidney injury (disorder)", "2026-07-15"),
                    _condition("cond-hyperk", "Hyperkalemia (disorder)", "2026-07-16"),
                ],
                "AllergyIntolerance": [_allergy("allergy-pcn", "Penicillin", "Rash")],
                "Observation": [
                    _observation("obs-egfr", "eGFR (CKD-EPI)", 28, "mL/min/1.73m2", "2026-07-15", "Low (AKI)"),
                    _observation("obs-k", "Potassium", 5.8, "mmol/L", "2026-07-16", "High"),
                ],
                "MedicationRequest": _medication_requests(),
            },
        },
        "transcript": HERO_TRANSCRIPT,
        "note": HERO_NOTE,
        "after_visit_summary": HERO_AVS,
        "after_visit_summary_provenance": {"source": "hand-authored hero"},
    }


def hero_header() -> PatientHeader:
    return PatientHeader(
        name="Margaret Alvarez", mrn="MRN 4471902", gender="female", age=74,
        dob="1951-11-03", code_status="Full Code", location="5 West · Bed 512-A",
        allergies=["Penicillin (rash)"], attending="Dr. Chen (Hospitalist)",
    )


def hero_meds():
    """Derived FROM the bundle via the normalizer — grounded, not hand-listed."""
    return normalize_meds(hero_record())


def hero_flags() -> list[Flag]:
    """Twelve grounded catches — each cites a real resource id in the bundle."""
    return [
        Flag(id="f1", type="cross_prescriber_conflict", severity="high", med_name="Enoxaparin",
             explanation=("Double anticoagulation on the go-home list. Cardiology started apixaban "
                          "for new atrial fibrillation (07-14); Orthopedics' DVT-prophylaxis "
                          "enoxaparin (ordered 07-13) is still active and was carried to discharge. "
                          "Cardiology verbally stopped it once apixaban was therapeutic — the order "
                          "was never discontinued."),
             transcript_evidence=Q_STOP_LOVENOX, transcript_speaker="DR. PATEL (Cardiology), Day 1",
             chart_evidence=ChartEvidence(resource_type="MedicationRequest", resource_id="mr-enoxaparin",
                                          display="Enoxaparin 40 mg SC daily — status: active, category: discharge"),
             prescriber=DR_OKAFOR,
             suggested_fix="Discontinue enoxaparin; continue apixaban 5 mg PO BID as the sole anticoagulant.",
             recommended_resolution="Stop enoxaparin (resolves duplicate anticoagulation)."),

        Flag(id="f2", type="renal_dose_conflict", severity="high", med_name="Metformin",
             explanation=("Metformin is on the discharge list at the home dose, but this admission's "
                          "labs show acute kidney injury (eGFR 28). Metformin is contraindicated below "
                          "eGFR 30 due to lactic-acidosis risk."),
             transcript_evidence=Q_RENAL, transcript_speaker="DR. CHEN (Hospitalist), Day 2",
             chart_evidence=ChartEvidence(resource_type="Observation", resource_id="obs-egfr",
                                          display="eGFR 28 mL/min/1.73m² (2026-07-15) — Low (AKI)"),
             prescriber=DR_CHEN,
             suggested_fix="Hold metformin; document a plan to recheck renal function before restarting.",
             recommended_resolution="Hold metformin (eGFR 28 < 30 contraindication)."),

        Flag(id="f3", type="drug_allergy_conflict", severity="high", med_name="Ampicillin-sulbactam",
             explanation=("Ampicillin-sulbactam — a penicillin-class antibiotic — was ordered "
                          "empirically at admission for a patient with a charted penicillin allergy. "
                          "The order predates allergy reconciliation from the outside chart."),
             transcript_evidence=Q_AMP_SULBACTAM, transcript_speaker="DR. REYES (Infectious Disease), Day 3",
             chart_evidence=ChartEvidence(resource_type="AllergyIntolerance", resource_id="allergy-pcn",
                                          display="Penicillin — reaction: Rash (active)"),
             prescriber=DR_REYES,
             suggested_fix="Confirm no discharge penicillin-class order; document the exposure and reaction watch.",
             recommended_resolution="Verify allergy; keep non-beta-lactam coverage on discharge."),

        Flag(id="f4", type="drug_drug_interaction", severity="high", med_name="Ibuprofen",
             explanation=("Ibuprofen was added for post-op swelling while the patient is on apixaban. "
                          "An NSAID plus an oral anticoagulant markedly raises GI-bleeding risk — and "
                          "the NSAID is also nephrotoxic in the setting of the current AKI."),
             transcript_evidence=Q_IBUPROFEN, transcript_speaker="DR. OKAFOR (Orthopedic Surgery), Day 2",
             chart_evidence=ChartEvidence(resource_type="MedicationRequest", resource_id="mr-ibuprofen",
                                          display="Ibuprofen 600 mg TID — interacts with apixaban (mr-apixaban)"),
             prescriber=DR_OKAFOR,
             suggested_fix="Discontinue ibuprofen; use acetaminophen ± the existing oxycodone for pain.",
             recommended_resolution="Stop ibuprofen (bleeding + renal risk on apixaban/AKI)."),

        Flag(id="f5", type="discontinued_but_active", severity="high", med_name="Aspirin",
             explanation=("Home aspirin remains active alongside newly-started apixaban. Cardiology "
                          "directed holding it to avoid stacking bleeding risk, but it was never removed."),
             transcript_evidence=Q_HOLD_ASPIRIN, transcript_speaker="DR. PATEL (Cardiology), Day 1",
             chart_evidence=ChartEvidence(resource_type="MedicationRequest", resource_id="mr-aspirin",
                                          display="Aspirin 81 mg daily — status: active"),
             prescriber=DR_PATEL,
             suggested_fix="Discontinue aspirin 81 mg for the duration of apixaban therapy.",
             recommended_resolution="Stop aspirin (bleeding-risk stacking with apixaban)."),

        Flag(id="f6", type="dropped_result", severity="high", med_name=None,
             explanation=("A critical potassium of 5.8 mmol/L was noted on 07-16 and deferred to "
                          "'recheck as an outpatient,' but no follow-up lab or potassium-management plan "
                          "was ordered — and the new losartan will push it higher."),
             transcript_evidence=Q_POTASSIUM, transcript_speaker="DR. CHEN (Hospitalist), Day 3",
             chart_evidence=ChartEvidence(resource_type="Observation", resource_id="obs-k",
                                          display="Potassium 5.8 mmol/L (2026-07-16) — High, no follow-up ordered"),
             prescriber=DR_CHEN,
             suggested_fix="Order a BMP within 48–72h of discharge and give a hyperkalemia-precautions plan.",
             recommended_resolution="Add a post-discharge potassium recheck order."),

        Flag(id="f7", type="duplicate_therapy", severity="moderate", med_name="Losartan",
             explanation=("Losartan (an ARB) was added for blood pressure while the patient already "
                          "takes lisinopril (an ACE inhibitor). Combined ACEi + ARB is duplicate RAAS "
                          "blockade — no added benefit and it compounds the hyperkalemia and AKI."),
             transcript_evidence=Q_LOSARTAN, transcript_speaker="DR. CHEN (Hospitalist), Day 2",
             chart_evidence=ChartEvidence(resource_type="MedicationRequest", resource_id="mr-losartan",
                                          display="Losartan 50 mg — duplicates home lisinopril (mr-lisinopril)"),
             prescriber=DR_CHEN,
             suggested_fix="Choose one RAAS agent. Given AKI + K 5.8, hold both and reassess pressures.",
             recommended_resolution="Do not add losartan on top of lisinopril."),

        Flag(id="f8", type="dropped_home_med", severity="moderate", med_name="Levothyroxine",
             explanation=("Home levothyroxine (hypothyroidism) was never addressed by any team and is "
                          "absent from the discharge orders. Silently dropping thyroid replacement risks "
                          "symptomatic hypothyroidism after discharge."),
             transcript_evidence=None, transcript_speaker=None,
             chart_evidence=ChartEvidence(resource_type="MedicationRequest", resource_id="mr-levothyroxine",
                                          display="Levothyroxine 75 mcg daily — home med, not continued at discharge"),
             prescriber=DR_LIN,
             suggested_fix="Continue levothyroxine 75 mcg PO daily on the discharge list.",
             recommended_resolution="Continue levothyroxine (no reason to stop documented)."),

        Flag(id="f9", type="history_mismatch", severity="moderate", med_name=None,
             explanation=("During rounds the team stated the patient has no history of diabetes, but "
                          "Type 2 diabetes mellitus is an active charted problem and she is on metformin. "
                          "The verbal history contradicts the record."),
             transcript_evidence=Q_NO_DIABETES, transcript_speaker="DR. CHEN (Hospitalist), Day 2",
             chart_evidence=ChartEvidence(resource_type="Condition", resource_id="cond-t2dm",
                                          display="Type 2 diabetes mellitus — active problem"),
             prescriber=DR_CHEN,
             suggested_fix="Reconcile the history: confirm T2DM with the patient and correct the record.",
             recommended_resolution="Keep charted T2DM; verify with the patient."),

        Flag(id="f10", type="adverse_drug_event", severity="moderate", med_name="Lisinopril",
             explanation=("A weeks-long dry cough with a clean chest film is a classic ACE-inhibitor "
                          "cough. Lisinopril is the likely cause; an ARB is the usual substitute — but "
                          "note losartan is already flagged for duplication, so switch rather than add."),
             transcript_evidence=Q_COUGH, transcript_speaker="DR. CHEN (Hospitalist), Day 2",
             chart_evidence=ChartEvidence(resource_type="MedicationRequest", resource_id="mr-lisinopril",
                                          display="Lisinopril 20 mg daily — active; associated ADR: dry cough"),
             prescriber=DR_LIN,
             suggested_fix="Consider stopping lisinopril and reassessing the cough; avoid adding a second RAAS agent.",
             recommended_resolution="Evaluate lisinopril as the cough cause (clinician decision)."),

        Flag(id="f11", type="orphaned_course", severity="moderate", med_name="Cephalexin",
             explanation=("The UTI antibiotic has no stop date on the discharge order. Infectious "
                          "Disease intended a fixed 7-day course ending 2026-07-19; as written it would "
                          "continue indefinitely."),
             transcript_evidence=Q_CEPHALEXIN, transcript_speaker="DR. REYES (Infectious Disease), Day 3",
             chart_evidence=ChartEvidence(resource_type="MedicationRequest", resource_id="mr-cephalexin",
                                          display="Cephalexin 500 mg q6h — no end date on order"),
             prescriber=DR_REYES,
             suggested_fix="Add a stop date of 2026-07-19 (completes the 7-day course).",
             recommended_resolution="Set cephalexin end date to 2026-07-19."),

        Flag(id="f12", type="mentioned_not_recorded", severity="moderate", med_name="Metoprolol",
             explanation=("Cardiology dictated starting metoprolol 25 mg BID for rate control, but no "
                          "structured discharge order was ever captured. The intent lives only in the "
                          "conversation — the patient would leave without a rate-control agent."),
             transcript_evidence=Q_START_METOPROLOL, transcript_speaker="DR. PATEL (Cardiology), Day 1",
             chart_evidence=ChartEvidence(resource_type="MedicationRequest", resource_id=None,
                                          display="No matching discharge order found"),
             prescriber=DR_PATEL,
             suggested_fix="Add metoprolol tartrate 25 mg PO BID to the discharge orders, per Cardiology.",
             recommended_resolution="Add metoprolol 25 mg PO BID (captures the spoken order)."),
    ]


# --- multi-day transcript (verbatim lines match the flags above) -------------
HERO_TRANSCRIPT = f"""\
════════ DAY 0 — {ADMIT} · Admission (ED → Ortho, ID) ════════
NURSE: 74-year-old, mechanical fall at home, right hip. She came in febrile too.
DR. OKAFOR (Orthopedic Surgery): Intertrochanteric fracture, she'll need ORIF today.
Start DVT prophylaxis — enoxaparin 40 subcutaneous daily — and oxycodone for pain.
DR. REYES (Infectious Disease): {Q_AMP_SULBACTAM} We'll narrow once cultures are back.

════════ DAY 1 — 2026-07-14 · Post-op · Cardiology consult ════════
DR. PATEL (Cardiology): Her heart's been in and out of a-fib since the surgery. I've
started apixaban five milligrams twice a day. {Q_STOP_LOVENOX}
DR. PATEL: {Q_HOLD_ASPIRIN}
DR. PATEL: {Q_START_METOPROLOL}

════════ DAY 2 — 2026-07-15 · Hospitalist rounds ════════
DR. CHEN (Hospitalist): {Q_RENAL}
DR. CHEN: {Q_LOSARTAN}
DR. CHEN: {Q_COUGH}
DR. CHEN: {Q_NO_DIABETES}
DR. OKAFOR (Orthopedic Surgery): {Q_IBUPROFEN}

════════ DAY 3 — 2026-07-16 · Hospitalist + ID ════════
DR. CHEN (Hospitalist): {Q_POTASSIUM}
DR. REYES (Infectious Disease): {Q_CEPHALEXIN}

════════ DAY 4 — {DISCHARGE_DATE} · Discharge planning ════════
DR. OKAFOR (Orthopedic Surgery): Hip's healing well, weight-bearing as tolerated.
DR. CHEN (Hospitalist): Let's get her list reconciled and the after-visit summary out.
"""

HERO_NOTE = f"""\
# Discharge Summary — Margaret Alvarez, 74F   ({ADMIT} → {DISCHARGE_DATE})

## Problem List
Essential hypertension · Type 2 diabetes mellitus · Hypothyroidism · Hyperlipidemia ·
CKD stage 3 · Right intertrochanteric hip fracture (ORIF) · New-onset atrial
fibrillation · UTI · Post-op acute kidney injury (eGFR nadir 28) · Hyperkalemia (K 5.8).

## Hospital Course
Admitted after a mechanical fall. ORIF by Orthopedics (Dr. Okafor). New AF managed by
Cardiology (Dr. Patel); UTI by Infectious Disease (Dr. Reyes); AKI and hyperkalemia by
Hospitalist (Dr. Chen). Four teams contributed medication orders across the stay.

## Discharge Disposition
Home with home health. Medication reconciliation pending — see the reconciliation
activity. Orders span four prescribers and multiple days; several require a decision.
"""

HERO_AVS = """\
## Your medicines — what changed and why
Your care team is finalizing your medication list. We are reconciling orders from your
surgery, heart, kidney, and infection teams before you go home so that nothing is
doubled-up, missed, or left without a stop date.
"""


# --- association + reconciliation -------------------------------------------
def _flag_matches_med(flag: Flag, med) -> bool:
    if flag.chart_evidence and flag.chart_evidence.resource_id and flag.chart_evidence.resource_id == med.id:
        return True
    if flag.med_name and med.name.lower().startswith(flag.med_name.lower()):
        return True
    return False


def hero_detail() -> EncounterDetail:
    rec = hero_record()
    return EncounterDetail(
        id=HERO_ID, header=hero_header(), metadata=rec["metadata"],
        transcript=rec["transcript"], note=rec["note"],
        after_visit_summary=rec["after_visit_summary"], meds=hero_meds(),
    )


def hero_reconciliation() -> Reconciliation:
    meds = hero_meds()
    flags = hero_flags()
    flagged_med_ids = {m.id for m in meds if any(_flag_matches_med(f, m) for f in flags)}
    high = sum(1 for f in flags if f.severity == "high")
    return Reconciliation(
        encounter_id=HERO_ID, draft_meds=meds, flags=flags,
        stats=ReconStats(
            total_meds=len(meds),
            agree_count=len(meds) - len(flagged_med_ids),
            flag_count=len(flags),
            high_severity_count=high,
        ),
    )
