"""FastAPI app — the copilot's backend.

Endpoints (all under /api):
  GET /api/health
  GET /api/encounters                 -> list (hero first, then the real 25)
  GET /api/encounters/{id}            -> full detail (header, transcript, note, meds)
  GET /api/encounters/{id}/reconcile  -> Reconciliation (draft meds + flag queue)
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import config, hero
from .engine import reconcile
from .loader import compute_age, get_record, is_inpatient, load_records
from .normalize import normalize_meds
from .schemas import (
    EncounterDetail,
    EncounterSummary,
    PatientHeader,
    Reconciliation,
)

app = FastAPI(title="Discharge Reconciliation Copilot", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_ORIGIN, "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "records_loaded": len(load_records())}


@app.get("/api/encounters", response_model=list[EncounterSummary])
def list_encounters() -> list[EncounterSummary]:
    out: list[EncounterSummary] = []

    # Hero first — the demo star.
    hrecon = hero.hero_reconciliation()
    hdetail = hero.hero_detail()
    out.append(
        EncounterSummary(
            id=hero.HERO_ID,
            patient_id="hero",
            date=hdetail.metadata.get("date"),
            visit_title=hdetail.metadata.get("visit_title"),
            visit_type=hdetail.metadata.get("visit_type"),
            gender=hdetail.header.gender,
            age=hdetail.header.age,
            is_inpatient=True,
            med_count=len(hrecon.draft_meds),
            flag_count=hrecon.stats.flag_count,
            is_hero=True,
        )
    )

    for rid, rec in load_records().items():
        meta = rec.get("metadata", {})
        patient = rec.get("patient_context", {}).get("patient", {})
        birth = patient.get("birthDate") or meta.get("birth_date")
        out.append(
            EncounterSummary(
                id=rid,
                patient_id=meta.get("patient_id", rid.split("::", 1)[0]),
                date=(meta.get("date") or "")[:10] or None,
                visit_title=meta.get("visit_title"),
                visit_type=meta.get("visit_type"),
                gender=patient.get("gender") or meta.get("gender"),
                age=compute_age(birth, meta.get("date")),
                is_inpatient=is_inpatient(rec),
                med_count=len(normalize_meds(rec)),
                flag_count=0,
                is_hero=False,
            )
        )
    return out


def _patient_header(rec: dict) -> PatientHeader:
    patient = rec.get("patient_context", {}).get("patient", {})
    meta = rec.get("metadata", {})
    name = "Unknown Patient"
    names = patient.get("name") or []
    if names:
        n = names[0]
        given = " ".join(n.get("given", []))
        name = f"{given} {n.get('family', '')}".strip() or name
    birth = patient.get("birthDate") or meta.get("birth_date")
    ls = rec.get("patient_context", {}).get("longitudinal_summary", {})
    allergies = ls.get("allergy_labels", []) or []
    return PatientHeader(
        name=name,
        mrn=f"MRN {meta.get('patient_id', '')[:8].upper()}",
        gender=patient.get("gender") or meta.get("gender"),
        age=compute_age(birth, meta.get("date")),
        dob=(birth or "")[:10] or None,
        location="Inpatient" if is_inpatient(rec) else "Outpatient clinic",
        allergies=allergies,
    )


@app.get("/api/encounters/{record_id}", response_model=EncounterDetail)
def get_encounter(record_id: str) -> EncounterDetail:
    if record_id == hero.HERO_ID:
        return hero.hero_detail()
    rec = get_record(record_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="encounter not found")
    return EncounterDetail(
        id=record_id,
        header=_patient_header(rec),
        metadata=rec.get("metadata", {}),
        transcript=rec.get("transcript", ""),
        note=rec.get("note", ""),
        after_visit_summary=rec.get("after_visit_summary", ""),
        meds=normalize_meds(rec),
    )


@app.get("/api/encounters/{record_id}/reconcile", response_model=Reconciliation)
def get_reconciliation(record_id: str) -> Reconciliation:
    recon = reconcile(record_id)
    if recon is None:
        raise HTTPException(status_code=404, detail="encounter not found")
    return recon
