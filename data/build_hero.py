"""Build the grounded hero record from a REAL Synthea chart + planted discrepancies.

Method (mirrors synthea_to_records.py / docs/data-pipeline-notes.md):
  1. Take Georgine Boyle's REAL Synthea substrate (data/hero/synthea_substrate.json):
     real Patient, real active problem list, real home meds (real RxNorm codes), real
     baseline labs.
  2. Plant the acute multi-day, multi-specialist inpatient stay ON TOP — the hip
     fracture, new AF, UTI, AKI, the four teams' discharge orders, and an injected
     penicillin allergy — each injected resource tagged  "_prov": "injected".
  3. Emit an Abridge-schema record (data/hero/hero_record.json) + an answer key
     (data/hero/hero_labels.json). Several catches anchor to REAL resource ids
     (metformin, insulin, amlodipine, tramadol, the T2DM problem); the rest use the
     injected acute orders. Every catch is labeled real- vs injected-grounded.

Run:  python3 data/build_hero.py
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SUB = os.path.join(HERE, "hero", "synthea_substrate.json")
OUT_REC = os.path.join(HERE, "hero", "hero_record.json")
OUT_LAB = os.path.join(HERE, "hero", "hero_labels.json")

HERO_ID = "hero::georgine-boyle-discharge"
ADMIT, DISCHARGE = "2026-07-13", "2026-07-17"

# --- prescribers -------------------------------------------------------------
PCP = ("Dr. Lin (PCP)", "1990000000")
HOSP = ("Dr. Chen (Hospitalist)", "1990000001")
ORTHO = ("Dr. Okafor (Orthopedic Surgery)", "1990000002")
CARD = ("Dr. Patel (Cardiology)", "1990000003")
ID_ = ("Dr. Reyes (Infectious Disease)", "1990000004")


def requester(p):
    return {"reference": f"Practitioner?identifier=http://hl7.org/fhir/sid/us-npi|{p[1]}", "display": p[0]}


# RxNorm codes for every injected med, resolved against the NLM RxNav API
# (rxnav.nlm.nih.gov) — so the planted orders carry the same real drug codings the
# genuine Synthea home meds do, and the bundle is uniform under inspection.
RXNORM = "http://www.nlm.nih.gov/research/umls/rxnorm"
RXCODES = {
    "Apixaban 5 mg Oral Tablet": ("1364445", "apixaban 5 MG Oral Tablet"),
    "Enoxaparin 40 mg/0.4 mL SC Injection": ("854235", "0.4 ML enoxaparin sodium 100 MG/ML Prefilled Syringe"),
    "Ampicillin-sulbactam 3 g IV": ("1659598", "ampicillin 2000 MG / sulbactam 1000 MG Injection"),
    "Ibuprofen 600 mg Oral Tablet": ("197806", "ibuprofen 600 MG Oral Tablet"),
    "Aspirin 81 mg Oral Tablet": ("308416", "aspirin 81 MG Delayed Release Oral Tablet"),
    "amLODIPine 5 mg Oral Tablet": ("197361", "amlodipine 5 MG Oral Tablet"),
    "Cephalexin 500 mg Oral Capsule": ("309114", "cephalexin 500 MG Oral Capsule"),
    "Oxycodone 5 mg Oral Tablet": ("1049621", "oxycodone hydrochloride 5 MG Oral Tablet"),
    "Pantoprazole 40 mg Oral Tablet": ("314200", "pantoprazole 40 MG Delayed Release Oral Tablet"),
    "Acetaminophen 650 mg Oral Tablet": ("198444", "acetaminophen 650 MG Oral Tablet"),
    "Docusate sodium 100 mg Oral Capsule": ("1115005", "docusate sodium 100 MG Oral Capsule"),
    "Ondansetron 4 mg Oral Tablet": ("198052", "ondansetron 4 MG Oral Tablet"),
    "Sodium chloride 0.9% 1000 mL IV": ("313002", "0.9 % Sodium Chloride Injectable Solution"),
}

# LOINC codes for the lab panel (real LOINCs) so injected Observations are coded too.
LOINC = "http://loinc.org"
LAB_LOINC = {
    "Sodium": ("2951-2", "mmol/L"), "Potassium": ("2823-3", "mmol/L"),
    "Chloride": ("2075-0", "mmol/L"), "Carbon dioxide": ("2028-9", "mmol/L"),
    "Urea nitrogen": ("3094-0", "mg/dL"), "Creatinine": ("2160-0", "mg/dL"),
    "eGFR": ("48642-3", "mL/min/1.73m2"), "Glucose": ("2345-7", "mg/dL"),
    "Hemoglobin A1c": ("4548-4", "%"), "Hemoglobin": ("718-7", "g/dL"),
}


def mr(rid, name, dose, unit, route, freq, category, who, authored, status="active", prov="injected", end=None):
    di = {"text": f"{dose} {unit} {route} {freq}", "route": {"text": route},
          "timing": {"code": {"text": freq}}, "doseAndRate": [{"doseQuantity": {"value": dose, "unit": unit}}]}
    cc = {"text": name}
    if name in RXCODES:
        rxcui, disp = RXCODES[name]
        cc = {"coding": [{"system": RXNORM, "code": rxcui, "display": disp}], "text": name}
    m = {"resourceType": "MedicationRequest", "id": rid, "status": status, "intent": "order",
         "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/medicationrequest-category",
                                    "code": category, "display": category.capitalize()}], "text": category.capitalize()}],
         "medicationCodeableConcept": cc, "authoredOn": f"{authored}T09:00:00-07:00",
         "requester": requester(who), "dosageInstruction": [di], "_prov": prov}
    if end:
        m["dispenseRequest"] = {"validityPeriod": {"end": end}}
    return m


def lab(oid, key, value, when, interp=None, ref_low=None, ref_high=None, prov="injected"):
    """A LOINC-coded Observation with units + optional reference range (real-EHR shape)."""
    code, unit = LAB_LOINC[key]
    o = {"resourceType": "Observation", "id": oid, "status": "final",
         "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                    "code": "laboratory"}]}],
         "code": {"coding": [{"system": LOINC, "code": code, "display": key}], "text": key},
         "valueQuantity": {"value": value, "unit": unit, "system": "http://unitsofmeasure.org"},
         "effectiveDateTime": f"{when}T07:00:00-07:00", "_prov": prov}
    if interp:
        o["interpretation"] = [{"text": interp}]
    if ref_low is not None or ref_high is not None:
        rng = {}
        if ref_low is not None:
            rng["low"] = {"value": ref_low, "unit": unit}
        if ref_high is not None:
            rng["high"] = {"value": ref_high, "unit": unit}
        o["referenceRange"] = [rng]
    return o


def condition(cid, label, onset, prov="injected"):
    return {"resourceType": "Condition", "id": cid, "clinicalStatus": {"coding": [{"code": "active"}]},
            "code": {"text": label}, "onsetDateTime": onset, "_prov": prov}


def observation(oid, label, value, unit, when, interp, prov="injected"):
    return {"resourceType": "Observation", "id": oid, "status": "final", "code": {"text": label},
            "valueQuantity": {"value": value, "unit": unit}, "interpretation": [{"text": interp}],
            "effectiveDateTime": f"{when}T07:00:00-07:00", "_prov": prov}


def flag(fid, ftype, sev, med, expl, quote, speaker, ev_type, ev_id, ev_disp, who, fix, resolution, grounding):
    return {"id": fid, "type": ftype, "severity": sev, "med_name": med, "explanation": expl,
            "transcript_evidence": quote, "transcript_speaker": speaker,
            "chart_evidence": {"resource_type": ev_type, "resource_id": ev_id, "display": ev_disp},
            "prescriber": {"name": who[0], "npi": who[1]} if who else {"name": None, "npi": None},
            "suggested_fix": fix, "recommended_resolution": resolution, "status": "pending",
            "grounding": grounding}


def main():
    sub = json.load(open(SUB))
    pat = sub["patient"]

    # index real home meds / conditions by keyword -> real id
    real_med = {}
    for m in sub["home_medications"]:
        t = m["medicationCodeableConcept"]["text"].lower()
        m.setdefault("category", [{"coding": [{"code": "community"}], "text": "Community"}])
        m["authoredOn"] = "2025-11-01T09:00:00-07:00"
        m["requester"] = requester(PCP)
        m["dosageInstruction"] = m.get("dosageInstruction") or [{"text": ""}]
        # Discharge snapshot: home meds are carried onto the discharge draft EXCEPT insulin,
        # which was omitted (the planted dropped-home-med). This is the point-in-time state
        # the default disposition reads from — not inferred from any flag.
        m["_on_discharge"] = "insulin" not in t
        if "metformin" in t: real_med["metformin"] = m
        elif "amlodipine" in t: real_med["amlodipine"] = m
        elif "insulin" in t: real_med["insulin"] = m
        elif "tramadol" in t: real_med["tramadol"] = m
    real_cond = {}
    for c in sub["conditions"]:
        t = c["code"]["text"].lower()
        if "diabetes mellitus type 2" in t: real_cond["t2dm"] = c
        if "kidney disease" in t: real_cond["ckd"] = c
        if "hypertension" in t: real_cond["htn"] = c

    # ---- coherent lab panel -------------------------------------------------
    # Synthea's own creatinine/eGFR pair was internally inconsistent (Cr 1.9 vs eGFR 73),
    # so we author a self-consistent timeline instead. Values verified against CKD-EPI
    # 2021 for a 74F: Cr 1.3 -> eGFR 42 (baseline CKD3a); Cr 2.1 -> eGFR 24 (AKI nadir).
    # Na/K baselines keep Synthea's real values.
    baseline_labs = [
        lab("obs-na-base", "Sodium", 141, "2026-06-03", ref_low=136, ref_high=145, prov="real"),
        lab("obs-k-base", "Potassium", 4.3, "2026-06-03", ref_low=3.5, ref_high=5.1, prov="real"),
        lab("obs-cr-base", "Creatinine", 1.3, "2026-06-03", "High", 0.6, 1.1),
        lab("obs-egfr-base", "eGFR", 42, "2026-06-03", "Low (G3a)", ref_low=60),
        lab("obs-bun-base", "Urea nitrogen", 26, "2026-06-03", "High", 7, 20),
        lab("obs-glu-base", "Glucose", 158, "2026-06-03", "High", 70, 99),
        lab("obs-a1c", "Hemoglobin A1c", 7.8, "2026-06-03", "High", ref_high=5.7),
        lab("obs-hgb", "Hemoglobin", 10.9, "2026-06-03", "Low", 12.0, 15.5),  # supports charted anemia
    ]
    # AKI + hyperkalemia trend across the stay — makes metformin/tramadol unsafe.
    acute_labs = [
        lab("obs-cr-d1", "Creatinine", 1.7, "2026-07-14", "High", 0.6, 1.1),
        lab("obs-egfr-d1", "eGFR", 31, "2026-07-14", "Low", ref_low=60),
        lab("obs-cr-d2", "Creatinine", 2.1, "2026-07-15", "High", 0.6, 1.1),
        lab("obs-egfr-d2", "eGFR", 24, "2026-07-15", "Low (AKI)", ref_low=60),
        lab("obs-k-d2", "Potassium", 5.2, "2026-07-15", "High", 3.5, 5.1),
        lab("obs-k-high", "Potassium", 5.8, "2026-07-16", "High", 3.5, 5.1),
    ]

    # ---- injected acute problem list (+ current CKD stage, progressed from real CKD2) --
    acute_conds = [
        condition("cond-ckd3", "Chronic kidney disease stage 3 (disorder)", "2020-04-11"),
        condition("cond-hipfx", "Fracture of intertrochanteric section of femur (disorder)", ADMIT),
        condition("cond-afib", "Atrial fibrillation (disorder)", "2026-07-14"),
        condition("cond-uti", "Urinary tract infection (disorder)", ADMIT),
        condition("cond-aki", "Acute kidney injury (disorder)", "2026-07-15"),
        condition("cond-hyperk", "Hyperkalemia (disorder)", "2026-07-16"),
    ]
    # ---- injected allergy ----
    allergy = {"resourceType": "AllergyIntolerance", "id": "allergy-pcn",
               "clinicalStatus": {"coding": [{"code": "active"}]}, "code": {"text": "Penicillin"},
               "reaction": [{"manifestation": [{"text": "Rash"}]}], "_prov": "injected"}

    # ---- the acute stay's medications, realistically categorized -------------
    # INPATIENT ORDERS = the active in-hospital order profile. These are given during the
    # stay and normally STOP at discharge (they don't go home). A real 5-day stay has many.
    inpatient_meds = [
        mr("mr-ampsulbactam", "Ampicillin-sulbactam 3 g IV", 3, "g", "IV", "every 6 hours", "inpatient", ID_, ADMIT, status="stopped"),
        mr("mr-ivfluids", "Sodium chloride 0.9% 1000 mL IV", 1000, "mL", "IV", "at 75 mL/hr", "inpatient", HOSP, ADMIT, status="stopped"),
        mr("mr-pantoprazole", "Pantoprazole 40 mg Oral Tablet", 40, "mg", "PO", "daily", "inpatient", HOSP, ADMIT),
        mr("mr-docusate", "Docusate sodium 100 mg Oral Capsule", 100, "mg", "PO", "twice daily", "inpatient", HOSP, ADMIT),
        mr("mr-ondansetron", "Ondansetron 4 mg Oral Tablet", 4, "mg", "IV", "every 8 hours PRN nausea", "inpatient", HOSP, "2026-07-14"),
    ]
    # DISCHARGE ORDERS = the reconciled home-going draft (continued home meds are handled
    # in the home group; these are the new/continued go-home orders + the planted errors).
    discharge_meds = [
        mr("mr-apixaban", "Apixaban 5 mg Oral Tablet", 5, "mg", "PO", "twice daily", "discharge", CARD, "2026-07-14"),
        mr("mr-enoxaparin", "Enoxaparin 40 mg/0.4 mL SC Injection", 40, "mg", "SC", "daily", "discharge", ORTHO, ADMIT),
        mr("mr-ibuprofen", "Ibuprofen 600 mg Oral Tablet", 600, "mg", "PO", "three times daily PRN", "discharge", ORTHO, "2026-07-15"),
        mr("mr-aspirin", "Aspirin 81 mg Oral Tablet", 81, "mg", "PO", "daily", "discharge", CARD, "2026-07-14"),
        mr("mr-amlodipine-dup", "amLODIPine 5 mg Oral Tablet", 5, "mg", "PO", "twice daily", "discharge", HOSP, "2026-07-15"),
        mr("mr-cephalexin", "Cephalexin 500 mg Oral Capsule", 500, "mg", "PO", "every 6 hours", "discharge", ID_, "2026-07-16"),
        mr("mr-oxycodone", "Oxycodone 5 mg Oral Tablet", 5, "mg", "PO", "every 4 hours PRN pain", "discharge", ORTHO, ADMIT),
        mr("mr-acetaminophen", "Acetaminophen 650 mg Oral Tablet", 650, "mg", "PO", "every 6 hours PRN", "discharge", ORTHO, ADMIT),
    ]
    acute_meds = inpatient_meds + discharge_meds

    # real home meds carried into the encounter (real ids, real codes)
    home = list(real_med.values())

    record = {
        "id": HERO_ID,
        "metadata": {
            "patient_id": pat["id"], "encounter_id": "hero-enc-1", "mrn": "MRN 30291847",
            "date": f"{DISCHARGE}T11:00:00-07:00", "status": "finished",
            "visit_type": "Inpatient discharge (multi-specialist)",
            "visit_title": "Inpatient discharge — hip fracture ORIF with new AF and UTI",
            "teams": ["Hospitalist", "Orthopedic Surgery", "Cardiology", "Infectious Disease"],
            "substrate": "real Synthea chart (Georgine Boyle) + planted discharge discrepancies",
            "is_hero": True,
        },
        "patient_context": {
            "patient": pat,
            "longitudinal_summary": {
                "resource_counts": {"Condition": len(sub["conditions"]) + len(acute_conds),
                                    "MedicationRequest": len(home) + len(acute_meds),
                                    "Observation": len(baseline_labs) + len(acute_labs), "AllergyIntolerance": 1},
                "condition_labels": [c["code"]["text"] for c in sub["conditions"]],
                "medication_labels": [],
                "allergy_labels": ["Penicillin (rash)"],
            },
        },
        "encounter_fhir": {
            "encounter": {"resourceType": "Encounter", "id": "hero-enc-1", "status": "finished",
                          "class": {"code": "IMP", "display": "inpatient encounter"},
                          "period": {"start": f"{ADMIT}T22:10:00-07:00", "end": f"{DISCHARGE}T11:00:00-07:00"}},
            "related_resources": {
                "Condition": sub["conditions"] + acute_conds,
                "AllergyIntolerance": [allergy],
                "Observation": baseline_labs + acute_labs,
                "MedicationRequest": home + acute_meds,
            },
        },
        "transcript": TRANSCRIPT, "note": NOTE, "after_visit_summary": AVS,
        "after_visit_summary_provenance": {"source": "hand-authored on real Synthea substrate"},
    }

    # ---- answer key (flags) ----
    mreal = real_med
    flags = [
        # -- grounded in REAL resources --
        flag("f1", "renal_dose_conflict", "high", "Metformin", RENAL_EXPL, Q_RENAL, "DR. CHEN (Hospitalist), Day 2",
             "MedicationRequest", mreal["metformin"]["id"],
             f'{mreal["metformin"]["medicationCodeableConcept"]["text"]} — active; eGFR now 24',
             HOSP, "Hold metformin; recheck renal function before restarting.",
             "Hold metformin (eGFR 24 < 30 contraindication).", "real"),
        flag("f2", "dropped_home_med", "high", "insulin", INSULIN_EXPL, None, None,
             "MedicationRequest", mreal["insulin"]["id"],
             f'{mreal["insulin"]["medicationCodeableConcept"]["text"]} — home med, not on discharge orders',
             PCP, "Continue home insulin (Humulin 70/30) on the discharge list with a glucose plan.",
             "Continue insulin (dropping it risks DKA/hyperglycemia).", "real"),
        flag("f3", "adverse_drug_event", "moderate", "amLODIPine", AMLO_EXPL, Q_EDEMA, "DR. CHEN (Hospitalist), Day 2",
             "MedicationRequest", mreal["amlodipine"]["id"],
             f'{mreal["amlodipine"]["medicationCodeableConcept"]["text"]} — active; associated ADR: peripheral edema',
             PCP, "Consider the new leg swelling is amlodipine edema; reassess vs. adding a diuretic.",
             "Evaluate amlodipine as the edema cause (clinician decision).", "real"),
        flag("f4", "renal_dose_conflict", "moderate", "tramadol", TRAMADOL_EXPL, None, None,
             "MedicationRequest", mreal["tramadol"]["id"],
             f'{mreal["tramadol"]["medicationCodeableConcept"]["text"]} — renally cleared; eGFR 24',
             PCP, "Reduce/space tramadol or switch analgesic given eGFR 24 (accumulation + seizure risk).",
             "Renally dose-adjust tramadol.", "real"),
        flag("f5", "history_mismatch", "moderate", None, HISTORY_EXPL, Q_NO_DIABETES, "DR. CHEN (Hospitalist), Day 2",
             "Condition", real_cond["t2dm"]["id"], "Diabetes mellitus type 2 — active problem", HOSP,
             "Reconcile the history: T2DM is charted and she is on metformin + insulin.",
             "Keep charted T2DM; verify with the patient.", "real"),
        flag("f6", "duplicate_therapy", "moderate", "amLODIPine 5", DUP_EXPL, Q_AMLO_ADD, "DR. CHEN (Hospitalist), Day 2",
             "MedicationRequest", "mr-amlodipine-dup",
             f'amLODIPine 5 mg BID — duplicates home {mreal["amlodipine"]["medicationCodeableConcept"]["text"]} ({mreal["amlodipine"]["id"]})',
             HOSP, "Do not stack a second amlodipine order; reconcile to a single dose.",
             "Consolidate to one amlodipine order.", "real"),
        # -- injected acute stay --
        flag("f7", "cross_prescriber_conflict", "high", "Enoxaparin", CROSS_EXPL, Q_STOP_LOVENOX, "DR. PATEL (Cardiology), Day 1",
             "MedicationRequest", "mr-enoxaparin", "Enoxaparin 40 mg SC daily — status: active, category: discharge",
             ORTHO, "Discontinue enoxaparin; continue apixaban as the sole anticoagulant.",
             "Stop enoxaparin (resolves duplicate anticoagulation).", "injected"),
        flag("f8", "drug_allergy_conflict", "high", "Ampicillin-sulbactam", ALLERGY_EXPL, Q_AMP, "DR. REYES (Infectious Disease), Day 3",
             "AllergyIntolerance", "allergy-pcn", "Penicillin — reaction: Rash (active)", ID_,
             "Confirm no discharge penicillin-class order; document the exposure and reaction watch.",
             "Verify allergy; keep non-beta-lactam coverage.", "injected"),
        flag("f9", "drug_drug_interaction", "high", "Ibuprofen", DDI_EXPL, Q_IBU, "DR. OKAFOR (Orthopedic Surgery), Day 2",
             "MedicationRequest", "mr-ibuprofen", "Ibuprofen 600 mg TID — interacts with apixaban (mr-apixaban)",
             ORTHO, "Discontinue ibuprofen; use acetaminophen ± oxycodone for pain.",
             "Stop ibuprofen (bleeding + renal risk on apixaban/AKI).", "injected"),
        flag("f10", "discontinued_but_active", "high", "Aspirin", ASPIRIN_EXPL, Q_HOLD_ASA, "DR. PATEL (Cardiology), Day 1",
             "MedicationRequest", "mr-aspirin", "Aspirin 81 mg daily — status: active", CARD,
             "Discontinue aspirin for the duration of apixaban therapy.",
             "Stop aspirin (bleeding-risk stacking with apixaban).", "injected"),
        flag("f11", "orphaned_course", "moderate", "Cephalexin", ORPHAN_EXPL, Q_CEPH, "DR. REYES (Infectious Disease), Day 3",
             "MedicationRequest", "mr-cephalexin", "Cephalexin 500 mg q6h — no end date on order", ID_,
             "Add a stop date of 2026-07-19 (completes the 7-day course).",
             "Set cephalexin end date to 2026-07-19.", "injected"),
        flag("f12", "mentioned_not_recorded", "moderate", "Metoprolol", MENTION_EXPL, Q_METOP, "DR. PATEL (Cardiology), Day 1",
             "MedicationRequest", None, "No matching discharge order found", CARD,
             "Add metoprolol tartrate 25 mg PO BID to the discharge orders, per Cardiology.",
             "Add metoprolol 25 mg PO BID (captures the spoken order).", "injected"),
        flag("f13", "dropped_result", "high", None, KRESULT_EXPL, Q_POTASSIUM, "DR. CHEN (Hospitalist), Day 3",
             "Observation", "obs-k-high", "Potassium 5.8 mmol/L (2026-07-16) — High, no follow-up ordered", HOSP,
             "Order a BMP within 48–72h and give hyperkalemia precautions.",
             "Add a post-discharge potassium recheck order.", "injected"),
    ]
    labels = {"id": HERO_ID, "has_discrepancy": True, "discrepancies": flags,
              "grounding_summary": {"real": sum(1 for f in flags if f["grounding"] == "real"),
                                    "injected": sum(1 for f in flags if f["grounding"] == "injected"),
                                    "total": len(flags)}}

    os.makedirs(os.path.join(HERE, "hero"), exist_ok=True)
    json.dump(record, open(OUT_REC, "w"), indent=1)
    json.dump(labels, open(OUT_LAB, "w"), indent=1)
    print(f"Wrote {OUT_REC} and {OUT_LAB}")
    print(f"  meds={len(home)+len(acute_meds)} (real home={len(home)}, injected acute={len(acute_meds)})")
    print(f"  flags={len(flags)}  real-grounded={labels['grounding_summary']['real']}  injected={labels['grounding_summary']['injected']}")
    # verify every transcript quote is verbatim-present
    miss = [f["id"] for f in flags if f["transcript_evidence"] and f["transcript_evidence"] not in TRANSCRIPT]
    print("  transcript quotes not found verbatim:", miss or "none")


# --- verbatim transcript lines (single source of truth) ----------------------
Q_STOP_LOVENOX = "Now that she's therapeutic on the apixaban, we can stop the Lovenox — she doesn't need both."
Q_HOLD_ASA = "Let's hold her baby aspirin while she's on the apixaban — no need to stack the bleeding risk without a stent indication."
Q_METOP = "Start her on metoprolol 25 twice a day for rate control, and her PCP can titrate up as needed."
Q_RENAL = "Her kidneys took a real hit — her eGFR is down around 24 now, so hold anything renally cleared."
Q_POTASSIUM = "Her potassium came back at 5.8 this morning; let's just recheck it as an outpatient."
Q_AMLO_ADD = "Her pressures are still running high, so let's add amlodipine 5 twice daily."
Q_EDEMA = "Her ankles are pretty swollen — has she always had that? It's been getting worse this week."
Q_NO_DIABETES = "And she's never had diabetes, right? Nothing like that in her history."
Q_IBU = "Keep the oxycodone for breakthrough pain, and add ibuprofen 600 three times a day for the swelling."
Q_AMP = "We started her on ampicillin-sulbactam empirically the night she came in febrile."
Q_CEPH = "Urine culture's sensitive to cephalexin. Seven days total — she'll finish it on Saturday, then it stops."

RENAL_EXPL = ("Metformin (her home med) is on the discharge list, but this admission's labs show acute kidney "
              "injury with eGFR 24 — metformin is contraindicated below eGFR 30 (lactic-acidosis risk).")
INSULIN_EXPL = ("Her home Humulin 70/30 insulin was never carried onto the discharge orders. Silently dropping "
                "insulin in a type-2 diabetic risks severe hyperglycemia after discharge.")
AMLO_EXPL = ("New, worsening ankle swelling with no cardiac cause noted is classic amlodipine-induced peripheral "
             "edema. Amlodipine is her home antihypertensive.")
TRAMADOL_EXPL = ("Her home tramadol is renally cleared; at eGFR 24 it accumulates and lowers the seizure "
                 "threshold. It needs dose adjustment or substitution in the AKI setting.")
HISTORY_EXPL = ("Rounds stated she has no diabetes history, but Type 2 diabetes mellitus is an active charted "
                "problem and she is on metformin and insulin.")
DUP_EXPL = ("A second amlodipine order (5 mg BID) was added on top of her home amlodipine 2.5 mg — duplicate "
            "therapy of the same drug at a higher combined dose.")
CROSS_EXPL = ("Double anticoagulation on the go-home list: Cardiology started apixaban for new AF; Orthopedics' "
              "DVT-prophylaxis enoxaparin is still active and was carried to discharge. Cardiology verbally "
              "stopped it — the order was never discontinued.")
ALLERGY_EXPL = ("Ampicillin-sulbactam, a penicillin-class antibiotic, was ordered empirically at admission for a "
                "patient with a charted penicillin allergy. The order predates allergy reconciliation.")
DDI_EXPL = ("Ibuprofen was added for swelling while she is on apixaban — an NSAID plus an anticoagulant sharply "
            "raises bleeding risk, and the NSAID is nephrotoxic during the current AKI.")
ASPIRIN_EXPL = ("Aspirin was added and remains active alongside newly-started apixaban. Cardiology directed "
                "holding it to avoid stacking bleeding risk, but it was never removed.")
ORPHAN_EXPL = ("The UTI antibiotic has no stop date. ID intended a fixed 7-day course ending 2026-07-19; as "
               "written it would continue indefinitely.")
MENTION_EXPL = ("Cardiology dictated starting metoprolol 25 mg BID for rate control, but no structured discharge "
                "order was captured — the patient would leave without a rate-control agent.")
KRESULT_EXPL = ("A critical potassium of 5.8 was noted and deferred to an outpatient recheck, but no follow-up "
                "lab or management plan was ordered.")

TRANSCRIPT = f"""\
════════ DAY 0 — {ADMIT} · Admission (ED → Ortho, ID) ════════
NURSE: Okay, Georgine, we're just going to get you settled. Can you tell me what happened?
PT: I got up in the night and my leg just... went out from under me. It hurts something awful.
DR. OKAFOR (Orthopedic Surgery): The X-ray confirms it — an intertrochanteric fracture of
the right hip. We'll take her to the OR today for the repair. Let's start DVT prophylaxis,
enoxaparin 40 subcutaneous daily, and she can have oxycodone for pain.
PT: Am I going to be able to walk again after this?
DR. OKAFOR: You will — we'll have you up with therapy as soon as tomorrow.
DR. REYES (Infectious Disease): Her urine's looking like an infection and she spiked a
fever in the ED. {Q_AMP} We'll narrow it once the culture comes back.

════════ DAY 1 — 2026-07-14 · Post-op · Cardiology consult ════════
DR. PATEL (Cardiology): So the surgery went fine, but her heart's been flipping in and out
of atrial fibrillation since she came out of the OR — that's new for her. I've started her
on apixaban, five milligrams twice a day, to protect against stroke. {Q_STOP_LOVENOX}
NURSE: Got it — so discontinue the Lovenox.
DR. PATEL: Right. And {Q_HOLD_ASA}
DR. PATEL: One more — {Q_METOP}

════════ DAY 2 — 2026-07-15 · Hospitalist rounds ════════
DR. CHEN (Hospitalist): Morning, Georgine. I want to go over a few things. {Q_RENAL}
DR. CHEN: Her blood pressure's been stubborn even after surgery. {Q_AMLO_ADD}
DR. CHEN: {Q_EDEMA}
DAUGHTER: They've been a bit puffy for maybe a week or two, I think, but it's worse now.
DR. CHEN: Good to know. {Q_NO_DIABETES}
PT: No, I don't think so.
DR. OKAFOR (Orthopedic Surgery): Hip incision looks clean. {Q_IBU}

════════ DAY 3 — 2026-07-16 · Hospitalist + ID ════════
DR. CHEN (Hospitalist): {Q_POTASSIUM}
DR. REYES (Infectious Disease): Culture's back. {Q_CEPH}

════════ DAY 4 — {DISCHARGE} · Discharge planning ════════
DR. OKAFOR (Orthopedic Surgery): Hip's healing well — weight-bearing as tolerated, and
she'll continue with home physical therapy.
DR. CHEN (Hospitalist): Alright, let's get her medication list reconciled and the
after-visit summary printed so she can head home.
"""

NOTE = f"""\
# Discharge Summary — Georgine Boyle, 74F   ({ADMIT} → {DISCHARGE})

## Problem List (real chart + this admission)
Essential hypertension · Type 2 diabetes mellitus · Chronic kidney disease · Metabolic
syndrome · Obesity · Chronic low back pain · Right intertrochanteric hip fracture (ORIF)
· New-onset atrial fibrillation · UTI · Post-op acute kidney injury (eGFR nadir 24) ·
Hyperkalemia (K 5.8).

## Hospital Course
Admitted after a mechanical fall. ORIF by Orthopedics (Dr. Okafor). New AF managed by
Cardiology (Dr. Patel); UTI by Infectious Disease (Dr. Reyes); AKI and hyperkalemia by
Hospitalist (Dr. Chen). Four teams contributed medication orders across the stay.

## Discharge Disposition
Home with home health. Medication reconciliation pending — orders span four prescribers
and multiple days; several require a decision.
"""

AVS = """\
## Your medicines — what changed and why
Your care team is finalizing your medication list, reconciling orders from your surgery,
heart, kidney, and infection teams before you go home.
"""

if __name__ == "__main__":
    main()
