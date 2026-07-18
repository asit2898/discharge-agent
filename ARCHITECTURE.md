# Architecture — how the agent actually works

> Companion to [`PROJECT.md`](./PROJECT.md) (the pitch). This is the engineering
> shape: what's an agent, what's a deterministic tool, and where Claude reasons.

## Is this even "agentic," or just a diff?

Be honest about it. A naive med-rec is a `set` diff across three lists. If that
were the whole job you would not need an LLM. Three things make it hard enough to
need a reasoning agent — and those three are exactly the demo:

1. **Entity resolution across sources.** `metoprolol tartrate 25 MG Oral Tablet`
   (home med) vs. *"we swapped your metoprolol to the once-a-day version"*
   (transcript) vs. `metoprolol succinate ER 50 MG` (inpatient order) are the
   same *ingredient* but a deliberate *formulation change* — not a duplicate to
   auto-merge, not two unrelated drugs. Fuzzy, judgment-laden matching.
2. **Intent extraction from conversation.** The transcript is where a stop/hold
   decision is *spoken* before it's ever *ordered*. Pulling
   `{drug, action, reason, prescriber, quote}` out of free dialogue is an LLM job.
3. **Disagreement classification with an authority rule.** Given the resolved
   entities, decide *agreement / omission / dose-conflict / discontinued-but-listed
   / duplicate / orphaned-course* — and when sources conflict, default the
   suggested resolution to the **note/order over the transcript** (the transcript
   only earns the flag; it never wins the decision).

So: **a structured pipeline whose hard steps are LLM-powered, wrapped in a
per-medication reasoning loop that must cite its evidence.** The "surface the
disagreements" output *is* the agent's audit trail — every flag is explainable
because the agent was forced to cite the source line that produced it.

## The shape: orchestrator + tools + a per-med loop

```
                         ┌─────────────────────────────┐
   FHIR bundle  ─────────▶                             │
   transcript   ─────────▶   Orchestrator (Claude)     │
   note / AVS   ─────────▶   - decides what to pull     │
                         │   - runs the per-med loop    │
                         └──────────┬──────────────────┘
                                    │ tool calls
                 ┌──────────────────┼───────────────────────┐
                 ▼                  ▼                        ▼
      ┌───────────────┐  ┌────────────────────┐  ┌────────────────────┐
      │  FHIR tools   │  │ Transcript retrieval│  │  Normalizer        │
      │ get_home_meds │  │ search_transcript() │  │  resolve_med(text) │
      │ get_inpatient │  │ get_note_section()  │  │  → RxNorm ingr +   │
      │ get_discharge │  │  (higher authority) │  │    strength + form │
      └───────────────┘  └────────────────────┘  └────────────────────┘
```

### Layer 1 — deterministic tools (no LLM)
Thin, testable functions the agent calls. They read the fixture, they don't reason.
- `get_home_meds()` → outpatient/community `MedicationRequest` + `MedicationStatement`
- `get_inpatient_orders()` → inpatient `MedicationRequest`s (grouped by `requester`)
- `get_discharge_orders()` → the pending discharge order set (what Epic would pre-load)
- `search_transcript(query)` → returns transcript segments + line numbers for a drug/topic
- `get_note_section(name)` → the physician note section (the authoritative record)
- `resolve_med(free_text)` → normalized `{ingredient, strength, form, rxnorm}`

### Layer 2 — extraction pass (one LLM call, strict schema)
Read transcript + note once, emit a list of **medication intents**:
`{drug, action∈{start,stop,hold,continue,change}, reason, prescriber, quote, confidence}`.
This is the "listen to the conversation" step — the thing only Abridge-style
ambient data makes possible.

### Layer 3 — reconciliation engine (deterministic core + LLM tie-breaks)
Build one **row per medication** across four columns:
`home | inpatient | discharge-order | conversation-intent`.
After normalization the matching is mostly deterministic; Claude is called only to
break fuzzy ties (is this a duplicate or a deliberate formulation switch?). Each row
gets a `status` and, on conflict, a `disagreement_type`.

### Layer 4 — reviewer / evidence pass (per flagged row, LLM)
For every disagreement: apply the authority rule, draft the **recommended
resolution**, write the **patient-friendly "why this changed" line**, and attach the
evidence (transcript quote + prescriber + the order it conflicts with).
**Precision-first:** suppress low-confidence flags — alert fatigue is the failure mode.

### Output
`{ draft_reconciled_list, disagreements[] }` — the pre-populated draft plus a ranked,
evidence-cited disagreement list. Nothing auto-applies; the clinician decides.

## Stack recommendation (hackathon)

**Hand-rolled orchestration calling Claude with tool-use — no heavy agent framework.**
- Python backend, **Anthropic Messages API with `tools`** (the tool-use loop).
- **Pydantic** typed state object threaded through the layers (also our eval schema).
- Skip LangGraph/CrewAI: the control flow is a map-over-medications, not a graph that
  benefits from a framework. Legibility > machinery for a demo.
- UI later: React SPA hitting a small FastAPI endpoint that returns the output object.

Why hand-rolled: every judge question is "how does it decide?" — a hand-rolled
tool-use loop makes the evidence chain inspectable. A framework hides it.

## Why this is defensibly "agentic"
- The orchestrator **chooses** which sources to pull and **when it has enough** to
  rule on a drug (not a fixed script).
- Each medication is a small **reason → act (call tool) → observe → verdict** loop.
- Every verdict carries a **tool-cited justification** — the audit trail is the product.
