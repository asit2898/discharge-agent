"""Stage 5 — Self-Verifier (Claude, adversarial).

For each candidate Flag, a separate call is asked to REFUTE it: given both pieces of
evidence, is this a real, clinically-actionable discharge problem, or a false positive?
Default to refute when uncertain. This is the alert-fatigue killer — it prunes the
over-generated candidates (e.g. a "dropped" home med that is actually being continued).

No LLM key → verification is skipped and every candidate passes through unverified
(the deterministic engine still stands on its own).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from . import llm
from .schemas import Flag


@dataclass
class Verdict:
    keep: bool
    confidence: float
    reason: str
    verified: bool          # True if the LLM actually ran; False = pass-through


_SCHEMA = {
    "type": "object",
    "properties": {
        "is_real": {"type": "boolean",
                    "description": "true only if this is a real, clinically-actionable discharge safety issue"},
        "confidence": {"type": "number",
                       "description": "0.0–1.0 confidence in YOUR verdict (how sure you are of is_real, either way)"},
        "reason": {"type": "string", "description": "one sentence justifying keep or refute"},
    },
    "required": ["is_real", "confidence", "reason"],
}

_SYSTEM = """You are a skeptical attending pharmacist reviewing an automated discharge \
safety flag before it reaches the physician. Your job is to REFUTE weak flags so the \
physician is not spammed. A flag is REAL only if it is clinically actionable at THIS \
discharge given the evidence shown. Common false positives to refute: a home med that is \
actually being continued elsewhere on the list; a duplicate that is a legitimate \
titration; an interaction that is standard, monitored co-therapy. When genuinely \
uncertain, refute. Be decisive."""


def _verify_one(flag: Flag) -> Verdict:
    ev = []
    if flag.transcript_evidence:
        ev.append(f'Conversation: "{flag.transcript_evidence}" — {flag.transcript_speaker or "unknown"}')
    if flag.chart_evidence:
        ev.append(f"Chart: {flag.chart_evidence.resource_type} — {flag.chart_evidence.display}")
    user = (
        f"FLAG TYPE: {flag.type}\nSEVERITY: {flag.severity}\nMED: {flag.med_name}\n"
        f"EXPLANATION: {flag.explanation}\nEVIDENCE:\n  " + "\n  ".join(ev or ["(none)"]) +
        f"\nPROPOSED FIX: {flag.suggested_fix}\n\nIs this a real, actionable discharge safety issue?"
    )
    out = llm.call_structured(
        model=llm.VERIFY_MODEL,
        system=_SYSTEM,
        user=user,
        tool_name="verdict",
        tool_description="Record whether the flag is a real, actionable safety issue.",
        schema=_SCHEMA,
        max_tokens=512,
    )
    if not out:
        return Verdict(keep=True, confidence=0.5, reason="verifier unavailable", verified=False)
    return Verdict(
        keep=bool(out.get("is_real")),
        confidence=float(out.get("confidence", 0.5)),
        reason=str(out.get("reason", "")),
        verified=True,
    )


def verify(flags: list[Flag]) -> list[tuple[Flag, Verdict]]:
    """Return (flag, verdict) for every candidate. Caller decides what to drop.

    Candidates are verified in parallel (independent refute calls) to keep latency
    bounded — the loop's wall-clock is one call, not N."""
    if not llm.available():
        return [(f, Verdict(keep=True, confidence=0.5, reason="verifier offline", verified=False)) for f in flags]
    if not flags:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(flags))) as pool:
        verdicts = list(pool.map(_verify_one, flags))
    return list(zip(flags, verdicts))
