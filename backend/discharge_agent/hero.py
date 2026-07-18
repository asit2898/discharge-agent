"""The grounded hero case — a REAL Synthea chart + planted discharge discrepancies.

The bundle and its answer key are BUILT by data/build_hero.py (real Synthea substrate
for Georgine Boyle + the planted acute multi-day, multi-specialist stay) and written to
data/hero/hero_record.json + data/hero/hero_labels.json. This module just loads them and
adapts them to the API models — so the "data" is a real artifact on disk, versioned and
inspectable, not hand-built in code.

Provenance: home meds, the chronic problem list, and baseline labs are REAL Synthea
resources (real RxNorm/SNOMED/LOINC codes, real ids); the acute stay (hip fracture, AF,
UTI, AKI, the four teams' orders, the penicillin allergy) is planted on top and tagged
"_prov": "injected". Six of the thirteen catches anchor to real resource ids.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from . import config
from .loader import compute_age
from .normalize import normalize_meds
from .schemas import EncounterDetail, Flag, PatientHeader, Reconciliation, ReconStats

HERO_ID = "hero::georgine-boyle-discharge"

_HERO_DIR = config.REPO_ROOT / "data" / "hero"
_RECORD_PATH = _HERO_DIR / "hero_record.json"
_LABELS_PATH = _HERO_DIR / "hero_labels.json"

_SEVERITY_RANK = {"high": 0, "moderate": 1, "low": 2}


@lru_cache(maxsize=1)
def hero_record() -> dict[str, Any]:
    return json.loads(_RECORD_PATH.read_text())


@lru_cache(maxsize=1)
def _hero_labels() -> dict[str, Any]:
    return json.loads(_LABELS_PATH.read_text())


def hero_meds():
    """Derived FROM the bundle via the normalizer — grounded, not hand-listed."""
    return normalize_meds(hero_record())


def hero_flags() -> list[Flag]:
    flags = [Flag(**d) for d in _hero_labels()["discrepancies"]]
    flags.sort(key=lambda f: _SEVERITY_RANK.get(f.severity, 9))
    return flags


def hero_header() -> PatientHeader:
    rec = hero_record()
    pat = rec["patient_context"]["patient"]
    nm = pat["name"][0]
    name = f"{' '.join(nm.get('given', []))} {nm.get('family', '')}".strip()
    allergies = rec["patient_context"]["longitudinal_summary"].get("allergy_labels", [])
    return PatientHeader(
        name=name,
        mrn=rec["metadata"].get("mrn", f"MRN {pat['id'][:8].upper()}"),
        gender=pat.get("gender"),
        age=compute_age(pat.get("birthDate"), rec["metadata"].get("date")),
        dob=pat.get("birthDate"),
        code_status="Full Code",
        location="5 West · Bed 512-A",
        allergies=allergies,
        attending="Dr. Chen (Hospitalist)",
    )


def hero_detail() -> EncounterDetail:
    rec = hero_record()
    return EncounterDetail(
        id=HERO_ID,
        header=hero_header(),
        metadata=rec["metadata"],
        transcript=rec["transcript"],
        note=rec["note"],
        after_visit_summary=rec["after_visit_summary"],
        meds=hero_meds(),
    )


def _flag_matches_med(flag: Flag, med) -> bool:
    if flag.chart_evidence and flag.chart_evidence.resource_id == med.id:
        return True
    if flag.med_name and med.name.lower().startswith(flag.med_name.lower()):
        return True
    return False


def hero_reconciliation() -> Reconciliation:
    meds = hero_meds()
    flags = hero_flags()
    flagged = {m.id for m in meds if any(_flag_matches_med(f, m) for f in flags)}
    return Reconciliation(
        encounter_id=HERO_ID,
        draft_meds=meds,
        flags=flags,
        stats=ReconStats(
            total_meds=len(meds),
            agree_count=len(meds) - len(flagged),
            flag_count=len(flags),
            high_severity_count=sum(1 for f in flags if f.severity == "high"),
        ),
    )
