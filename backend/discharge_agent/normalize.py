"""Chart Compiler (lite): normalize a record's meds into the common `Med` shape.

Works on two grades of input, identically:
  * The provided Abridge 25 — encounter `MedicationRequest`s reference drug UUIDs with
    no resolvable `Medication` resource and no `display`, so most inpatient med *names*
    are not recoverable. We resolve what we can and label the rest honestly.
  * The hand-authored grounded hero bundle (hero.py) — full FHIR `MedicationRequest`s
    with `medicationCodeableConcept`, `dosageInstruction`, dated `authoredOn`, and a
    per-specialist `requester`. Everything resolves.

Home-med names for the real 25 also come from
`patient_context.longitudinal_summary.medication_labels`.
"""
from __future__ import annotations

from typing import Any

from .loader import is_inpatient
from .schemas import Med, MedCategory, Prescriber

# FHIR medicationrequest-category code -> our source lane.
_CATEGORY_SOURCE = {
    "community": "home",
    "discharge": "discharge",
    "outpatient": "discharge",
    "inpatient": "inpatient",
}


def _resolve_name(mr: dict[str, Any]) -> str:
    cc = mr.get("medicationCodeableConcept")
    if isinstance(cc, dict):
        if cc.get("text"):
            return cc["text"]
        for coding in cc.get("coding", []):
            if coding.get("display"):
                return coding["display"]
    ref = mr.get("medicationReference", {})
    if ref.get("display"):
        return ref["display"]
    return "Inpatient medication (name not in bundle)"


def _category(mr: dict[str, Any]) -> MedCategory:
    for cat in mr.get("category", []):
        for coding in cat.get("coding", []):
            code = coding.get("code")
            if code in ("inpatient", "outpatient", "community", "discharge"):
                return "outpatient" if code == "discharge" else code  # type: ignore[return-value]
        text = (cat.get("text") or "").lower()
        if text in ("inpatient", "outpatient", "community"):
            return text  # type: ignore[return-value]
    return "unknown"


def _dosage(mr: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Return (dose, route, frequency) from dosageInstruction, best-effort."""
    di_list = mr.get("dosageInstruction") or []
    if not di_list:
        return None, None, None
    di = di_list[0]
    route = (di.get("route") or {}).get("text")
    freq = ((di.get("timing") or {}).get("code") or {}).get("text") or None
    dose = None
    for dr in di.get("doseAndRate") or []:
        dq = dr.get("doseQuantity") or {}
        if dq.get("value") is not None:
            dose = f"{dq['value']} {dq.get('unit', '')}".strip()
            break
    return dose, route, freq


def _prescriber(mr: dict[str, Any]) -> Prescriber:
    req = mr.get("requester", {})
    npi = None
    ref = req.get("reference", "")
    if "us-npi|" in ref:
        npi = ref.split("us-npi|", 1)[1]
    return Prescriber(name=req.get("display"), npi=npi)


def _source(cat: MedCategory, mr: dict[str, Any], inpatient: bool) -> str:
    # Prefer the raw FHIR category code (handles the 'discharge' lane the enum folds).
    for c in mr.get("category", []):
        for coding in c.get("coding", []):
            lane = _CATEGORY_SOURCE.get(coding.get("code"))
            if lane:
                return lane
    if cat in ("community",):
        return "home"
    if cat in ("outpatient",):
        return "discharge"
    return "inpatient" if (inpatient or cat == "inpatient") else "discharge"


def normalize_meds(record: dict[str, Any]) -> list[Med]:
    """Home meds (named) + encounter MedicationRequests (source-attributed)."""
    meds: list[Med] = []
    ls = record.get("patient_context", {}).get("longitudinal_summary", {})

    # Home / prior-to-admission meds from labels (only when not already FHIR resources).
    for i, label in enumerate(ls.get("medication_labels", []) or []):
        meds.append(
            Med(id=f"home-{i}", name=label, status="active", category="home", source="home")
        )

    inpatient = is_inpatient(record)
    rr = record.get("encounter_fhir", {}).get("related_resources", {})
    for mr in rr.get("MedicationRequest", []) or []:
        cat = _category(mr)
        dose, route, freq = _dosage(mr)
        src = _source(cat, mr, inpatient)
        # Point-in-time discharge snapshot: on the discharge draft or not. Inpatient-only
        # orders default off (they stop at discharge); discharge/home default on. An
        # explicit `_on_discharge` marker in the data overrides (e.g. a dropped home med).
        on_discharge = mr.get("_on_discharge")
        if on_discharge is None:
            on_discharge = src != "inpatient"
        meds.append(
            Med(
                id=mr.get("id", f"mr-{len(meds)}"),
                name=_resolve_name(mr),
                dose=dose,
                route=route,
                frequency=freq,
                status=mr.get("status"),
                intent=mr.get("intent"),
                category="home" if cat == "community" else cat,
                source=src,  # type: ignore[arg-type]
                prescriber=_prescriber(mr),
                authored_on=mr.get("authoredOn"),
                on_discharge=bool(on_discharge),
            )
        )
    return meds
