"""
Builds the hero-patient fixture for the discharge-agent demo.

Two-stage pipeline (the same shape Abridge used for their dataset):
  1. BASE from Synthea  — a real generated patient (Philomena Goodwin, 78F, Boston)
     and her real RxNorm-coded medications, pulled from synthea-tool output.
  2. CURATED OVERLAY    — a surgical admission across three prescribers
     (surgeon / hospitalist / infectious-disease) with THREE planted
     discrepancies + an authored transcript/note/AVS. Synthea cannot produce
     spoken contradictions or an orphaned course, so those are layered on here.

Output:
  hero_patient.json  — one record in the Abridge synthetic-ambient-fhir schema shape
  ground_truth.json  — the planted discrepancies + agreement cases (for eval)

Note on codes: every `medicationCodeableConcept` uses a real RxNorm code taken
from Philomena's Synthea bundle. We use `medicationCodeableConcept` (self-contained
inline drug name) rather than the dataset's `medicationReference` uuid so each order
carries its own resolvable name — documented deviation for a controllable fixture.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Identity — real Synthea patient (trimmed from the generated bundle)
# ---------------------------------------------------------------------------
PATIENT_ID = "89d0a5a1-39b4-95ef-d7a6-22168f2d641a"
ENCOUNTER_ID = "89d0a5a1-39b4-95ef-adm1-2026dischg0001"
DISPLAY_NAME = "Philomena Goodwin"  # clean narrative name (FHIR keeps Synthea's)

PATIENT = {
    "resourceType": "Patient",
    "id": PATIENT_ID,
    "name": [{"use": "official", "family": "Goodwin327",
              "given": ["Philomena945", "Desire394"], "prefix": ["Ms."]}],
    "gender": "female",
    "birthDate": "1944-05-16",
    "address": [{"line": ["817 Bartoletti Flat"], "city": "Boston",
                 "state": "MA", "postalCode": "02151", "country": "US"}],
    "maritalStatus": {"text": "Never Married"},
    "communication": [{"language": {"text": "English (United States)"}}],
}

# ---------------------------------------------------------------------------
# Prescribers — three specialties (the multi-specialist hero scenario)
# ---------------------------------------------------------------------------
SURGEON = {"npi": "1558112233", "display": "Dr. Priya Nair", "specialty": "General Surgery"}
HOSPITALIST = {"npi": "1669223344", "display": "Dr. Alan Whitfield", "specialty": "Internal Medicine (Hospitalist)"}
ID_DOC = {"npi": "1770334455", "display": "Dr. Marcus Bell", "specialty": "Infectious Disease"}

ADMIT = "2026-07-12"
DISCHARGE = "2026-07-16"


def rx(code, display):
    return {"coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm",
                        "code": code, "display": display}], "text": display}


# Real RxNorm codes pulled from Philomena's Synthea bundle
MEDS = {
    "ramipril":     rx("198188", "ramipril 2.5 MG Oral Capsule"),
    "labetalol":    rx("896758", "labetalol hydrochloride 100 MG Oral Tablet"),
    "metoprolol":   rx("866412", "24 HR metoprolol succinate 100 MG Extended Release Oral Tablet"),
    "atorvastatin": rx("259255", "atorvastatin 80 MG Oral Tablet"),
    "metformin":    rx("860975", "24 HR Metformin hydrochloride 500 MG Extended Release Oral Tablet"),
    "prasugrel":    rx("855812", "prasugrel 10 MG Oral Tablet"),
    "aspirin":      rx("243670", "aspirin 81 MG Oral Tablet"),
    "amoxclav":     rx("562251", "Amoxicillin 250 MG / Clavulanate 125 MG Oral Tablet"),
    "oxycodone":    rx("857005", "Acetaminophen 325 MG / HYDROcodone Bitartrate 7.5 MG Oral Tablet"),
    "enoxaparin":   rx("854228", "Enoxaparin sodium 40 MG/0.4ML Injectable Solution"),
}

_counter = [0]


def med_request(key, category, status, intent, prescriber, authored,
                dosage=None, note=None, extra_id=None):
    _counter[0] += 1
    mr = {
        "resourceType": "MedicationRequest",
        "id": extra_id or f"mr-{_counter[0]:03d}",
        "status": status,
        "intent": intent,
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/medicationrequest-category",
                                  "code": category if category != "discharge" else "outpatient",
                                  "display": category.capitalize()}],
                      "text": category.capitalize()}],
        "medicationCodeableConcept": MEDS[key],
        "subject": {"reference": f"urn:uuid:{PATIENT_ID}"},
        "encounter": {"reference": f"urn:uuid:{ENCOUNTER_ID}"},
        "authoredOn": authored,
        "requester": {
            "reference": f"Practitioner?identifier=http://hl7.org/fhir/sid/us-npi|{prescriber['npi']}",
            "display": prescriber["display"],
        },
    }
    if dosage:
        mr["dosageInstruction"] = [{"text": dosage}]
    if note:
        mr["note"] = [{"text": note}]
    return mr


# ---------------------------------------------------------------------------
# HOME MEDS  (category=community — pre-admission, what she was taking at home)
# ---------------------------------------------------------------------------
home = [
    med_request("ramipril", "community", "active", "order", HOSPITALIST, "2024-05-23", "2.5 mg PO once daily"),
    med_request("labetalol", "community", "active", "order", HOSPITALIST, "2024-05-23", "100 mg PO twice daily"),
    med_request("atorvastatin", "community", "active", "order", HOSPITALIST, "2024-05-23", "80 mg PO once daily at bedtime"),
    med_request("metformin", "community", "active", "order", HOSPITALIST, "2024-05-23", "500 mg PO twice daily"),
    med_request("prasugrel", "community", "active", "order", SURGEON, "2023-11-01", "10 mg PO once daily"),
    med_request("aspirin", "community", "active", "order", SURGEON, "2023-11-01", "81 mg PO once daily"),
]

# ---------------------------------------------------------------------------
# INPATIENT ORDERS  (category=inpatient — what happened during the stay)
# ---------------------------------------------------------------------------
inpatient = [
    # Surgeon
    med_request("prasugrel", "inpatient", "stopped", "order", SURGEON, ADMIT,
                "HOLD peri-operatively", note="Held for laparoscopic cholecystectomy; resume at discharge once hemostasis confirmed."),
    med_request("oxycodone", "inpatient", "active", "order", SURGEON, ADMIT,
                "1 tab PO q6h PRN moderate pain", note="Post-operative analgesia."),
    med_request("enoxaparin", "inpatient", "active", "order", SURGEON, ADMIT,
                "40 mg SC once daily", note="VTE prophylaxis, inpatient only — discontinue at discharge."),
    # Hospitalist
    med_request("ramipril", "inpatient", "stopped", "order", HOSPITALIST, "2026-07-13",
                "HOLD", note="Held for post-operative AKI (Cr 1.1 -> 1.8). Do NOT resume until renal function rechecked by nephrology."),
    med_request("metoprolol", "inpatient", "active", "order", HOSPITALIST, "2026-07-13",
                "100 mg (succinate ER) PO once daily", note="Transitioning from labetalol 100 mg BID to once-daily metoprolol succinate for rate/BP control and simpler dosing. Labetalol discontinued."),
    med_request("atorvastatin", "inpatient", "active", "order", HOSPITALIST, ADMIT, "80 mg PO once daily"),
    med_request("metformin", "inpatient", "stopped", "order", HOSPITALIST, "2026-07-13",
                "HOLD", note="Held during AKI; resume at discharge."),
    # Infectious Disease
    med_request("amoxclav", "inpatient", "active", "order", ID_DOC, "2026-07-13",
                "875/125 mg PO twice daily x 7 days", note="Surgical-site / intra-abdominal infection. 7-day course started 2026-07-13; COMPLETE full course (through 2026-07-19) — 3 days remain at discharge."),
]

# ---------------------------------------------------------------------------
# DISCHARGE ORDER SET  (category=discharge — the pending list we reconcile
# against; THIS is where the three bugs live)
# ---------------------------------------------------------------------------
discharge = [
    # BUG D1: ramipril still here — hospitalist meant it discontinued
    med_request("ramipril", "discharge", "active", "order", HOSPITALIST, DISCHARGE, "2.5 mg PO once daily"),
    # BUG D2: labetalol still here AND metoprolol added -> duplicate beta-blocker
    med_request("labetalol", "discharge", "active", "order", HOSPITALIST, DISCHARGE, "100 mg PO twice daily"),
    med_request("metoprolol", "discharge", "active", "order", HOSPITALIST, DISCHARGE, "100 mg (succinate ER) PO once daily"),
    # correct / agreement cases
    med_request("atorvastatin", "discharge", "active", "order", HOSPITALIST, DISCHARGE, "80 mg PO once daily at bedtime"),
    med_request("metformin", "discharge", "active", "order", HOSPITALIST, DISCHARGE, "500 mg PO twice daily"),
    med_request("prasugrel", "discharge", "active", "order", SURGEON, DISCHARGE, "10 mg PO once daily"),
    med_request("aspirin", "discharge", "active", "order", SURGEON, DISCHARGE, "81 mg PO once daily"),
    med_request("oxycodone", "discharge", "active", "order", SURGEON, DISCHARGE, "1 tab PO q6h PRN moderate pain x 10 tabs"),
    # BUG D3: amoxicillin-clavulanate MISSING (orphaned course — dropped from the list)
]

ALL_MRS = home + inpatient + discharge

# ---------------------------------------------------------------------------
# Encounter
# ---------------------------------------------------------------------------
ENCOUNTER = {
    "resourceType": "Encounter",
    "id": ENCOUNTER_ID,
    "status": "finished",
    "class": {"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "IMP", "display": "inpatient encounter"},
    "type": [{"text": "Inpatient admission — laparoscopic cholecystectomy"}],
    "subject": {"reference": f"urn:uuid:{PATIENT_ID}"},
    "period": {"start": f"{ADMIT}T08:15:00-04:00", "end": f"{DISCHARGE}T14:30:00-04:00"},
    "reasonCode": [{"text": "Acute cholecystitis; post-operative intra-abdominal infection"}],
}

# ---------------------------------------------------------------------------
# Narrative layer — transcript / note / AVS (authored overlay)
# ---------------------------------------------------------------------------
TRANSCRIPT = f"""\
[Discharge rounds — Room 7B. Present: {DISPLAY_NAME} (patient), her nephew Daniel, \
Dr. Whitfield (hospitalist). Dr. Nair (surgery) and Dr. Bell (infectious disease) join briefly.]

DR. WHITFIELD: Good morning, Ms. Goodwin. Big day — you're going home this afternoon. I want to walk through your medicines so you and Daniel know exactly what changes.
PT: Please. I take a lot of them and I get confused.
DR. WHITFIELD: That's exactly why we do this. First — your ramipril, the little blood-pressure capsule. We stopped that when you came in. Your kidney numbers climbed after the surgery, and ramipril can be hard on the kidneys, so I want it to stay off until your kidney doctor rechecks your labs. Do not restart it on your own.
PT: So no more of the little one. For now.
DR. WHITFIELD: For now, correct. Second change — you were taking labetalol twice a day. I've switched you to a once-a-day pill, metoprolol, the extended-release one. It does the same job for your blood pressure and heart rate but it's just once in the morning. So you stop the labetalol completely and take the metoprolol instead.
DANIEL: One beta-blocker, not both. Once a day.
DR. WHITFIELD: Exactly. The rest stay the same — your atorvastatin at night, the metformin twice a day for your sugar.
[Dr. Bell enters.]
DR. BELL: Ms. Goodwin, I'm Dr. Bell, infection team. The antibiotic you're on — the amoxicillin-clavulanate — you're four days into a seven-day course. This is important: you need to finish the full seven days, so that's three more days once you get home. Don't stop early even if you feel well.
PT: Three more days of the antibiotic. Even at home.
DR. BELL: Three more days. It should be on your take-home list and your pharmacy will have it.
[Dr. Nair enters.]
DR. NAIR: Ms. Goodwin, surgery side — the gallbladder came out cleanly. One thing: we held your prasugrel, the heart blood-thinner, around the operation. The incisions look good now, so you can go back on the prasugrel starting today. And I've left you a small number of pain tablets if you need them.
PT: Back on the heart pill. Good.
DR. WHITFIELD: Great. The nurse will print all of this on your after-visit summary before you leave.
"""

NOTE = f"""\
DISCHARGE SUMMARY — {DISPLAY_NAME}, 82F  (Attending: Dr. Whitfield, Hospitalist)
Admitted {ADMIT}, discharged {DISCHARGE}. Dx: Acute cholecystitis s/p laparoscopic \
cholecystectomy (Dr. Nair); post-operative intra-abdominal infection (Infectious Disease, Dr. Bell); \
post-operative AKI, resolving.

MEDICATION RECONCILIATION — physician plan of record:
- Ramipril: DISCONTINUED. Held on admission for post-operative AKI (Cr 1.1 -> 1.8). \
Do NOT resume; nephrology to reassess as outpatient.
- Labetalol: DISCONTINUED. Transitioned to once-daily metoprolol succinate ER 100 mg for \
BP/rate control and dosing simplicity. Patient should take metoprolol, NOT labetalol.
- Metoprolol succinate ER 100 mg daily: CONTINUE (new, replaces labetalol).
- Atorvastatin 80 mg nightly: CONTINUE (unchanged).
- Metformin ER 500 mg BID: CONTINUE (resume at discharge; was held during AKI).
- Prasugrel 10 mg daily: RESUME at discharge (held peri-operatively by surgery; hemostasis confirmed).
- Aspirin 81 mg daily: CONTINUE (unchanged).
- Amoxicillin-clavulanate 875/125 mg BID: CONTINUE to complete 7-day course \
(started 2026-07-13, through 2026-07-19) — 3 days remain after discharge. Per Infectious Disease.
- Hydrocodone/acetaminophen PRN: NEW, short course for post-operative pain.
- Enoxaparin: inpatient VTE prophylaxis only — discontinued at discharge.
"""

AVS = f"""\
After Visit Summary — {DISPLAY_NAME}

Your medicines when you go home
• Metoprolol (once daily) — this REPLACES your old labetalol. Stop the labetalol.
• Atorvastatin at bedtime — no change
• Metformin twice a day — no change
• Prasugrel once daily — restart today
• Aspirin once daily — no change
• Amoxicillin-clavulanate — 3 more days to finish your antibiotic course
• Pain tablets — only if you need them

Stopped for now
• Ramipril — do not restart until your kidney doctor checks your labs
"""

# ---------------------------------------------------------------------------
# Assemble record in Abridge schema shape
# ---------------------------------------------------------------------------
record = {
    "id": f"{PATIENT_ID}::{ENCOUNTER_ID}",
    "metadata": {
        "source": "synthea-fhir-r4 + curated-overlay",
        "synthetic": True,
        "patient_id": PATIENT_ID,
        "encounter_id": ENCOUNTER_ID,
        "encounter_reference": f"urn:uuid:{ENCOUNTER_ID}",
        "date": f"{DISCHARGE}T14:30:00-04:00",
        "status": "finished",
        "visit_type": "Inpatient admission — laparoscopic cholecystectomy",
        "document_status": "current",
        "scenario": "multi-specialist discharge medication reconciliation",
        "prescribers": [SURGEON, HOSPITALIST, ID_DOC],
    },
    "patient_context": {
        "patient": PATIENT,
        "longitudinal_summary": {
            "resource_counts": {"MedicationRequest": len(ALL_MRS), "Encounter": 1},
            "condition_labels": ["Acute cholecystitis (disorder)",
                                 "Post-operative intra-abdominal infection (disorder)",
                                 "Acute kidney injury (disorder)",
                                 "Coronary artery disease (disorder)",
                                 "Essential hypertension (disorder)",
                                 "Type 2 diabetes mellitus (disorder)"],
            "medication_labels": sorted({m["medicationCodeableConcept"]["text"] for m in ALL_MRS}),
        },
    },
    "encounter_fhir": {
        "encounter": ENCOUNTER,
        "related_resources": {"MedicationRequest": ALL_MRS},
    },
    "transcript": TRANSCRIPT,
    "note": NOTE,
    "after_visit_summary": AVS,
    "after_visit_summary_provenance": {"authored_by": "curated-overlay", "model": "hand-authored"},
}

# ---------------------------------------------------------------------------
# Ground truth (for eval) — the planted discrepancies + agreement cases
# ---------------------------------------------------------------------------
ground_truth = {
    "patient": DISPLAY_NAME,
    "encounter_id": ENCOUNTER_ID,
    "planted_discrepancies": [
        {
            "id": "D1",
            "type": "discontinued_but_listed",
            "medication": "ramipril 2.5 mg",
            "prescriber": HOSPITALIST["display"],
            "expected_resolution": "REMOVE from discharge list — intentionally discontinued for post-op AKI.",
            "evidence": {
                "transcript": "We stopped that when you came in ... I want it to stay off until your kidney doctor rechecks",
                "note": "Ramipril: DISCONTINUED. ... Do NOT resume",
                "conflict": "Discharge order set still contains ramipril 2.5 mg active.",
            },
        },
        {
            "id": "D2",
            "type": "duplicate_therapy",
            "medication": "labetalol 100 mg (duplicate of metoprolol succinate ER 100 mg)",
            "prescriber": HOSPITALIST["display"],
            "expected_resolution": "REMOVE labetalol — replaced by once-daily metoprolol; both are beta-blockers.",
            "evidence": {
                "transcript": "you stop the labetalol completely and take the metoprolol instead",
                "note": "Labetalol: DISCONTINUED. Transitioned to once-daily metoprolol succinate",
                "conflict": "Discharge order set contains BOTH labetalol and metoprolol succinate ER.",
            },
        },
        {
            "id": "D3",
            "type": "orphaned_course",
            "medication": "amoxicillin-clavulanate 875/125 mg",
            "prescriber": ID_DOC["display"],
            "expected_resolution": "ADD to discharge list — 3 days remain of a 7-day course.",
            "evidence": {
                "transcript": "you need to finish the full seven days, so that's three more days once you get home",
                "note": "Amoxicillin-clavulanate ... CONTINUE to complete 7-day course ... 3 days remain",
                "conflict": "Active inpatient course; MISSING from the discharge order set.",
            },
        },
    ],
    "agreement_cases_should_not_flag": [
        {"medication": "atorvastatin 80 mg", "reason": "continued unchanged"},
        {"medication": "metformin ER 500 mg", "reason": "held during AKI, correctly resumed at discharge"},
        {"medication": "prasugrel 10 mg", "reason": "held peri-op by surgeon, correctly resumed — note + transcript agree"},
        {"medication": "aspirin 81 mg", "reason": "continued unchanged"},
        {"medication": "metoprolol succinate ER 100 mg", "reason": "intended new med (the switch target), not a duplicate on its own"},
        {"medication": "hydrocodone/acetaminophen", "reason": "new post-op med, expected"},
    ],
}

if __name__ == "__main__":
    with open(os.path.join(HERE, "hero_patient.json"), "w") as f:
        json.dump(record, f, indent=2)
    with open(os.path.join(HERE, "ground_truth.json"), "w") as f:
        json.dump(ground_truth, f, indent=2)
    print("wrote hero_patient.json  (%d MedicationRequests: %d home / %d inpatient / %d discharge)"
          % (len(ALL_MRS), len(home), len(inpatient), len(discharge)))
    print("wrote ground_truth.json  (%d planted discrepancies, %d agreement cases)"
          % (len(ground_truth["planted_discrepancies"]), len(ground_truth["agreement_cases_should_not_flag"])))
