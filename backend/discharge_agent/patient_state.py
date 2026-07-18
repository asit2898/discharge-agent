"""Stage 1 — Chart Compiler (deterministic, no LLM).

Parse a record's FHIR `related_resources` + `patient_context` into a normalized
`PatientState`: active meds (KB-resolved), allergies (with cross-reactivity classes),
the problem list, the safety-relevant labs (eGFR, K, A1c, INR), and a pregnancy flag.

This is pure Python — cheap, reliable, never hallucinates. It is the structured
substrate every downstream check reasons over.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from . import kb
from .normalize import normalize_meds
from .schemas import Med


@dataclass
class Lab:
    key: str                     # egfr | k | a1c | inr | scr ...
    value: float
    unit: Optional[str]
    resource_id: Optional[str]
    display: Optional[str]
    effective: Optional[str]     # ISO datetime, best-effort


@dataclass
class Allergy:
    label: str                   # e.g. "Penicillin"
    classes: set[str]            # cross-reactive drug classes, e.g. {"penicillin"}
    resource_id: Optional[str]
    display: Optional[str]


@dataclass
class PatientState:
    meds: list[Med]
    allergies: list[Allergy]
    problems: list[str]          # active problem-list condition texts (lowercased-safe originals)
    labs: dict[str, Lab]         # keyed by lab key; worst/most-relevant value per key
    pregnant: bool
    record: dict[str, Any] = field(repr=False, default_factory=dict)

    def active_meds(self) -> list[Med]:
        """Meds that will be in effect after discharge: home + discharge lanes, and
        inpatient orders still marked active. Completed/stopped orders are excluded."""
        out = []
        for m in self.meds:
            if (m.status or "active") in ("stopped", "completed", "cancelled"):
                continue
            out.append(m)
        return out


# ---- lab extraction ----------------------------------------------------------

# Map a lab observation to a KB lab key by LOINC code first, then display text.
_LOINC_TO_KEY = {code: key for key, (code, _disp, _unit) in kb.LOINC_CODES.items()}
_TEXT_HINTS = {
    "egfr": ("glomerular filtration", "egfr"),
    "scr": ("creatinine",),
    "k": ("potassium",),
    "a1c": ("hemoglobin a1c", "a1c"),
    "inr": ("inr",),
    "tsh": ("thyrotropin", "tsh"),
}

# For these labs the *worst* value is the safety-relevant one (lowest renal function,
# highest potassium). For others we keep the most recent seen.
_WORST_IS_MIN = {"egfr"}
_WORST_IS_MAX = {"k", "inr", "a1c"}


def _obs_key(obs: dict[str, Any]) -> Optional[str]:
    code = obs.get("code", {}) or {}
    for coding in code.get("coding", []) or []:
        k = _LOINC_TO_KEY.get(coding.get("code"))
        if k:
            return k
    text = (code.get("text") or "").lower()
    for coding in code.get("coding", []) or []:
        text += " " + (coding.get("display") or "").lower()
    for key, hints in _TEXT_HINTS.items():
        if any(h in text for h in hints):
            return key
    return None


def _extract_labs(rr: dict[str, Any]) -> dict[str, Lab]:
    labs: dict[str, Lab] = {}
    for obs in rr.get("Observation", []) or []:
        key = _obs_key(obs)
        if not key:
            continue
        vq = obs.get("valueQuantity") or {}
        val = vq.get("value")
        if val is None:
            continue
        code = obs.get("code", {}) or {}
        display = code.get("text") or (code.get("coding") or [{}])[0].get("display")
        lab = Lab(
            key=key,
            value=float(val),
            unit=vq.get("unit"),
            resource_id=obs.get("id"),
            display=display,
            effective=obs.get("effectiveDateTime"),
        )
        prev = labs.get(key)
        if prev is None:
            labs[key] = lab
        elif key in _WORST_IS_MIN:
            if lab.value < prev.value:
                labs[key] = lab
        elif key in _WORST_IS_MAX:
            if lab.value > prev.value:
                labs[key] = lab
        else:
            # keep most recent by effective time when available
            if (lab.effective or "") >= (prev.effective or ""):
                labs[key] = lab
    return labs


# ---- allergy extraction ------------------------------------------------------

def _classes_for_label(label: str) -> set[str]:
    """Cross-reactivity classes for a charted allergy label. Exact ALLERGY_CROSS
    hit first; else derive the class from a drug name embedded in the label."""
    for known, info in kb.ALLERGY_CROSS.items():
        if known.lower() in label.lower() or label.lower() in known.lower():
            return set(info["classes"])
    cls = kb.drug_class(label)
    return {cls} if cls else set()


def _extract_allergies(rr: dict[str, Any], ls: dict[str, Any]) -> list[Allergy]:
    out: list[Allergy] = []
    seen: set[str] = set()
    for a in rr.get("AllergyIntolerance", []) or []:
        code = a.get("code", {}) or {}
        label = code.get("text") or (code.get("coding") or [{}])[0].get("display")
        if not label:
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            Allergy(
                label=label,
                classes=_classes_for_label(label),
                resource_id=a.get("id"),
                display=label,
            )
        )
    # Fall back to longitudinal_summary allergy_labels when no FHIR resource carries them.
    for label in ls.get("allergy_labels", []) or []:
        base = label.split("(")[0].strip()
        if base.lower() in seen or not base:
            continue
        seen.add(base.lower())
        out.append(Allergy(label=base, classes=_classes_for_label(base), resource_id=None, display=label))
    return out


# ---- problems + pregnancy ----------------------------------------------------

_PREGNANCY_HINTS = ("pregnan", "gestation", "gravida")


def _extract_problems(rr: dict[str, Any], ls: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for c in rr.get("Condition", []) or []:
        code = c.get("code", {}) or {}
        text = code.get("text") or (code.get("coding") or [{}])[0].get("display")
        if not text:
            continue
        # active problem-list items only
        status = ((c.get("clinicalStatus") or {}).get("coding") or [{}])[0].get("code", "active")
        if status not in ("active", "recurrence", "relapse"):
            continue
        if text.lower() in seen:
            continue
        seen.add(text.lower())
        problems.append(text)
    for text in ls.get("condition_labels", []) or []:
        if text.lower() not in seen:
            seen.add(text.lower())
            problems.append(text)
    return problems


def compile_state(record: dict[str, Any]) -> PatientState:
    rr = record.get("encounter_fhir", {}).get("related_resources", {}) or {}
    ls = record.get("patient_context", {}).get("longitudinal_summary", {}) or {}
    problems = _extract_problems(rr, ls)
    pregnant = any(any(h in p.lower() for h in _PREGNANCY_HINTS) for p in problems)
    return PatientState(
        meds=normalize_meds(record),
        allergies=_extract_allergies(rr, ls),
        problems=problems,
        labs=_extract_labs(rr),
        pregnant=pregnant,
        record=record,
    )
