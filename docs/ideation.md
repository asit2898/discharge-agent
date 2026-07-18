# Abridge Hackathon — Idea Book

**Event:** The Future of Agentic AI in Healthcare — Abridge × Anthropic × Lightspeed
**Where/When:** Shack15, SF · Sat July 18, 2026 · build 10:30am → **submissions 5:00pm (~5 hrs)** + 1-min demo video
**Team:** Akshay + Asit (max 2)

## Prompt
Build an **agentic system** for one clinical or operational healthcare workflow that makes it faster, smarter, or safer. Ship something a clinician/patient-facing team could use Monday.

## Judging (Round 1 weights)
- **Execution 30%** — complete, polished, working, clean live demo
- **Originality 25%** — "has this been seen before?"
- **Impact 20%** — real pain, at scale
- **Technical 20%** — hard problem, real engineering depth

## Hard constraints / bans
- Must be genuinely agentic (multi-step, tool-using, self-verifying) + take action
- Public repo · new work only (built during event) · 1-min demo video
- ❌ Banned: **basic RAG**, **Streamlit**, **dashboard-as-main-feature**, **basic chatbots**, basic image analyzers

## Resources
- Abridge anonymized **encounter + FHIR** dataset (.zip on event details page)
- $100 Anthropic **Claude** API credits

---

# The Build

## ⭐ Conversation-vs-Record Discrepancy Detector `LOCKED` — 🟢🟢 highest feasibility
*Origin: Asit (A4). Both teammates independently converged on this.*

**Problem.** Care can look fine on paper while something dangerous slips through: what's *said/prescribed* in the visit contradicts the patient's *chart* — a drug the patient is allergic to, a dose wrong for their kidney function, a home med silently dropped, "patient reports no meds" while the chart shows a statin.

**Solution.** A **safety-catch agent** — the second set of eyes on every visit. It cross-references the ambient visit conversation/transcript against the structured FHIR chart, flags **contradictions**, and shows each with grounded evidence on both sides + a suggested fix.

**Approach (the agentic loop — deliberately NOT basic RAG).**
1. Parse conversation → extract clinical assertions (meds prescribed, statements, plan)
2. Parse FHIR → structured patient state
3. Per assertion, run **tool checks**: drug–allergy, drug–drug interaction, renal-dose (vs eGFR), duplicate therapy, history consistency
4. Ground each hit → cite the exact conversation line **and** the exact chart evidence
5. Self-verify → kill false positives (clinician trust)
6. Rank by severity → flag + drafted fix

**Catches:** drug–allergy conflict · dose-vs-eGFR (e.g. metformin at eGFR 24) · drug–drug interaction · dropped/duplicate med · history mismatch.

**Hackathon feasibility — highest.** Data is **fully self-contained** in Abridge's dataset (conversation **and** FHIR both provided). **Point-in-time** (one-shot analysis), nothing to fabricate, no external KB, ban-safe, clean single-beat demo.

**Discussion notes.**
- Purest instance of the **safety-catch philosophy** (catch what humans miss, not generate/automate).
- Scored highest on the rubric (~4.30/5): the only idea high on *all four* criteria with no weak spot; wins Execution because its data needs zero fabrication.
- **The merge / vision:** architect it as an extensible **"catch engine"** — the contradiction check is the flagship; additional checks plug into the same loop.
  - Point-in-time checks (cheap MVP adds, same synchronous engine): *omission*, *note-vs-transcript hallucination*.
  - Temporal checks (stretch, need a scheduler + simulated time): *dropped result*, *dropped referral (A3)*, *external exposure (#6)*.
- **MVP discipline:** build the loop + ONE check (contradiction / med-safety) rock-solid first. Add others only if ahead. **Pitch the full safety net; demo the one that works flawlessly.** Never ship 5 half-built checks.
- Fits Abridge's taste (they build clinical eval frameworks).

---

# Candidates (ordered by feasibility)

## 1. Post-Visit Companion — 🟢 high feasibility ⚠️ ban-risk
*Origin: Asit (A1 reminders/adherence + plain-language after-visit summary).*

**Problem.** Patients don't understand their after-visit plan (health literacy) and don't follow it (adherence — ~50% non-adherence in chronic disease; a $100B+ problem).

**Solution.** A patient-facing companion that delivers a **plain-language after-visit summary** + reminders/adherence support, and loops non-adherence back to the doctor.

**Approach.** Visit plan → personalized plain-language summary → reminders/nudges → flag non-adherence to the doctor.

**Hackathon feasibility.** Easy to build (generation + reminders, one-shot). ⚠️ **Ban-adjacent:** a summary/reminder bot brushes "basic chatbot, limited complexity" → risks the score even if it ships.

**Discussion notes.**
- A1 alone was too thin (killed); merging with the AVS rescued it.
- Medium originality — crowded patient-engagement space; generation + chatbot are the two weakest philosophies for this rubric.
- **vs Continuous-Care:** Post-Visit does *behavioral* work (comprehension + adherence) tied to *one visit*; Continuous-Care does *clinical* work (titration/escalation) across the *disease course*.

## 2. Trial-Protocol Adherence — 🟡 med-high feasibility
*Origin: Akshay (#4, from "hospital compliance" → "protocol requirements").*

**Problem.** A patient *enrolled* in a clinical trial must meet a strict protocol — required labs/procedures per visit window, maintained eligibility, con-med restrictions, adverse-event reporting. Coordinators track this by hand; **protocol deviations** are audited by sponsors/FDA and can invalidate data or harm patients.

**Solution.** Parse a trial protocol into structured requirements → check the patient's encounter+FHIR against them → flag deviations, missed/overdue procedures, eligibility drift, prohibited-med conflicts.

**Approach.** Protocol doc → structured requirements → check patient state → flag. Source real protocols from ClinicalTrials.gov (free). Stretch: protocol amendment → re-check affected patients (the *dynamic-rules* ingredient).

**Hackathon feasibility.** One-shot, ban-safe, patient side from FHIR. ⚠️ Blocker: modeling one complex protocol into structured rules is real work; user is research-ops (a step from front-line clinician).

**Discussion notes.**
- A safety-catch (catch protocol deviations).
- Distinct from the crowded "trial matching" prompt example everyone will build → good for Originality.
- The fresh, ownable idea that survived the whole compliance branch.

## 3. Critical Patient Transfer — 🟡 med feasibility (high ceiling / high variance)
*Origin: Akshay (#2).*

**Problem.** Moving a critically ill patient between facilities (rural ER → ICU, ED → cath lab) is high-stakes and mostly done by phone/fax under time pressure. Minutes cost lives ("time is brain/muscle"); handoff communication failure is a leading cause of sentinel events.

**Solution.** From the live encounter + FHIR, generate the **SBAR handoff + transfer packet**, with a stabilization/EMTALA check and a level-of-care recommendation.

**Approach.**
1. Ingest encounter + FHIR (vitals trend, labs, meds, interventions)
2. Reason about level of care + specialty needed
3. Checks: stabilized enough to move? missing info for a safe handoff?
4. Generate SBAR + transfer packet
5. Stretch (avoid): facility matching from a seeded directory + transport request

**Hackathon feasibility.** Buildable one-shot SBAR generator. ⚠️ **Blocker:** needs critical-care/**time-series** data likely absent from Abridge's (probably outpatient) dataset → must fabricate an ICU scenario. Avoid facility-directory/transport scope (overscope). Watch the dashboard trap; show the reasoning steps so it reads as an agent, not a doc generator.

**Discussion notes — the intricacies.** Level of care during transport (BLS/ALS/Critical-Care) · mode + flight contraindications (e.g. untreated pneumothorax) · destination capability matching (PCI/stroke/trauma/burn centers) · EMTALA/legal ("patient dumping") · stabilization gaps ("GCS 6, no secured airway → intubate first") · SBAR quality needs *trending* vitals · evolving state + repeated re-telling. Highest Impact (5) and high Originality, but Execution is the risk.

## 4. Discharge / Transitions — 🟡 med feasibility
*Origin: Akshay (#9 "discharge formalities").*

**Problem.** Discharge (hospital→home) is one of the most dangerous moments in care. Done badly → readmissions (a national penalty metric) + adverse drug events. Specific gaps: **20–30% of discharge scripts are never filled** (primary non-adherence); **orphaned test results** that return after discharge get missed (major malpractice source).

**Solution.** A discharge agent that **catches what humans miss** (not "writes the summary" — that's commodity ambient-vendor work). Pick ONE spine:
- **Closed-loop pending-results** — catch the orphaned result (most original/dramatic; but temporal)
- **Med-affordability / primary non-adherence** — catch the un-fillable script (fresh, SDOH)
- **Discharge-summary self-audit** — reconcile summary vs the record, catch omissions (Abridge eval taste)
- (+ med reconciliation: dropped home med, interaction, duplicate)

**Approach.** Encounter (+FHIR) → run the chosen safety-catch → grounded flag + drafted fix. Key insight: *generation* tasks (summary/instructions) = commodity/low-originality; the *safety-catch* spines differentiate.

**Hackathon feasibility.** Feasible only if **scoped to one point-in-time spine**. ⚠️ Blocker: needs inpatient discharge encounters (Abridge data may be outpatient); the pending-results spine is temporal (harder). Don't build all spines.

**Discussion notes.** Full menu spans generate / reconcile / catch / orchestrate. The **"formalities"** (paperwork/logistics) framing is the *weak* half — back-office, efficiency-not-lives — unless built as an **autonomous executor** (does the paperwork in parallel, frees beds → hospital-throughput impact story). Absorbs Asit's AVS + med-rec. Best Abridge-fit (summary generation is near their product), but that also caps originality if you lean on generation.

## 5. Voice Prescreen Agent — 🟡 med feasibility ⚠️ demo-risk
*Origin: Akshay (#1 adaptive intake) + Asit (voice prescreen), merged.*

**Problem.** Intake is redundant and dumb — patients re-key info the system already has; static forms ask everyone everything; clinicians get incomplete histories.

**Solution.** The patient/nurse *talks* to an agent before the visit. It's **prefilled from the FHIR record** (already knows meds/history), asks only smart **adaptive** follow-ups by voice, and hands the doctor a structured **HPI + triage flag**.

**Approach — one agent, three layers.**
- **Phase 0 — Prefill (memory):** load FHIR + past encounters → "known context" + a "don't ask, already known" list.
- **Phase 1 — Voice loop (ears/mouth):** patient speaks (STT) → Claude (known context + convo + reason) decides the next question or "enough" → speaks it (TTS) → loop. Also checks answers against the record live (a mini discrepancy detection — e.g. "no meds" vs a charted statin).
- **Phase 2 — Handoff:** structured HPI + triage flag → doctor.
- **Stack:** browser Web Speech API (STT) + SpeechSynthesis (TTS) — free, keeps credits on reasoning; Claude is the brain.

**Hackathon feasibility.** Agent loop is buildable. ⚠️ **Blocker:** live-voice demo failure risk in a loud venue → must have a recorded fallback + a "type instead of talk" path.

**Discussion notes.** Triage red-flag gives it a safety spine. Competes with the Discrepancy Detector on Originality (voice-intake is closer to what startups / Abridge-adjacent products already ship). Mental model: prefill = memory, voice = mouth/ears, Claude loop = brain.

## 6. Referral Tracking + Auto Check-in — 🔴 med-low feasibility
*Origin: Asit (A3).*

**Problem.** The "referral black hole" — ~25–50% of referrals are never completed; specialist notes often never return to the PCP → missed diagnoses (the referred-but-never-seen cancer), duplicated care, liability.

**Solution.** Track each referral through **ordered → scheduled → attended → note-back**, auto-chasing at each step and flagging stalls (auto check-in = proactive follow-up).

**Approach.** Ingest referrals (FHIR `ServiceRequest`) → track lifecycle state → detect stalls → act (patient outreach, request notes from specialist, alert PCP) → loop until closed.

**Hackathon feasibility.** **Temporal** → must simulate the referral lifecycle + design a time-compression demo. ⚠️ dashboard-risk (keep the *chasing* as the star, not a status board).

**Discussion notes.** High Impact (missed-referral = missed-cancer); medium Originality (referral-management is a known enterprise category). It's a **"dropped-loop" safety-catch**, but *temporal* — a heavier architectural add than point-in-time checks. Merges into the catch engine as the temporal/stretch-tier catch.

## 7. Continuous-Care Agent (incl. homebound/bedridden) — 🔴 med-low feasibility
*Origin: Akshay (#3, from prenatal → "consistent care"). Absorbs Asit's A2 at-home bedridden care.*

**Problem.** Chronic disease + poor follow-through is where the system fails — patients never reach goal because titration lapses between visits; deterioration is caught too late → hospitalizations/readmissions.

**Solution.** A stateful agent that **manages a patient's clinical trajectory over time** — ingests new data between visits, reasons on-track / deteriorating / non-adherent, and acts (adjust dose, remind, escalate). Same engine covers homebound/bedridden patients via caregiver-reported input (A2).

**Approach.** care plan + patient state → new data arrives (home BP/weight/glucose/symptoms/caregiver reports) → reason → proactive action. Best instances: **CHF monitoring** (best "save lives + money," readmissions), **HTN/diabetes titration** (best scale), INR, post-op.

**Hackathon feasibility.** **Temporal** → must simulate the between-visit data stream + design a **time-compression "fast-forward" demo** (show weeks in 90 sec). Between-visit data isn't in FHIR (simulated). The demo staging is the make-or-break.

**Discussion notes.** The **"temporal-monitoring engine"** (watch state over time → act). A2 (homebound) folds in — its distinctive physical layer (skin/mobility/ADLs) is data-gated, so what's buildable is just #3 aimed at homebound patients. **vs Post-Visit Companion:** clinical management vs behavioral adherence. **vs pending-results catch:** ongoing management (unbounded) vs one-loop closure (finite).

## 8. Proactive Patient-Protection — 🔴 med-low feasibility
*Origin: Akshay (#6, reframe of outbreak tracking).*

**Problem.** When something changes in the outside world that endangers patients (drug recall, outbreak, guideline change, environmental hazard), the question *"which of my patients does this affect, and what should each do?"* is answered slowly, manually, or not at all → vulnerable patients missed.

**Solution.** An agent that watches for external events and, for each, determines **which specific patients are endangered** (reasoning over each patient's health context) and takes protective action (personalized alert + clinician notification).

**Approach.** event → structured risk profile → per-patient reasoning against the chart (comorbidities, meds, immunizations, age, location) → prioritize → drafted personalized alert + clinician flag.
- **Formal unit of work:** for each `(event, patient)` → `{ at_risk?, why (grounded), action }`.
- **Lead demo:** drug recall (crispest) — "Valsartan lot X recalled → agent finds the 4 patients on it → drafts each a stop/switch message + alerts their PCP."
- **Same engine, other triggers:** outbreak · guideline change (absorbs *dynamic-rules*) · environmental.
- **Hackathon scope:** inject one event → sweep a small FHIR panel → personalized alerts.

**Hackathon feasibility.** Needs a patient **panel** + injected event + sweep (more setup). ⚠️ dashboard-drift risk (keep the star = per-patient reasoning + alert). Uses structured FHIR more than the ambient encounter — a step outside Abridge's core.

**Discussion notes.** The "external event → protect my patients" engine; absorbs the dynamic-rules ingredient. Fresh framing (few will build it), but temporal + panel setup drags feasibility.

---

# Cross-cutting patterns (discovered while ideating)

- **Safety-catch philosophy** — the agent's job is to *catch what humans miss* (a grounded flag + fix), not *generate* documents or *execute* paperwork. Best fit for this rubric (Impact + Originality + Technical + Abridge taste); inherently dodges the dashboard/RAG bans. The winning meta-theme. *(A4 is its purest form.)*
- **Temporal-monitoring engine** — a persistent agent that watches something over time and acts when a condition is met. Powers Continuous-Care, Patient-Protection, referral/pending-results tracking. Demos need time-compression staging.
- **Point-in-time vs temporal catches** — point-in-time (one-shot on an encounter) is far more finishable in 5 hrs than temporal (needs a scheduler + simulated time). This split defines MVP vs stretch.
- **Dynamic-rules ingredient** — rules change (recall, guideline, protocol amendment) → re-flag affected patients. A modifier, not a standalone.

## Decision filters used
1. Is the signal even in Abridge's encounter+FHIR data? (else you fabricate)
2. Front-line clinician/patient, or back-office? (back-office loses clinician-judge resonance)
3. Dodges the dashboard + basic-RAG + chatbot bans?
4. Distinct, or does it collapse into another candidate/engine?
5. Uses Abridge's world (ambient documentation), or orbiting outside it?

## Rejected (Akshay's explicit calls)
- Patient support group · Patient-doctor matching (incl. "Tinder for docs") · Vaccination tracking
