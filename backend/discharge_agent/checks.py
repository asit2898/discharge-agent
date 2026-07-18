"""Stages 3 + 4 — Catch Engine + Grounder (deterministic, KB-backed).

Each check routes over the PatientState (and, where relevant, the extracted
assertions) and emits grounded candidate `Flag`s — both-sided evidence (transcript
span where available + the exact FHIR resource id) + a drafted fix. Nothing here reads
the answer key; every flag is derived from the chart and the KB.

Candidates may over-generate (e.g. dropped-med flags every uncontinued home med); the
LLM self-verifier (stage 5) prunes the false positives.
"""
from __future__ import annotations

from typing import Optional

from . import kb
from .assertions import ClinicalAssertion
from .patient_state import PatientState
from .schemas import ChartEvidence, Flag, Prescriber, Severity


def _chart_evidence(med) -> ChartEvidence:
    return ChartEvidence(resource_type="MedicationRequest", resource_id=med.id, display=med.name)


def _prov(med) -> Optional[str]:
    p = getattr(med, "_prov", None)
    return "injected" if p == "injected" else "real"


def _tokens(text: str) -> set[str]:
    return {t for t in "".join(c if c.isalnum() else " " for c in text.lower()).split() if len(t) > 3}


# --- 1. drug ↔ allergy --------------------------------------------------------

def check_drug_allergy(state: PatientState, _assertions) -> list[Flag]:
    flags: list[Flag] = []
    for med in state.meds:  # scan ALL encounter meds — a penicillin given to a PCN-allergic patient matters even if now stopped
        key = kb.resolve_drug(med.name)
        if not key:
            continue
        acls = kb.DRUGS[key].get("allergy_class")
        if not acls:
            continue
        for allergy in state.allergies:
            if acls in allergy.classes:
                flags.append(Flag(
                    id=f"allergy-{med.id}",
                    type="drug_allergy_conflict",
                    severity="high",
                    med_name=med.name,
                    explanation=(f"{med.name} is a {kb.DRUGS[key]['cls']} ({acls} class), which cross-reacts "
                                 f"with the charted {allergy.label} allergy."),
                    transcript_evidence=None,
                    transcript_speaker=None,
                    chart_evidence=_chart_evidence(med),
                    prescriber=med.prescriber,
                    suggested_fix=f"Avoid {med.name}; select a non-{acls} alternative.",
                    recommended_resolution=f"Do not give {med.name} ({allergy.label} allergy).",
                    grounding=_prov(med),
                ))
    return flags


# --- 2. renal dosing ----------------------------------------------------------

def check_renal_dose(state: PatientState, _assertions) -> list[Flag]:
    egfr = state.labs.get("egfr")
    if egfr is None:
        return []
    flags: list[Flag] = []
    for med in state.active_meds():
        key = kb.resolve_drug(med.name)
        if not key:
            continue
        renal = kb.DRUGS[key].get("renal")
        thr = renal.get("threshold") if isinstance(renal, dict) else None
        if not thr or egfr.value >= thr:
            continue
        rule = renal.get("rule", "")
        severity: Severity = "high" if "contraindicated" in rule else "moderate"
        flags.append(Flag(
            id=f"renal-{med.id}",
            type="renal_dose_conflict",
            severity=severity,
            med_name=med.name,
            explanation=(f"{med.name} at eGFR {egfr.value:g} {egfr.unit or ''}: {rule} "
                         f"(threshold eGFR {thr})."),
            transcript_evidence=None,
            transcript_speaker=None,
            chart_evidence=_chart_evidence(med),
            prescriber=med.prescriber,
            suggested_fix=f"Hold or renally dose-adjust {med.name}; recheck renal function.",
            recommended_resolution=f"Adjust {med.name} for eGFR {egfr.value:g}.",
            grounding=_prov(med),
        ))
    return flags


# --- 3. drug ↔ drug interaction ----------------------------------------------

def check_drug_drug(state: PatientState, _assertions) -> list[Flag]:
    active = [(m, kb.resolve_drug(m.name)) for m in state.active_meds()]
    active = [(m, k) for m, k in active if k]
    flags: list[Flag] = []
    seen: set[frozenset] = set()
    for i, (ma, ka) in enumerate(active):
        for mb, kb_key in active[i + 1:]:
            if ka == kb_key:
                continue
            harm = kb.DRUGS[ka]["interacts"].get(kb_key) or kb.DRUGS[kb_key]["interacts"].get(ka)
            if not harm:
                continue
            pair = frozenset((ka, kb_key))
            if pair in seen:
                continue
            seen.add(pair)
            flags.append(Flag(
                id=f"ddi-{ka}-{kb_key}",
                type="drug_drug_interaction",
                severity="high",
                med_name=f"{ma.name} + {mb.name}",
                explanation=f"{ma.name} + {mb.name}: {harm}.",
                transcript_evidence=None,
                transcript_speaker=None,
                chart_evidence=_chart_evidence(ma),
                prescriber=ma.prescriber,
                suggested_fix=f"Reassess co-prescription of {ka} and {kb_key} ({harm}).",
                recommended_resolution=f"Avoid combining {ka} and {kb_key}.",
                grounding=_prov(ma),
            ))
    return flags


# --- 4. duplicate therapy -----------------------------------------------------

def check_duplicate(state: PatientState, _assertions) -> list[Flag]:
    by_key: dict[str, list] = {}
    for m in state.active_meds():
        k = kb.resolve_drug(m.name)
        if k:
            by_key.setdefault(k, []).append(m)
    flags: list[Flag] = []
    for key, meds in by_key.items():
        if len(meds) < 2:
            continue
        names = ", ".join(m.name for m in meds)
        flags.append(Flag(
            id=f"dup-{key}",
            type="duplicate_therapy",
            severity="moderate",
            med_name=meds[-1].name,
            explanation=f"Duplicate {key} orders on the discharge list: {names}.",
            transcript_evidence=None,
            transcript_speaker=None,
            chart_evidence=_chart_evidence(meds[-1]),
            prescriber=meds[-1].prescriber,
            suggested_fix=f"Consolidate to a single {key} order.",
            recommended_resolution=f"Keep one {key} order; remove the duplicate.",
            grounding=_prov(meds[-1]),
        ))
    return flags


# --- 5. dropped home med ------------------------------------------------------

def check_dropped_home_med(state: PatientState, _assertions) -> list[Flag]:
    discharge_keys = {kb.resolve_drug(m.name) for m in state.meds if m.source == "discharge"}
    discharge_names = " ".join(m.name.lower() for m in state.meds if m.source == "discharge")
    flags: list[Flag] = []
    for m in state.meds:
        if m.source != "home":
            continue
        key = kb.resolve_drug(m.name)
        carried = (key and key in discharge_keys) or (m.name.lower() in discharge_names)
        if carried:
            continue
        flags.append(Flag(
            id=f"dropped-{m.id}",
            type="dropped_home_med",
            severity="high",
            med_name=m.name,
            explanation=f"Home med {m.name} was not carried onto the discharge orders.",
            transcript_evidence=None,
            transcript_speaker=None,
            chart_evidence=_chart_evidence(m),
            prescriber=m.prescriber,
            suggested_fix=f"Confirm whether {m.name} should continue on discharge.",
            recommended_resolution=f"Continue {m.name} unless intentionally stopped.",
            grounding=_prov(m),
        ))
    return flags


# --- 6. teratogen in pregnancy ------------------------------------------------

def check_teratogen(state: PatientState, _assertions) -> list[Flag]:
    if not state.pregnant:
        return []
    flags: list[Flag] = []
    for m in state.active_meds():
        key = kb.resolve_drug(m.name)
        if key and kb.DRUGS[key].get("teratogen"):
            flags.append(Flag(
                id=f"terato-{m.id}",
                type="drug_condition_conflict",
                severity="high",
                med_name=m.name,
                explanation=f"{m.name} is a known teratogen and the patient is pregnant.",
                transcript_evidence=None,
                transcript_speaker=None,
                chart_evidence=_chart_evidence(m),
                prescriber=m.prescriber,
                suggested_fix=f"Discontinue {m.name}; choose a pregnancy-safe alternative.",
                recommended_resolution=f"Stop {m.name} in pregnancy.",
                grounding=_prov(m),
            ))
    return flags


# --- 7. cross-prescriber anticoagulant conflict -------------------------------

def check_cross_prescriber(state: PatientState, _assertions) -> list[Flag]:
    anticoags = []
    for m in state.active_meds():
        key = kb.resolve_drug(m.name)
        if key and "anticoagulant" in kb.DRUGS[key]["cls"]:
            anticoags.append((m, key))
    prescribers = {(m.prescriber.name or "?") for m, _ in anticoags}
    if len(anticoags) < 2 or len(prescribers) < 2:
        return []
    names = ", ".join(f"{m.name} ({m.prescriber.name})" for m, _ in anticoags)
    lead = anticoags[0][0]
    return [Flag(
        id="xpresc-anticoag",
        type="cross_prescriber_conflict",
        severity="high",
        med_name=lead.name,
        explanation=f"Overlapping anticoagulants ordered by different services: {names}.",
        transcript_evidence=None,
        transcript_speaker=None,
        chart_evidence=_chart_evidence(lead),
        prescriber=lead.prescriber,
        suggested_fix="Reconcile the anticoagulation plan across services; avoid dual anticoagulation.",
        recommended_resolution="One anticoagulant; align the ordering services.",
        grounding=_prov(lead),
    )]


# --- 8. adverse drug event (assertion-driven) ---------------------------------

def check_adverse_event(state: PatientState, assertions: list[ClinicalAssertion]) -> list[Flag]:
    flags: list[Flag] = []
    symptoms = [a for a in assertions if a.kind == "report_symptom" and (a.symptom or a.verbatim_span)]
    for a in symptoms:
        stoks = _tokens((a.symptom or "") + " " + a.verbatim_span)
        for m in state.active_meds():
            key = kb.resolve_drug(m.name)
            if not key:
                continue
            for adr in kb.DRUGS[key].get("adr", []):
                if _tokens(adr) & stoks:
                    flags.append(Flag(
                        id=f"ade-{key}-{abs(hash(a.verbatim_span)) % 10000}",
                        type="adverse_drug_event",
                        severity="moderate",
                        med_name=m.name,
                        explanation=f"Reported symptom (“{a.symptom or a.verbatim_span}”) matches a known "
                                    f"adverse effect of {m.name} ({adr}).",
                        transcript_evidence=a.verbatim_span,
                        transcript_speaker=a.speaker,
                        chart_evidence=_chart_evidence(m),
                        prescriber=m.prescriber,
                        suggested_fix=f"Consider {m.name} as the cause of “{a.symptom or adr}”; reassess the drug.",
                        recommended_resolution=f"Evaluate {m.name} as the symptom cause (clinician decision).",
                        grounding=_prov(m),
                    ))
                    break
    return flags


# --- 9. denied history vs charted problem (assertion-driven) ------------------

def check_denied_history(state: PatientState, assertions: list[ClinicalAssertion]) -> list[Flag]:
    flags: list[Flag] = []
    for a in assertions:
        if a.kind != "deny_history" or not (a.condition or a.verbatim_span):
            continue
        ctoks = _tokens((a.condition or "") + " " + a.verbatim_span)
        for problem in state.problems:
            if _tokens(problem) & ctoks:
                flags.append(Flag(
                    id=f"hist-{abs(hash(a.verbatim_span)) % 10000}",
                    type="history_mismatch",
                    severity="moderate",
                    med_name=None,
                    explanation=f"History denied in conversation (“{a.condition or a.verbatim_span}”) but "
                                f"“{problem}” is an active charted problem.",
                    transcript_evidence=a.verbatim_span,
                    transcript_speaker=a.speaker,
                    chart_evidence=ChartEvidence(resource_type="Condition", resource_id=None, display=problem),
                    prescriber=Prescriber(),
                    suggested_fix=f"Reconcile the history: “{problem}” is charted and active.",
                    recommended_resolution=f"Keep charted “{problem}”; verify with the patient.",
                    grounding="real",
                ))
                break
    return flags


# --- 10. stop said, still active (assertion-driven) ---------------------------

def check_discontinued_but_active(state: PatientState, assertions: list[ClinicalAssertion]) -> list[Flag]:
    flags: list[Flag] = []
    active_by_key = {kb.resolve_drug(m.name): m for m in state.active_meds() if kb.resolve_drug(m.name)}
    for a in assertions:
        if a.kind != "stop" or not a.drug:
            continue
        key = kb.resolve_drug(a.drug)
        med = active_by_key.get(key)
        if not med:
            continue
        flags.append(Flag(
            id=f"disc-{med.id}",
            type="discontinued_but_active",
            severity="high",
            med_name=med.name,
            explanation=f"{med.name} was said to be discontinued but is still active on the chart.",
            transcript_evidence=a.verbatim_span,
            transcript_speaker=a.speaker,
            chart_evidence=_chart_evidence(med),
            prescriber=med.prescriber,
            suggested_fix=f"Discontinue {med.name} in the orders to match the stated plan.",
            recommended_resolution=f"Stop {med.name} (stated discontinued).",
            grounding=_prov(med),
        ))
    return flags


# --- 11. spoken order not recorded (assertion-driven) -------------------------

def check_mentioned_not_recorded(state: PatientState, assertions: list[ClinicalAssertion]) -> list[Flag]:
    chart_keys = {kb.resolve_drug(m.name) for m in state.meds}
    chart_names = " ".join(m.name.lower() for m in state.meds)
    flags: list[Flag] = []
    seen: set[str] = set()
    for a in assertions:
        if a.source != "llm" or a.kind not in ("prescribe", "continue") or not a.drug:
            continue
        key = kb.resolve_drug(a.drug)
        recorded = (key and key in chart_keys) or (a.drug.lower() in chart_names)
        if recorded or a.drug.lower() in seen:
            continue
        seen.add(a.drug.lower())
        flags.append(Flag(
            id=f"unrec-{abs(hash(a.drug)) % 10000}",
            type="mentioned_not_recorded",
            severity="moderate",
            med_name=a.drug,
            explanation=f"{a.drug} was discussed in the visit but is not on the medication orders.",
            transcript_evidence=a.verbatim_span,
            transcript_speaker=a.speaker,
            chart_evidence=None,
            prescriber=Prescriber(name=a.speaker),
            suggested_fix=f"Add {a.drug} to the orders or document why it was not started.",
            recommended_resolution=f"Record {a.drug} if it was intended.",
            grounding="real",
        ))
    return flags


ALL_CHECKS = [
    check_drug_allergy,
    check_renal_dose,
    check_drug_drug,
    check_duplicate,
    check_dropped_home_med,
    check_teratogen,
    check_cross_prescriber,
    check_adverse_event,
    check_denied_history,
    check_discontinued_but_active,
    check_mentioned_not_recorded,
]


def run_checks(state: PatientState, assertions: list[ClinicalAssertion]) -> list[Flag]:
    flags: list[Flag] = []
    for check in ALL_CHECKS:
        flags.extend(check(state, assertions))
    return flags
