"""Reconciliation engine — STUB.

Contract: `reconcile(record_id) -> Reconciliation`. Today it routes the hero case to a
hand-authored, grounded reconciliation and returns a normalized (flag-free) draft for
the real 25 encounters. Tomorrow the neuro-symbolic safety-catch loop (docs/engine.md:
Chart Compiler -> Assertion Extractor -> Catch Engine -> Grounder -> Self-Verifier ->
Rank/Act) drops in behind this same function signature — the frontend never changes.
"""
from __future__ import annotations

from typing import Optional

from . import hero
from .loader import get_record
from .normalize import normalize_meds
from .schemas import Reconciliation, ReconStats

# Rank order for the "needs a decision" queue: severity, then high-risk types first.
_SEVERITY_RANK = {"high": 0, "moderate": 1, "low": 2}


def reconcile(record_id: str) -> Optional[Reconciliation]:
    if record_id == hero.HERO_ID:
        recon = hero.hero_reconciliation()
        recon.flags.sort(key=lambda f: _SEVERITY_RANK.get(f.severity, 9))
        return recon

    record = get_record(record_id)
    if record is None:
        return None

    meds = normalize_meds(record)
    # Stub: real detection not yet wired for the provided encounters. Present the
    # pre-populated draft honestly, with an empty queue rather than fabricated flags.
    return Reconciliation(
        encounter_id=record_id,
        draft_meds=meds,
        flags=[],
        stats=ReconStats(
            total_meds=len(meds),
            agree_count=len(meds),
            flag_count=0,
            high_severity_count=0,
        ),
    )
