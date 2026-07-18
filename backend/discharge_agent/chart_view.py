"""Detail-view extraction for the Epic-style Problem List and Results Review panels.

Distinct from patient_state.py (the engine's *collapsed* chart compiler, which keeps only
the worst value per lab). Here we keep the FULL serial lab history so the frontend can
render a flowsheet trend, and the full problem list with codes + acuity.
"""
from __future__ import annotations

from typing import Any, Optional

from .schemas import LabResult, Problem

_ACUTE_HINTS = (
    "fracture", "atrial fibrillation", "urinary tract", "acute kidney", "hyperkalemia",
    "sepsis", "pneumonia", "acute",
)


def _coding0(concept: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    for c in concept.get("coding", []) or []:
        system = c.get("system", "") or ""
        label = "ICD-10" if "icd" in system.lower() else ("SNOMED" if "snomed" in system.lower() else "LOINC" if "loinc" in system.lower() else None)
        return c.get("code"), label
    return None, None


def extract_problems(record: dict[str, Any], cap: int = 30) -> list[Problem]:
    rr = record.get("encounter_fhir", {}).get("related_resources", {})
    admit = (
        record.get("encounter_fhir", {}).get("encounter", {})
        .get("period", {}).get("start", "")[:10]
    )
    out: list[Problem] = []
    seen: set[str] = set()
    for c in rr.get("Condition", []) or []:
        status = ((c.get("clinicalStatus", {}) or {}).get("coding", [{}]) or [{}])[0].get("code")
        if status not in (None, "active"):
            continue
        label = (c.get("code", {}) or {}).get("text") or "Unknown problem"
        if label.lower() in seen:
            continue
        seen.add(label.lower())
        code, system = _coding0(c.get("code", {}) or {})
        onset = (c.get("onsetDateTime") or "")[:10]
        acute = any(h in label.lower() for h in _ACUTE_HINTS) or (bool(admit) and onset >= admit)
        out.append(Problem(label=label, code=code, system=system, onset=onset or None, acute=acute))
    # acute (this-admission) first, then by onset desc
    out.sort(key=lambda p: (not p.acute, p.onset or ""), reverse=False)
    return out[:cap]


def _is_abnormal(value: float, interp: Optional[str], low: Optional[float], high: Optional[float]) -> bool:
    if interp and interp.strip().lower() not in ("normal", "n", ""):
        return True
    if low is not None and value < low:
        return True
    if high is not None and value > high:
        return True
    return False


def extract_labs(record: dict[str, Any], cap: int = 80) -> list[LabResult]:
    rr = record.get("encounter_fhir", {}).get("related_resources", {})
    out: list[LabResult] = []
    for o in rr.get("Observation", []) or []:
        vq = o.get("valueQuantity")
        if not vq or vq.get("value") is None:
            continue
        cat = ((o.get("category", [{}]) or [{}])[0].get("coding", [{}]) or [{}])[0].get("code")
        if cat and cat != "laboratory":
            continue
        name = (o.get("code", {}) or {}).get("text") or "Lab"
        loinc, _sys = _coding0(o.get("code", {}) or {})
        rng = (o.get("referenceRange", [{}]) or [{}])[0]
        low = (rng.get("low") or {}).get("value")
        high = (rng.get("high") or {}).get("value")
        interp = ((o.get("interpretation", [{}]) or [{}])[0]).get("text")
        val = vq.get("value")
        out.append(
            LabResult(
                name=name,
                loinc=loinc,
                value=str(val),
                unit=vq.get("unit"),
                when=(o.get("effectiveDateTime") or "")[:10] or None,
                interpretation=interp,
                ref_low=low,
                ref_high=high,
                abnormal=_is_abnormal(float(val), interp, low, high),
            )
        )
    return out[:cap]
