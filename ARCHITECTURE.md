# Architecture — how the agent works

> Companion to [`PROJECT.md`](./PROJECT.md). `PROJECT.md` is the pitch and the
> plain-terms **logic**; this is the **build spec** — the same idea turned into concrete
> steps: what the model decides, what stays plain code, and what each tool hands back.

## The whole thing at a glance

The core idea: **hand the model the chart + the conversation and a set of grounded
safety tools, and let it drive** — decide which checks fit this patient, investigate the
ambiguous ones against the record, keep what's real, and draft the order action. The
loop is the model's; the *tools* are plain, auditable code.

```
                                   INPUTS · 4 sources
   ┌──────────────────┬──────────────────┬──────────────────┬──────────────────┐
   │  home med list   │  hospital orders │    transcript    │   signed note    │
   └────────┬─────────┴────────┬─────────┴────────┬─────────┴────────┬─────────┘
            └──────────  Chart Compiler (plain code, no LLM)  ────────┘        STEP 0
                                      ▼
                    ┌───────────────────────────────────┐
                    │  PatientState — meds · labs ·       │   the grounded substrate
                    │  allergies · problems · assertions  │   every tool reads
                    └──────────────────┬──────────────────┘
                                       ▼
   ╔═══════════════════════════════════════════════════════════════════════════╗
   ║  ◆ ORCHESTRATOR AGENT — Claude in a tool-use loop, deciding each step        ║
   ║                                                                             ║
   ║    plan ──▶ run_safety_check(…) ──▶ investigate ──▶ confirm / dismiss ──▶    ║
   ║      ▲          (grounded KB check)   (labs, problems,   (draft the order    ║
   ║      └──────────── loop ─────────────  transcript search)  action)          ║
   ║                                                          └──▶ finish         ║
   ╚═══════════════════════════════════════════════════════════════════════════╝
                                       ▼                                    STEP N
                ┌───────────────────────────────────────────┐   plain code
                │  ASSEMBLE + RANK   (one card per issue)      │
                └──────────────────────┬──────────────────────┘
                                       ▼
        draft list  (the quiet ~90%)   +   confirmed issues  (each with a drafted
                                            action + a receipt + a reasoning trace)


   ◆ = the model drives here · the Chart Compiler, the tools, and assemble/rank are plain code
```

Read top to bottom: four sources → one grounded `PatientState` → the agent loops over
its tools, deciding what to check and investigate → confirmed issues get a drafted action
→ ranked and handed back, with the whole loop captured as an inspectable trace.

## One design choice up front: an agent, with grounded tools

Per Anthropic's [Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents):
an **agent** lets the model decide its own next move in a loop; a **workflow** runs the
model through fixed, known steps. This is an **agent** — the model owns the control flow:
which checks to run, what to investigate, what to keep, what action to draft, and when
it's done. On a simple patient it may take a handful of steps; on a complex
multi-specialist discharge it investigates one drug across several tools.

The subtlety that keeps a clinical safety-catch trustworthy is that **detection stays
grounded**. The agent cannot invent a flag out of thin air — it can only *confirm* a
candidate that a deterministic, KB-backed check actually surfaced, and every confirmed
issue keeps its both-sided evidence and the exact FHIR resource id. So we get agency
(the model plans, investigates, and acts) **without** giving up the receipt (a flag still
traces to a rule in `checks.py` + a resource in the chart). That's the hybrid: a
model-driven loop over auditable tools.

---

## Step 0 · Chart Compiler — build the grounded substrate (no LLM)

Before the agent runs, plain code (`patient_state.py`) parses the FHIR
`related_resources` + `patient_context` into a normalized `PatientState`: the med lines
(home / inpatient / discharge / transcript, each source-tagged and prescriber-attributed),
the safety-relevant labs (eGFR, K, INR, A1c), the allergies with their cross-reactivity
classes, the active problem list, and a pregnancy flag. This is cheap, reliable, and never
hallucinates — it's the structured ground truth every tool reads. The transcript/note
assertions (what was *said*, with a verbatim span) are extracted once here too, so the
transcript-driven checks have something to route on.

> **Absence is data.** A drug on the home list with *no* discharge row is exactly the
> "accidentally dropped" case — which is why every source is a tagged lane on the same med.

---

## The agent's tools

The model is handed nine tools and chooses among them. Three families:

**Read the chart** (grounded facts, no decisions):
- `get_medication_table` — every med line with dose, status, source, prescriber, and
  whether it's on the discharge order set. The agent starts here.
- `get_labs` · `get_problem_list` · `get_allergies` — the rest of the `PatientState`.

**Investigate** (ground or refute a candidate):
- `search_transcript` — search the transcript **and** the signed note for a term (a drug
  name) to find what was actually said and by whom. This is how the agent grounds a
  cross-prescriber conflict or refutes a false positive before deciding.

**Run a grounded safety check** — the detection backbone:
- `run_safety_check(check)` — run **one** KB-backed check from the menu and get back
  candidate issues, each with a `candidate_id` and both-sided evidence. The menu is the
  eleven checks in `checks.py`: drug–allergy, renal dose, drug–drug interaction, duplicate
  therapy, dropped home med, teratogen-in-pregnancy, cross-prescriber anticoagulant,
  adverse drug event, denied history, discontinued-but-active, mentioned-not-recorded.
  The agent picks which ones fit the patient.

**Decide + act** (the "take action" clause):
- `confirm_issue(candidate_id, disposition, action, rationale)` — confirm a candidate as
  real and **draft the concrete order edit** a clinician should take (continue / modify /
  discontinue). Guarded: you can only confirm a `candidate_id` a check actually surfaced.
- `dismiss_issue(candidate_id, reason)` — kill a false positive (the alert-fatigue
  control), with the reason recorded.
- `finish(summary)` — end the loop when every relevant check has run and every candidate
  is either confirmed-with-an-action or dismissed.

Each tool call is recorded as a step in the trace, so the loop is fully inspectable.

---

## The loop the agent runs (a real trace, hero patient)

Given the system prompt below, Claude drives roughly this — **deciding each step**, not
following a script:

```
💭 "I'll start by getting the full medication picture."
 ▸ get_medication_table          → 17 med lines across home/inpatient/discharge/transcript
💭 "Let me gather clinical context before running checks."
 ▸ get_labs                       → k=5.8, egfr=24, a1c=7.8
 ▸ get_problem_list · get_allergies → 16 problems · Penicillin
💭 "High-risk: eGFR 24 (AKI on CKD), K 5.8, penicillin allergy, AF, multiple prescribers."
 ▸ run_safety_check drug_allergy / renal_dose / cross_prescriber / interaction / …
💭 "Investigate the ones needing transcript grounding."
 ▸ search_transcript "enoxaparin" → Dr. Patel (Cardiology): "we can stop the Lovenox…"
💭 "Cardiology directed stopping it, but Ortho ordered it — different teams. Surface it,
    don't auto-resolve."
 ▸ confirm_issue enoxaparin → discontinue, action="…cross-prescriber; both services confirm"
 ▸ dismiss_issue <weak candidate> → reason="documented titration, not a duplicate"
 …
 ▸ finish "10 issues confirmed with drafted actions; candidates dismissed as false positives"
```

The agent chose which six checks to run (not all eleven), searched the transcript for the
drugs that mattered, applied the authority rule on the cross-prescriber conflict, and
pruned the candidate set down to the confirmed queue — each with a drafted action.

---

## The rules the agent works under (in its system prompt)

**Authority — signed beats spoken, but only within one prescriber.** The signed
order/note outranks a spoken remark *only* when it's the same clinician reconsidering
their own words (surgeon says "hold the Plavix" in the room, then signs "resume" — the
signed line wins, the spoken line becomes the receipt). Across **different** prescribers,
a spoken directive is **not** overridden by another team's signed order — the agent
surfaces the conflict with both sides and does not pick a winner. This is exactly the
multi-specialist hero case (surgery / hospitalist / cardiology / ID), and it's why every
med line carries *who* ordered it.

**Grounding — no invented flags, no invented quotes.** The agent can only confirm a
candidate a check surfaced, and the evidence (the transcript span, the chart resource id)
is passed in on the candidate, not re-found — it *cites*, it can't fabricate.

**Precision — a quiet queue beats a noisy one.** The agent is told to dismiss weak,
low-confidence candidates (alert fatigue is the failure mode we design against), while
erring toward *surfacing* high-severity safety issues. This is the agent's version of the
old self-verifier: refutation happens inside the loop, as a decision, not as a separate
pass.

**It never signs.** Every confirmed issue is a *drafted* action pended for a licensed
human. Decision support, not decision replacement.

---

## Assemble + rank — the thing the screen shows (no LLM)

Plain code (`engine.py`) turns the agent's confirmed issues into the `Reconciliation` the
UI renders: the draft med list (everything that agreed, pre-filled) plus the confirmed
queue, ranked by severity. Each card carries the drafted `agent_action`, the disposition,
the rationale, and the both-sided receipt. The full `trace` rides along so the loop is
visible in the UI (the `AgentTrace` panel) — the "agentic" receipt for a judge.

```
   final output (Reconciliation)
   ├─ draft_meds   ← agreements, pre-filled            (the quiet ~90%)
   ├─ flags        ← confirmed issues, ranked, each with a drafted action + receipt
   └─ trace        ← the agent's step-by-step loop     (inspectable)
```

Nothing applies itself. **The agent lines it up, drafts the action, and shows its work;
the human decides.**

---

## Fallback — the deterministic workflow

When no `ANTHROPIC_API_KEY` is present (offline, or eval), `engine.py` runs the original
deterministic pipeline instead: extract chart-derived assertions → run all eleven checks →
adversarial self-verify (pass-through offline) → dedup → rank. Same output shape, same
grounding, no model. Set `DISCHARGE_AGENTIC=0` to force this path even with a key (used by
the offline eval harness so scoring is deterministic). The engine reports which mode
produced a result via `Reconciliation.mode` (`"agent"` | `"workflow"`).

---

## Stack (hackathon)

**Hand-rolled, calling Claude directly — no heavy agent framework.** The loop is a small,
readable tool-use driver (`llm.run_tool_loop`), and every judge question is "how does it
decide?" — hand-rolled keeps that answer visible.

- **Python backend**, **Anthropic Messages API** — `run_tool_loop` drives the multi-turn
  tool-use loop; the model chooses tools, Python executes them and feeds results back.
- **The tools are plain code** — the Chart Compiler, the eleven KB-backed checks
  (`checks.py`), the transcript search, assemble/rank — all testable with no model, and
  all reusable by the deterministic fallback.
- **Pydantic** for the shapes crossing the API boundary (`Med`, `Flag`, `AgentEvent`,
  `Reconciliation`) — also the eval schema.
- UI: a small React page hitting a FastAPI endpoint that returns the `Reconciliation`,
  including the agent trace it renders in the `AgentTrace` panel.
