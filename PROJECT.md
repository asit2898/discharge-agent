# Discharge Medication Reconciliation — Project Brief

**Hackathon:** Abridge / "The Future of Agentic AI in Healthcare"
**One-liner:** An Abridge-powered agent that does the tedious *prep* for discharge
medication reconciliation — it **pre-populates** a draft reconciled list from every
source (home meds, inpatient orders, and the ambient **transcript**), then **surfaces
exactly where the sources disagree**, each conflict laid side-by-side with the
transcript quote and prescriber as evidence. The clinician still makes every call —
we just turn "assemble the picture from scratch, then decide" into "the picture is
already assembled and the disagreements are highlighted; decide."

**What it does NOT do:** it does not reconcile *for* the clinician or auto-sign
anything. It removes the gathering and the hunting, and makes the human's decision
faster — decision *support*, not decision *replacement*.

### Where the time actually comes from (two levers)
1. **Pre-population / assembly.** The documented time sink is building the picture —
   cross-referencing home meds, hospital orders, pharmacy history, and the
   conversation into one normalized, prescriber-attributed list. We do that up front,
   so the reconciliation screen opens *already filled in* instead of blank.
2. **Surfacing disagreements with evidence.** Instead of the clinician eyeballing 15
   meds to find the 3 that conflict, we put every disagreement on top — home-vs-order,
   order-vs-conversation, prescriber-vs-prescriber — each with the quote/source that
   causes it. The decision stays human; the *finding* is done for them.

We win on **making the decision easy, not making the decision.**

---

## The problem (validated, not assumed)

Medication reconciliation at care transitions is one of the most-studied
patient-safety failures in medicine:

- **~60% of medication errors** occur at care transitions (admission / transfer /
  discharge). More than **40%** trace to inadequate reconciliation.
- **Up to 67–70% of patients** have an *unintended* medication discrepancy at
  admission or discharge; discrepancies are **more common at discharge** than
  admission.
- **~78–80% of discrepancies are "system-generated"** — the two biggest drivers
  are **failure to remove discontinued meds** and **failure to capture meds
  discussed but never structured**. This is the gap only the transcript can close.
- **12.5% of patients** have an adverse drug event within 30 days of discharge;
  **~62% were preventable.**

Sources:
- Medication Reconciliation as a Patient Safety Strategy — *Annals of Internal Medicine* (2013). https://www.acpjournals.org/doi/10.7326/0003-4819-158-5-201303051-00006
- Unintentional medication discrepancies at care transitions — *BMC Geriatrics* (2024). https://link.springer.com/article/10.1186/s12877-024-05517-w
- Sources & Types of Discrepancies Between EMRs and Actual Outpatient Medication Use — *PMC*. https://pmc.ncbi.nlm.nih.gov/articles/PMC10437703/
- Readmissions and Adverse Events After Discharge — *AHRQ PSNet*. https://psnet.ahrq.gov/primer/readmissions-and-adverse-events-after-discharge
- When Records Do Not Connect: Medication Safety in EHR Interoperability Gaps — *Pharmacy Times*. https://www.pharmacytimes.com/view/when-records-do-not-connect-medication-safety-risks-hidden-in-ehr-interoperability-gaps

---

## Point 1 — The pharmacist is usually absent (our core opening)

Pharmacist-led discharge reconciliation is the accuracy gold standard, but it is a
**special program, not the default** — typically reserved for high-risk patients.
In the common case, discharge reconciliation is done by the **discharging
physician alone, from memory**, then handed to a **nurse** for patient education.

When a pharmacist *is* involved, the workflow is:
**Pharmacist reconciles & "pends" a draft in the EHR → Physician reviews & signs →
Nurse assembles the After-Visit Summary (AVS) & educates the patient.**
The physician always signs last (legal authority); the pharmacist works *in front
of* that signature.

- Pharmacist-obtained medication histories are **more accurate and complete** than
  those obtained by other clinicians. BPMH (Best Possible Medication History) is
  explicitly documented as **time-consuming** because it requires cross-checking
  multiple sources (community pharmacy, EHR, patient interview, outside records).

**Our positioning:** the agent *plays the role of the pharmacist the patient didn't
get* — an always-on reconciliation pass that pends a draft for the physician/nurse.

Sources:
- Pharmacist-facilitated discharge med-rec workflow — *ScienceDirect* (2022). https://www.sciencedirect.com/science/article/abs/pii/S1544319122003247
- BPMH / Medication Reconciliation — *ISMP Canada*. https://ismpcanada.ca/courses/medication-reconciliation-and-obtaining-a-best-possible-medication-history-bpmh-in-primary-care/
- Epic Physician Discharge Reconciliation Process — *Salem Health*. https://www.salemhealth.org/docs/default-source/default-document-library/education---physician-discharge-reconciliation.pdf

---

## Point 2 — Multi-source / multi-specialist is the hero scenario

The reason reconciliation is hard and error-prone: during a stay, **each specialist
prescribes inside their own silo** for their own problem, and **no single person
holds the aggregate view.** At discharge, one clinician must reconcile *everyone's*
orders into one outpatient list.

This produces the two worst discrepancy types, which we specifically detect:

1. **Cross-prescriber conflicts / duplication** — e.g. surgeon continues an
   anticoagulant for DVT prophylaxis while the patient's home regimen already
   includes one → double therapy.
2. **Orphaned meds** — a course a specialist started (e.g. an ID antibiotic or a
   steroid taper) that no one remembered to explicitly stop or continue.

**Two deployment modes, same engine:**
- **Primary target — no pharmacist present:** the agent *is* the reconciliation
  safety net between physician and nurse. Highest real-world coverage.
- **When a pharmacist is present:** the pharmacist becomes the **reviewer of our
  output** — we pend the draft, they verify a ranked queue instead of building the
  list from scratch. Either way a licensed human approves; we never sign.

FHIR makes attribution possible: each `MedicationRequest` carries a **`requester`**
(prescriber name + NPI) and a **`category`** (inpatient / outpatient / community),
so we can label *who ordered what* and *which meds are hospital-only vs. home*.

---

## Point 3 — Epic add-on, not a replacement (the integration story)

We do **not** replace Epic and we do **not** use brittle screen-scraping / computer-use.
The sanctioned path is a **SMART on FHIR embedded app**, registered via Epic's
marketplace (**Showroom / Connection Hub**), that:
- **reads** patient context via an authenticated FHIR token
  (`MedicationRequest`, `MedicationStatement`, `AllergyIntolerance`), and
- **pends a draft reconciliation** back into Epic's existing discharge med-rec
  screen — the *same "pend for the physician to sign" mechanism the pharmacist uses.*

**Why this is credible for an Abridge judge:** Abridge is already **"Epic's First
Pal"** — embedded in Epic (records in Haiku, writes notes *and orders* back through
Hyperdrive, bidirectional). Our engine **rides the Abridge embed that already
exists**, consuming the transcript Abridge already captures. We are an augmentation
layer on their platform, not a rip-and-replace.

**For the demo:** all of this is **mocked** — no live Epic. Inputs are local
FHIR-shaped JSON + a transcript; the output UI is styled as "the pre-filled
reconciliation draft that pends into Epic." Credibility line:
> *"We don't replace Epic — we pend a draft into the screen clinicians already use,
> riding the Abridge embed that writes orders today."*

Sources:
- Abridge Inside for Inpatient/Outpatient Orders. https://www.abridge.com/press-release/abridge-inside-for-inpatient-and-outpatient-orders
- Abridge Becomes Epic's First Pal. https://www.abridge.com/press-release/abridge-becomes-epics-first-pal-bringing-generative-ai-to-more-providers-and-patients
- Building a SMART on FHIR App with Epic — *Itirra*. https://itirra.com/blog/how-to-build-a-smart-on-fhir-app-that-integrates-with-epic/

---

## Landscape & differentiation (why doesn't X already do this?)

The market splits into **two camps, and no one sits in the seam between them** —
which is exactly where we live.

### Camp A — Ambient documentation (Dragon Copilot, Wellsheet, Abridge itself)
Listen to the conversation and **generate documents** — notes, discharge summaries,
flowsheets.
- **Microsoft Dragon Copilot** — Oct 2025 nursing release ambiently captures
  nurse-patient talk → flowsheet entries; generates discharge reports.
- **Wellsheet Care Team Copilot** — reads the whole chart → drafts the discharge
  summary + length-of-stay dashboard.

**What they do NOT do:** cross-check the conversation *against* the structured
orders and flag **discrepancies with evidence.** They transcribe and summarize; they
don't reconcile and contest. *A discharge summary that faithfully repeats a wrong med
list is still wrong.*

### Camp B — Medication-history data tools (DrFirst, Cureatr)
The serious med-rec incumbents. They aggregate **external structured history** and
normalize it.
- **DrFirst (MedHx / SmartSuite)** — pulls 12 months of external fill history
  (Surescripts, pharmacy, payer, HIE), auto-maps 86% of sigs.
- **Cureatr** — aggregates records across Carequality / CommonWell / eHealth Exchange.

**What they do NOT do:** they source from **structured fill/claims data — never the
conversation.** Great at "what was the patient dispensed?"; blind to "what did the
doctor just decide and say?" They cannot catch a med a surgeon *verbally* stopped
that is still an active order, because that intent lives only in the room.

### Our wedge (one sentence)
> Every existing tool has either the **conversation** OR the **structured record**.
> We are the only one that **reconciles the two against each other** — three-way
> (transcript ↔ FHIR ↔ prescriptions), across **multiple prescribers**, with the
> **transcript quote as the evidence** for each flag.

**Three defensible differentiators:**
1. **Conflict detection, not documentation.** Camp A writes down what was said; we
   *diff it against the orders and raise a flag when they disagree.* Different job.
2. **The conversation as a first-class reconciliation source.** Camp B's best data is
   a pharmacy fill record; ours is what the ID doctor *actually said*. This is
   Abridge's structural moat — they own the ambient layer.
3. **Cross-prescriber attribution + citation.** We flag the surgeon-vs-cardiologist
   anticoagulant duplication and cite *who said what* — a ranked queue of conflicts,
   each with a receipt.

### The honest risk (and our answer)
*"Abridge already generates discharge orders from the conversation — isn't this their
roadmap?"* → **Generating an order from the conversation is the easy half. The hard,
unsolved half is catching where the conversation and the existing record *conflict* —
the discontinued-but-still-active med, the two teams double-prescribing. Abridge
produces the intent stream; we are the reconciliation/conflict layer that consumes
it.** This makes us *additive to Abridge*, the right posture in their own hackathon.

Sources:
- Microsoft extends Dragon Copilot to nurses (Oct 2025). https://news.microsoft.com/source/2025/10/16/microsoft-extends-ai-advancements-in-dragon-copilot-to-nurses-and-partners-to-enhance-patient-care/
- Wellsheet launches Care Team Copilot — *HIT Consultant*. https://hitconsultant.net/2025/07/18/wellsheet-launches-care-team-copilot-to-halve-charting-time/
- DrFirst Medication History & Reconciliation. https://drfirst.com/medication-history-reconciliation
- Cureatr Medication Management Technology. https://www.cureatr.com/comprehensive-medication-management-technology

---

## Point 4 — Data: what we have and what we must build

**Provided dataset:** `synthetic-ambient-fhir-25/` — 25 synthetic patients, **one
encounter each**, each record bundling:
- `transcript` (speaker-labeled ambient conversation — our **intent** source)
- `note` (SOAP clinical note) + `after_visit_summary` (baseline AVS to improve on)
- `patient_context.longitudinal_summary` — `resource_counts`,
  `condition_labels`, `medication_labels`
- `encounter_fhir.related_resources` — FHIR R4 grouped by type, including
  **`MedicationRequest`** with `status`, `intent`, `authoredOn`,
  `category` (**inpatient/outpatient/community**), and **`requester`** (prescriber
  + NPI). Drug names resolve via `medicationReference` → `Medication` /
  `medication_labels`.

**This gives us:** the exact FHIR shape we need for prescriber attribution and
inpatient-vs-home classification, plus paired transcript↔note↔AVS to ground the
"cite what was said" feature.

**The gap we must fill ourselves:** the data is **one encounter per patient**, so a
true **multi-specialist inpatient→discharge journey does not exist natively.** The
hero scenario is something we **construct**:
- Generate a richer patient (Synthea-style FHIR) with encounters + `MedicationRequest`s
  from **multiple prescribers** (hospitalist, surgeon, ID), and
- Author **multiple transcripts** (per-specialist + discharge conversation) with LLMs,
  **planting deliberate discrepancies**: one discontinued-but-still-listed med, one
  cross-prescriber duplication/conflict, one orphaned antibiotic course.

Everything else in the engine reads this constructed bundle exactly as if it came
from a live FHIR token.

**Note — generating more data is on-method, not a hack:** the provided dataset was
itself built with **Synthea (simulated patients) + LLM-authored transcripts**
grounded in the structured record. Constructing our multi-specialist hero patient
uses the *same pipeline Abridge used*, simply extended to the transition-of-care
case they didn't include. This is a point in our favor with judges, not a liability.

---

## Assumptions & source authority (how we stay safe)

**We assume ambient transcripts are available for the relevant encounters.** This is
a *fair* assumption here: this is Abridge — ambient capture of clinical conversations
is their entire product, already live in Epic and expanding across inpatient and
specialty settings. Building on that data isn't a stretch; it's the platform's premise.

**The transcript is a detection signal, not the source of truth.** A conversation is
casual and provisional — a clinician may say "let's stop the heparin" and then keep it
on the signed order for a good reason. So we never let a raw utterance *overrule* the
considered record. Our authority order is:

> **signed order / clinical note  >  transcript**

- When the note/order and the transcript **agree**, we pre-populate and move on.
- When they **disagree**, the transcript's job is only to **raise the flag** — we
  surface the disagreement and **default our suggested resolution to the note/order**
  (the deliberate, signed artifact), showing the transcript quote as the *reason we're
  asking*, not as the answer. The clinician decides.

This gives us the best of both: the transcript lets us **catch** discrepancies a
FHIR-only tool can't see, while the note/order keeps us from **acting on** an offhand
remark. Detection from the conversation; recommendation from the record; decision from
the human.

**One important limit: "signed beats spoken" only holds _within the same doctor_.**
The rule above is really *self-reconsideration* — one clinician's considered record
supersedes their *own* offhand remark (they say "let's hold the heparin," then sign to
continue it for a good reason). It is **not** a license for one doctor's signed order to
override a *different* doctor's spoken directive. A spoken "hold" from the surgeon is not
inferior to a signed "resume" from cardiology — those are two independent clinicians
disagreeing, and it **still needs to be flagged**, not silently auto-resolved. So across
different prescribers, authority *abstains* — any contradiction (spoken-vs-signed or
signed-vs-signed) surfaces as a conflict with **both prescribers' orders side by side**
for the human. This is exactly the multi-specialist hero case (surgeon / hospitalist /
ID), and it's why every med row carries *who* ordered it, not just *what* the record
says. (Mechanics: see [`ARCHITECTURE.md`](./ARCHITECTURE.md).)

---

## How it works — the logic, in plain terms

*The reasoning a discharge pharmacist does by hand; this is what we automate.*

**We read four sources, and each tells us something different:**

1. **Her home med list** — what she was actually taking before admission. The
   baseline everything else is compared against.
2. **The hospital's orders** — what each team prescribed during the stay, and *who*
   prescribed it (surgeon, hospitalist, ID). This is what changed while she was in.
3. **The ambient conversation (transcript)** — what the clinicians actually said out
   loud: the reasoning ("we're stopping this because…", "keep taking that, it's
   important"), often spoken before, or instead of, being written down anywhere.
4. **The signed note** — the official, committed written version of what should
   happen (its Assessment & Plan states the decision in the clinician's own words).

The home list and hospital orders are structured facts we read directly. The
conversation and the note are where *intent* lives — what was decided and why.

**We compare them one medication at a time.** For each drug: was it on the home
list? Did the hospital order it, and which team? Did anyone say anything about it in
the room? Is it in the note? Then the simple question: *do the sources agree on
whether she should be taking this, and at what dose?*

**Each drug resolves to one of a few situations:**
- **All sources agree** → fill it into the draft list, quietly. (Most meds.)
- **On the home list, gone from the discharge orders, and no one said to stop it** →
  likely an accidental drop → raise it.
- **Someone said to stop it, but it is still on the list** → raise it.
- **Two teams prescribed for the same thing** → duplication → raise it.
- **A course was started with no stated end** → orphaned → raise it.
- **Said in the room but never turned into an order** → raise it.

**When sources disagree, the signed record wins — always.** Orders and note are
deliberate and committed; the conversation is casual and provisional (a clinician may
say "let's stop the heparin," then keep it on the signed order for a good reason). So
the conversation's only job is to *make us notice* the disagreement — it never
overrides. Our suggested resolution defaults to the signed record, with the spoken
quote shown beside it as *"why we're asking,"* not as the answer.

**What we hand back:** a discharge list already filled in for everything that agreed,
plus a short, ranked list of the disagreements — each showing the drug, the conflict,
who said what, and the exact quote — so the clinician spends attention only on the few
that need a human decision. We assemble and surface; the human decides.

---

## Architecture

The full engineering build spec — every step from the logic above turned into concrete
code (what the model decides vs. what stays plain code, the tools, the contracts, the
stack) — lives in **[`ARCHITECTURE.md`](./ARCHITECTURE.md)**.

In one line: it's an **orchestrator agent over grounded tools** — Claude drives a
tool-use loop (plan → run the safety checks that fit this patient → investigate the
ambiguous ones against the chart + transcript → confirm/dismiss → draft the order action),
while the tools themselves (the Chart Compiler and the eleven KB-backed checks) stay
deterministic. The agent gets the agency; the tools keep the receipt — a confirmed flag
still traces to a rule in code + an exact FHIR resource, and the whole loop is an
inspectable trace. (A deterministic no-LLM workflow is the offline/eval fallback.)

## UI (the demoable 20%)

One reconciliation screen — left: draft outpatient med list; right: discrepancy queue,
each card with ✅ Accept / ✏️ Edit / ❌ Reject and a transcript snippet ("why").
A reviewer clears a full patient in ~60 seconds.

**Killer demo moment:** a med the **EHR still lists but the transcript shows a
specialist stopped** (or a cross-team duplication) — our agent catches it, cites the
quote and the prescriber, and a FHIR-only tool never could.

---

## Open decisions
- **Persona for the demo UI:** nurse vs. pharmacist vs. physician (same engine).
  Leaning nurse/pharmacist for the cleanest "verify a queue" story.
- **Stack:** single-page web app (React) + small backend calling Claude for the
  reason/citation step.
