"""Stage 2 — Assertion Extractor.

Turn the messy discharge conversation (transcript + note) into a typed list of
`ClinicalAssertion`s, each grounded by a verbatim span. This is the one thing only an
LLM can do well; the deterministic checks then reason over these + the PatientState.

When no LLM key is present, `extract_assertions` still returns the chart-derived
`prescribe`/`continue` assertions (one per active med) so the chart-vs-chart checks
(allergy, renal, interaction, duplicate, dropped-med) run unchanged. The transcript-only
checks (adverse-event, denied-history, discontinued-but-active, mentioned-not-recorded)
light up when the LLM comes online.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import llm
from .patient_state import PatientState

# kind vocabulary mirrors docs/engine.md
ASSERTION_KINDS = (
    "prescribe",        # start/continue a drug on discharge
    "continue",         # explicitly keep a home med
    "stop",             # discontinue a drug
    "deny_history",     # clinician/patient denies a condition
    "report_symptom",   # patient reports a symptom
    "state_fact",       # a lab/result/plan stated aloud
)


@dataclass
class ClinicalAssertion:
    kind: str
    drug: Optional[str] = None
    dose: Optional[str] = None
    condition: Optional[str] = None
    symptom: Optional[str] = None
    verbatim_span: str = ""
    speaker: Optional[str] = None
    source: str = "llm"          # llm | chart


_SCHEMA = {
    "type": "object",
    "properties": {
        "assertions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": list(ASSERTION_KINDS),
                             "description": "the clinical speech-act type"},
                    "drug": {"type": "string", "description": "drug name if the assertion is about a medication"},
                    "dose": {"type": "string"},
                    "condition": {"type": "string", "description": "condition/diagnosis if about history"},
                    "symptom": {"type": "string", "description": "patient-reported symptom if kind=report_symptom"},
                    "verbatim_span": {"type": "string",
                                      "description": "EXACT quote from the transcript/note that grounds this assertion — required"},
                    "speaker": {"type": "string", "description": "who said it, e.g. 'DR. CHEN (Hospitalist), Day 2'"},
                },
                "required": ["kind", "verbatim_span"],
            },
        }
    },
    "required": ["assertions"],
}

_SYSTEM = """You are a clinical scribe auditor. Extract every clinically load-bearing \
assertion from a hospital discharge conversation and note. Each assertion MUST include a \
verbatim_span quoted exactly from the source text — no span, no assertion. Do not infer \
facts that were not stated. Capture: drugs started/continued/stopped, denied history, \
patient-reported symptoms, and stated labs/results/plans. Be precise and exhaustive; \
downstream safety checks depend on your spans being real."""


def _llm_assertions(transcript: str, note: str) -> list[ClinicalAssertion]:
    user = f"TRANSCRIPT:\n{transcript}\n\nDISCHARGE NOTE:\n{note}\n\nExtract the assertions."
    out = llm.call_structured(
        model=llm.EXTRACT_MODEL,
        system=_SYSTEM,
        user=user,
        tool_name="record_assertions",
        tool_description="Record the typed clinical assertions extracted from the visit.",
        schema=_SCHEMA,
        max_tokens=4096,
    )
    if not out:
        return []
    res: list[ClinicalAssertion] = []
    for a in out.get("assertions", []):
        if not a.get("verbatim_span") or a.get("kind") not in ASSERTION_KINDS:
            continue
        res.append(
            ClinicalAssertion(
                kind=a["kind"],
                drug=a.get("drug"),
                dose=a.get("dose"),
                condition=a.get("condition"),
                symptom=a.get("symptom"),
                verbatim_span=a["verbatim_span"].strip(),
                speaker=a.get("speaker"),
                source="llm",
            )
        )
    return res


def _chart_assertions(state: PatientState) -> list[ClinicalAssertion]:
    """Deterministic backbone: every active med is a prescribe/continue assertion so
    the chart-vs-chart checks have something to route on without the LLM."""
    out: list[ClinicalAssertion] = []
    for m in state.active_meds():
        out.append(
            ClinicalAssertion(
                kind="continue" if m.source == "home" else "prescribe",
                drug=m.name,
                dose=m.dose,
                verbatim_span=f"[chart] {m.name} ({m.source})",
                speaker=m.prescriber.name,
                source="chart",
            )
        )
    return out


def extract_assertions(state: PatientState, transcript: str, note: str) -> list[ClinicalAssertion]:
    """Chart-derived assertions always; LLM-mined transcript assertions when available."""
    assertions = _chart_assertions(state)
    if llm.available() and (transcript or note):
        assertions.extend(_llm_assertions(transcript, note))
    return assertions
