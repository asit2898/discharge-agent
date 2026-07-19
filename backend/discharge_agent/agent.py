"""The orchestrator agent — the *agentic* front for the reconciliation engine.

Where `engine._reconcile_workflow` runs a fixed pipeline, this drives a real
model-in-the-loop: Claude plans, decides which grounded safety checks to run,
investigates the chart/transcript when a candidate is ambiguous, self-verifies to
kill false positives, and drafts the order action for each confirmed issue. The model
owns the control flow; Python only owns the *tools*.

The hybrid is deliberate. Detection stays **grounded**: the agent cannot invent a
flag — it can only confirm a candidate that a deterministic, KB-backed check
(`checks.py`) actually surfaced, and every confirmed flag keeps its both-sided
evidence + FHIR resource id. What the agent adds is agency: which checks to run, what
to investigate, what to keep, and the drafted action ("take action"). The whole loop
is captured as an inspectable trace.

Falls back to None when the LLM is unavailable so the caller can run the workflow.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from . import checks, kb, llm
from .assertions import extract_assertions
from .patient_state import PatientState
from .schemas import AgentEvent, Flag

# The grounded checks, exposed to the agent as a menu it chooses from. Each is a pure
# function (state, assertions) -> list[Flag]; the agent decides which are worth running.
CHECK_MENU: dict[str, Callable] = {
    "drug_allergy": checks.check_drug_allergy,
    "renal_dose": checks.check_renal_dose,
    "drug_interaction": checks.check_drug_drug,
    "duplicate_therapy": checks.check_duplicate,
    "dropped_home_med": checks.check_dropped_home_med,
    "teratogen_in_pregnancy": checks.check_teratogen,
    "cross_prescriber_anticoag": checks.check_cross_prescriber,
    "adverse_drug_event": checks.check_adverse_event,
    "denied_history": checks.check_denied_history,
    "discontinued_but_active": checks.check_discontinued_but_active,
    "mentioned_not_recorded": checks.check_mentioned_not_recorded,
}

_DISPOSITION_VERB = {"continue": "Continue", "modify": "Modify", "discontinue": "Discontinue"}
_SEVERITY_RANK = {"high": 0, "moderate": 1, "low": 2}


@dataclass
class _Session:
    """Mutable state threaded through the tool dispatch closure."""
    state: PatientState
    transcript: str
    note: str
    assertions: list = field(default_factory=list)
    candidates: dict[str, Flag] = field(default_factory=dict)   # candidate_id -> Flag
    confirmed: list[Flag] = field(default_factory=list)
    dismissed: set[str] = field(default_factory=set)

    def register(self, flag: Flag) -> str:
        """Give a check's candidate a stable id and remember it (idempotent by flag.id)."""
        cid = flag.id
        self.candidates.setdefault(cid, flag)
        return cid


# ---- tool implementations ----------------------------------------------------

def _med_row(m) -> dict[str, Any]:
    return {
        "id": m.id,
        "name": m.name,
        "dose": m.dose,
        "route": m.route,
        "frequency": m.frequency,
        "status": m.status or "active",
        "source": m.source,               # home | inpatient | discharge | transcript
        "on_discharge": m.on_discharge,
        "prescriber": m.prescriber.name,
    }


def _tool_get_medication_table(s: _Session, _args) -> dict[str, Any]:
    rows = [_med_row(m) for m in s.state.meds]
    return {"content": {"medications": rows, "count": len(rows)},
            "summary": f"{len(rows)} med lines across home/inpatient/discharge/transcript"}


def _tool_get_labs(s: _Session, _args) -> dict[str, Any]:
    labs = {k: {"value": lb.value, "unit": lb.unit, "display": lb.display} for k, lb in s.state.labs.items()}
    return {"content": {"labs": labs} if labs else {"labs": {}, "note": "no safety-relevant labs charted"},
            "summary": ", ".join(f"{k}={v['value']}" for k, v in labs.items()) or "no labs"}


def _tool_get_problem_list(s: _Session, _args) -> dict[str, Any]:
    return {"content": {"problems": s.state.problems, "pregnant": s.state.pregnant},
            "summary": f"{len(s.state.problems)} active problems"}


def _tool_get_allergies(s: _Session, _args) -> dict[str, Any]:
    al = [{"label": a.label, "cross_reactive_classes": sorted(a.classes)} for a in s.state.allergies]
    return {"content": {"allergies": al}, "summary": ", ".join(a["label"] for a in al) or "no charted allergies"}


def _tool_search_transcript(s: _Session, args) -> dict[str, Any]:
    query = (args.get("query") or "").strip().lower()
    if not query:
        return {"content": {"error": "query is required"}, "summary": "empty query"}
    hits: list[str] = []
    haystack = f"{s.transcript}\n{s.note}"
    for line in haystack.splitlines():
        if query in line.lower():
            hits.append(line.strip())
    hits = hits[:8]
    return {"content": {"query": query, "matches": hits},
            "summary": f'{len(hits)} line(s) mention "{query}"'}


def _tool_run_safety_check(s: _Session, args) -> dict[str, Any]:
    name = args.get("check")
    fn = CHECK_MENU.get(name)
    if fn is None:
        return {"content": {"error": f"unknown check '{name}'", "available": sorted(CHECK_MENU)},
                "summary": f"unknown check '{name}'"}
    found = fn(s.state, s.assertions)
    out = []
    for f in found:
        cid = s.register(f)
        out.append({
            "candidate_id": cid,
            "type": f.type,
            "severity": f.severity,
            "med": f.med_name,
            "explanation": f.explanation,
            "chart_evidence": f.chart_evidence.display if f.chart_evidence else None,
            "transcript_evidence": f.transcript_evidence,
            "transcript_speaker": f.transcript_speaker,
            "default_resolution": f.recommended_resolution,
        })
    return {"content": {"check": name, "candidates": out, "count": len(out)},
            "summary": f"{name}: {len(out)} candidate(s)"}


def _tool_confirm_issue(s: _Session, args) -> dict[str, Any]:
    cid = args.get("candidate_id")
    flag = s.candidates.get(cid)
    if flag is None:
        return {"content": {"error": f"no candidate '{cid}' — run the safety check that surfaces it first"},
                "summary": f"reject: unknown candidate '{cid}'"}
    if cid in s.dismissed:
        return {"content": {"error": f"candidate '{cid}' was already dismissed"}, "summary": "already dismissed"}
    disp = args.get("disposition")
    if disp not in _DISPOSITION_VERB:
        return {"content": {"error": "disposition must be continue|modify|discontinue"},
                "summary": "bad disposition"}
    action = (args.get("action") or "").strip()
    rationale = (args.get("rationale") or "").strip()
    if not action:
        return {"content": {"error": "action (the drafted order edit) is required"}, "summary": "missing action"}

    # Grounding is preserved: we adjudicate the check's candidate, never fabricate a flag.
    flag.agent_disposition = disp
    flag.agent_action = action
    flag.agent_rationale = rationale
    # Reflect the agent's decision in the fields the UI already renders, so the shown
    # resolution + disposition color track the agent (leading verb drives proposedDisp).
    flag.recommended_resolution = f"{_DISPOSITION_VERB[disp]}: {action}"
    if rationale:
        flag.suggested_fix = rationale
    if flag not in s.confirmed:
        s.confirmed.append(flag)
    return {"content": {"confirmed": cid, "disposition": disp, "queued": len(s.confirmed)},
            "summary": f"confirm {flag.med_name or flag.type} → {disp}"}


def _tool_dismiss_issue(s: _Session, args) -> dict[str, Any]:
    cid = args.get("candidate_id")
    if cid not in s.candidates:
        return {"content": {"error": f"no candidate '{cid}'"}, "summary": f"unknown candidate '{cid}'"}
    s.dismissed.add(cid)
    s.confirmed = [f for f in s.confirmed if f.id != cid]
    return {"content": {"dismissed": cid, "reason": args.get("reason", "")},
            "summary": f"dismiss {cid}: {args.get('reason', '')[:80]}"}


def _tool_finish(s: _Session, args) -> dict[str, Any]:
    return {"content": {"done": True, "confirmed": len(s.confirmed), "dismissed": len(s.dismissed)},
            "summary": args.get("summary", "done"), "stop": True}


_TOOL_IMPL: dict[str, Callable] = {
    "get_medication_table": _tool_get_medication_table,
    "get_labs": _tool_get_labs,
    "get_problem_list": _tool_get_problem_list,
    "get_allergies": _tool_get_allergies,
    "search_transcript": _tool_search_transcript,
    "run_safety_check": _tool_run_safety_check,
    "confirm_issue": _tool_confirm_issue,
    "dismiss_issue": _tool_dismiss_issue,
    "finish": _tool_finish,
}


# ---- tool schemas (the menu handed to the model) -----------------------------

def _tools_spec() -> list[dict[str, Any]]:
    return [
        {"name": "get_medication_table", "description":
         "List every medication line across all sources (home, inpatient, discharge, transcript) "
         "with dose, status, source, prescriber, and whether it is on the discharge order set. "
         "Start here to see the picture.",
         "input_schema": {"type": "object", "properties": {}}},
        {"name": "get_labs", "description":
         "Safety-relevant labs (eGFR, potassium, INR, A1c). Use to judge renal dosing or monitoring.",
         "input_schema": {"type": "object", "properties": {}}},
        {"name": "get_problem_list", "description":
         "Active problem list + pregnancy flag. Use to judge drug–condition conflicts.",
         "input_schema": {"type": "object", "properties": {}}},
        {"name": "get_allergies", "description":
         "Charted allergies with their cross-reactive drug classes.",
         "input_schema": {"type": "object", "properties": {}}},
        {"name": "search_transcript", "description":
         "Search the visit transcript AND signed note for a term (e.g. a drug name) to find what "
         "was actually said and by whom. Use to ground or refute a candidate before deciding.",
         "input_schema": {"type": "object",
                          "properties": {"query": {"type": "string", "description": "term to search for"}},
                          "required": ["query"]}},
        {"name": "run_safety_check", "description":
         "Run one grounded, KB-backed safety check over the chart. Returns candidate issues, each "
         "with a candidate_id and both-sided evidence. You may only confirm issues that a check "
         "surfaced — this keeps every flag traceable. Choose the checks that fit this patient.",
         "input_schema": {"type": "object",
                          "properties": {"check": {"type": "string", "enum": sorted(CHECK_MENU),
                                                   "description": "which safety check to run"}},
                          "required": ["check"]}},
        {"name": "confirm_issue", "description":
         "Confirm a candidate as a real, clinically-actionable discharge safety issue and draft the "
         "order action a clinician should take. Only confirm what survives your scrutiny. Authority "
         "rule: the signed order/note beats a spoken remark ONLY within the same prescriber; across "
         "different prescribers, do not pick a winner — surface it and say so.",
         "input_schema": {"type": "object",
                          "properties": {
                              "candidate_id": {"type": "string"},
                              "disposition": {"type": "string", "enum": ["continue", "modify", "discontinue"],
                                              "description": "the order change you are proposing"},
                              "action": {"type": "string",
                                         "description": "the concrete drafted order edit for the clinician, "
                                                        "e.g. 'Discontinue cefdinir — 7-day course complete'"},
                              "rationale": {"type": "string",
                                            "description": "one line: why this is real after investigating"}},
                          "required": ["candidate_id", "disposition", "action", "rationale"]}},
        {"name": "dismiss_issue", "description":
         "Dismiss a candidate as a false positive (alert-fatigue control). Give the reason.",
         "input_schema": {"type": "object",
                          "properties": {"candidate_id": {"type": "string"},
                                         "reason": {"type": "string"}},
                          "required": ["candidate_id", "reason"]}},
        {"name": "finish", "description":
         "Call when the reconciliation is complete: all relevant checks run, every candidate either "
         "confirmed with an action or dismissed. Give a one-line summary.",
         "input_schema": {"type": "object",
                          "properties": {"summary": {"type": "string"}}}},
    ]


_SYSTEM = """You are a discharge medication-reconciliation safety agent — the second set \
of eyes a patient gets when no pharmacist is in the room. You investigate the chart and \
the visit conversation, surface where the sources disagree, and draft the order action a \
clinician should take. You never sign; a licensed human decides. Decision support, not \
decision replacement.

HOW TO WORK — you drive the loop, using the tools:
1. Call get_medication_table first to see every med line and its sources.
2. Reason about which safety checks fit THIS patient, then call run_safety_check for each \
that is worth running. Don't skip high-risk ones (allergy, renal, interaction, dropped \
home med, cross-prescriber).
3. For each candidate a check surfaces, INVESTIGATE before deciding — pull labs, the \
problem list, allergies, or search_transcript to see what was actually said and by whom. \
Ground it or refute it.
4. confirm_issue for real, actionable issues (draft the concrete order edit); dismiss_issue \
for false positives. A quiet, trustworthy queue beats a noisy one — be decisive, and when \
genuinely uncertain about a weak flag, dismiss it. But err toward SURFACING high-severity \
safety issues.
5. When done, call finish.

AUTHORITY RULE. The signed order/note outranks a spoken remark ONLY within the same \
prescriber (one clinician reconsidering their own words). Across DIFFERENT prescribers, a \
spoken directive is NOT overridden by another team's signed order — surface the conflict \
with both sides, do not pick a winner. Every med row carries who ordered it.

GROUNDING. You may only confirm candidates that a safety check surfaced; you cannot invent \
a flag. Cite the evidence already attached — never fabricate a quote."""


def run_agent(record_id: str, state: PatientState, transcript: str, note: str) -> Optional[tuple[list[Flag], list[AgentEvent]]]:
    """Run the orchestrator loop. Returns (confirmed_flags, trace) or None if no LLM."""
    if not llm.available():
        return None

    session = _Session(state=state, transcript=transcript, note=note)
    # Candidates for the transcript-driven checks need the extracted assertions; the
    # chart-vs-chart checks work off state alone. Extract once, up front.
    session.assertions = extract_assertions(state, transcript, note)

    def dispatch(name: str, args: dict[str, Any]) -> dict[str, Any]:
        impl = _TOOL_IMPL.get(name)
        if impl is None:
            return {"content": {"error": f"unknown tool '{name}'"}, "summary": f"unknown tool '{name}'"}
        return impl(session, args)

    user = (
        f"Reconcile the discharge medications for encounter {record_id}. "
        "Work through the tools step by step, then finish."
    )
    raw_trace = llm.run_tool_loop(
        model=llm.ORCHESTRATOR_MODEL,
        system=_SYSTEM,
        user=user,
        tools=_tools_spec(),
        dispatch=dispatch,
        max_iters=28,
    )
    if raw_trace is None:
        return None

    flags = list(session.confirmed)
    flags.sort(key=lambda f: _SEVERITY_RANK.get(f.severity, 9))
    trace = [AgentEvent(**ev) for ev in raw_trace]
    return flags, trace
