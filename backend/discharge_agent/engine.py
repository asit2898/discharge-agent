"""Reconciliation engine — the neuro-symbolic safety-catch loop.

`reconcile(record_id) -> Reconciliation`. The flags are DERIVED, not read from any
answer key. The loop (docs/engine.md):

  1. Chart Compiler   (deterministic)  -> PatientState: meds, allergies, problems, labs
  2. Assertion Extractor (Claude)      -> typed assertions from transcript + note
  3. Catch Engine     (deterministic)  -> route assertions/state to KB-backed checks
  4. Grounder                          -> Flag with both-sided evidence + drafted fix
  5. Self-Verifier    (Claude, refute) -> prune false positives
  6. Rank by severity + return

Stages 2 and 5 (Claude) activate when ANTHROPIC_API_KEY is present; without it the
deterministic chart-vs-chart checks still run and return grounded flags. Nothing here
reads data/*labels*.json — those exist only for the offline eval harness.
"""
from __future__ import annotations

import os
from typing import Optional

from . import agent, checks, kb, llm, verifier
from .assertions import extract_assertions
from .loader import get_record
from .patient_state import PatientState
from .patient_state import compile_state
from .schemas import AgentEvent, Flag, Reconciliation, ReconStats

# Rank order for the "needs a decision" queue: severity, then high-risk types first.
_SEVERITY_RANK = {"high": 0, "moderate": 1, "low": 2}

# A refuted candidate is only dropped if the verifier is at least this confident in the
# refutation. Asymmetric by severity: high-severity safety flags are HARD to suppress —
# we err toward surfacing them for the physician. This is a safety stance, not label-tuning.
_DROP_THRESHOLD = {"high": 0.85, "moderate": 0.60, "low": 0.50}

# Reconciliations are pure functions of static records + the KB, so cache them.
# Keyed by (record_id, llm_available, mode) so results refresh when the key comes
# online or the engine mode changes.
_RECON_CACHE: dict[tuple[str, bool, str], Reconciliation] = {}


def _agentic_enabled() -> bool:
    """Use the orchestrator agent when the LLM is live, unless explicitly disabled.
    Set DISCHARGE_AGENTIC=0 to force the deterministic workflow (e.g. for eval)."""
    return llm.available() and os.environ.get("DISCHARGE_AGENTIC", "1") != "0"


def _dedup_sig(f: Flag):
    """Signature that collapses flags describing the same underlying issue (e.g. an ADR
    that fires for both strengths of one drug, or a denial captured across two turns)."""
    dkey = kb.resolve_drug(f.med_name) or (f.med_name or "")
    if f.type == "drug_drug_interaction":
        return (f.type, f.id)  # id already encodes the unordered drug pair
    if f.type == "adverse_drug_event":
        return (f.type, dkey, (f.transcript_evidence or "")[:40])
    if f.type == "history_mismatch":
        return (f.type, f.chart_evidence.display if f.chart_evidence else "")
    return (f.type, dkey, f.chart_evidence.resource_id if f.chart_evidence else None)


def _dedup(flags: list[Flag]) -> list[Flag]:
    seen: set = set()
    out: list[Flag] = []
    for f in flags:
        sig = _dedup_sig(f)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(f)
    return out


def _detail_for(record_id: str):
    """Return (record, transcript, note) for either the hero or a dataset encounter."""
    from . import hero
    if record_id == hero.HERO_ID:
        rec = hero.hero_record()
    else:
        rec = get_record(record_id)
    if rec is None:
        return None, "", ""
    return rec, rec.get("transcript", ""), rec.get("note", "")


def _assemble(record_id: str, state: PatientState, flags: list[Flag], *,
              mode: str, trace: list[AgentEvent]) -> Reconciliation:
    """Build the Reconciliation from a set of flags — shared by both engine modes."""
    meds = state.meds
    flagged_meds = {f.chart_evidence.resource_id for f in flags
                    if f.chart_evidence and f.chart_evidence.resource_id}
    return Reconciliation(
        encounter_id=record_id,
        draft_meds=meds,
        flags=flags,
        stats=ReconStats(
            total_meds=len(meds),
            agree_count=len(meds) - len(flagged_meds),
            flag_count=len(flags),
            high_severity_count=sum(1 for f in flags if f.severity == "high"),
        ),
        mode=mode,
        trace=trace,
    )


def _workflow_flags(state: PatientState, transcript: str, note: str) -> list[Flag]:
    """The deterministic pipeline (fallback / eval path): extract → checks → verify →
    dedup → rank. Same logic as before the agent, factored out."""
    # 2. Assertion Extractor (Claude when available; chart-derived assertions always)
    assertions = extract_assertions(state, transcript, note)

    # 3 + 4. Catch Engine + Grounder -> candidate flags
    candidates = checks.run_checks(state, assertions)

    # 5. Self-Verifier — adversarial refute (pass-through when LLM offline).
    # Keep a flag unless the verifier confidently refutes it; the confidence bar to
    # suppress scales with severity so high-severity catches survive weak refutations.
    verified = verifier.verify(candidates)
    flags = []
    for f, v in verified:
        if not v.verified or v.keep:
            flags.append(f)
        elif v.confidence < _DROP_THRESHOLD.get(f.severity, 0.6):
            flags.append(f)  # refuted, but not confidently enough to suppress this severity

    # 6. Dedup near-identical findings, then rank by severity
    flags = _dedup(flags)
    flags.sort(key=lambda f: _SEVERITY_RANK.get(f.severity, 9))
    return flags


def reconcile(record_id: str) -> Optional[Reconciliation]:
    mode = "agent" if _agentic_enabled() else "workflow"
    cache_key = (record_id, llm.available(), mode)
    if cache_key in _RECON_CACHE:
        return _RECON_CACHE[cache_key]

    record, transcript, note = _detail_for(record_id)
    if record is None:
        return None

    # 1. Chart Compiler (deterministic) — shared substrate for both modes.
    state = compile_state(record)

    recon: Optional[Reconciliation] = None
    if mode == "agent":
        # The orchestrator agent drives the loop: it decides which grounded checks to
        # run, investigates, self-verifies, and drafts each action. Falls back to the
        # deterministic workflow if the loop can't run.
        result = agent.run_agent(record_id, state, transcript, note)
        if result is not None:
            flags, trace = result
            recon = _assemble(record_id, state, flags, mode="agent", trace=trace)

    if recon is None:
        flags = _workflow_flags(state, transcript, note)
        recon = _assemble(record_id, state, flags, mode="workflow", trace=[])

    _RECON_CACHE[cache_key] = recon
    return recon


def deterministic_flag_count(record_id: str) -> int:
    """Cheap, LLM-free flag count for list badges (no extractor, no verifier)."""
    record, _t, _n = _detail_for(record_id)
    if record is None:
        return 0
    state = compile_state(record)
    assertions = extract_assertions(state, "", "")  # chart-derived only; skips LLM
    return len(checks.run_checks(state, assertions))


def engine_status() -> dict:
    """Whether the LLM stages are live — surfaced via /api/health."""
    return llm.status()
