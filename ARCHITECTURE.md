# Architecture — how the agent works

> Companion to [`PROJECT.md`](./PROJECT.md). `PROJECT.md` is the pitch and the
> plain-terms **logic**; this is the **build spec** — the same idea turned into concrete
> steps: what's plain code, what needs the model, and what each step hands the next.

## The whole thing at a glance

The core idea is boring on purpose: **put every line from every source into one table,
then group by drug and look for disagreements.** That's it.

```
                                   INPUTS · 4 sources
   ┌──────────────────┬──────────────────┬──────────────────┬──────────────────┐
   │  home med list   │  hospital orders │    transcript    │   signed note    │
   └────────┬─────────┴────────┬─────────┴────────┬─────────┴────────┬─────────┘
            │   READ (no LLM)   │                  │  READ (◆ LLM)    │            STEP 1
            ▼                   ▼                  ▼                  ▼
        ┌───────────────────────────┐      ┌───────────────────────────┐
        │  rows from the lists       │      │  rows from the talking     │
        │  (drug · dose · state)     │      │  (drug · decision · quote) │
        └─────────────┬─────────────┘      └─────────────┬─────────────┘
                      └───────────────┬──────────────────┘
                                      ▼                                           STEP 2
                ┌───────────────────────────────────────────┐   plain code
                │  ONE TABLE of med-lines — the ground truth  │
                │  drug·strength·form·state·source·doctor·quote│
                └──────────────────────┬──────────────────────┘
                                       ▼                                          STEP 3
                ┌───────────────────────────────────────────┐   ◆ LLM + guardrail
                │  MATCHER  (+ resolve_med → RxNorm/class)     │
                │  clean up the drug name, group table by drug │
                └──────────────────────┬──────────────────────┘
                                       ▼                                          STEP 4
                ┌───────────────────────────────────────────┐   plain code
                │  CLASSIFIER   look down each drug group      │   (truth table)
                │  → a verdict per drug                        │
                └───────────┬───────────────────────┬─────────┘
                     agreements                    flags ⚠
                            │                          ▼                          STEP 5
                            │            ┌───────────────────────────────┐  ◆ LLM ×N
                            │            │  EXPLAINER  (one per flag)      │  (flags only)
                            │            │  resolution · reason · receipt  │  + precision gate
                            │            └───────────────┬───────────────┘
                            └─────────────┬──────────────┘
                                          ▼                                       STEP 6
                ┌───────────────────────────────────────────┐   plain code
                │  ASSEMBLE + RANK   (one card per drug)       │
                └──────────────────────┬──────────────────────┘
                                       ▼
        draft list  (the quiet ~90%)   +   disagreements  (ranked, each with a receipt)


   ◆ = the model is used here · everything else is plain code
   Model is used 3 places:  the READ of prose (transcript + note) · the Matcher · one call per flag
```

Read top to bottom: four sources → one table of lines → grouped by drug → each drug
checked against a truth table → only the flagged drugs get explained → ranked and handed
back. The rest of this doc is one section per step.

## One design choice up front: a workflow, not an agent

Per Anthropic's [Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents):
an **agent** lets the model decide its own next move in a loop (use it when you can't
predict the path); a **workflow** runs the model through fixed, known steps (use it when
you can).

Our path is the same every time — *read → build the table → group → check → explain →
rank* — so this is a **workflow**. That's the strength, not a cop-out: a fixed path means
every decision is inspectable, which is the whole product. We use the model **only where
the meaning is in prose, or the drug name is messy**; everything a computer can do
exactly stays plain code. That's just three model calls total: reading the prose, the
Matcher, and one call per flagged drug (and there are few of those).

---

## Step 1 · Read the four sources

Two sources are plain lists we can read field-by-field; two are prose where a person has
to *read the meaning*. So the first split is: a **read-the-fields lane** (no model) and a
**read-the-meaning lane** (needs the model).

```
   READ THE FIELDS  ──  no model                READ THE MEANING  ──  ◆ model
   ════════════════════════════════             ═══════════════════════════════

   ┌────────────────────────┐                   ┌────────────────────────┐
   │ home med list          │                   │ transcript             │
   │   → read the fields    │                   │   → pull out decisions  │
   └───────────┬────────────┘                   └───────────┬────────────┘
               │                                            │
   ┌───────────┴────────────┐                   ┌───────────┴────────────┐
   │ hospital orders        │                   │ note (A&P)             │
   │   → read fields + who   │                   │   → pull out decisions  │
   │      ordered it         │                   │      + who wrote them   │
   └───────────┬────────────┘                   └───────────┬────────────┘
               │                                            │
               ▼                                            ▼
       rows for the table                          rows for the table
   drug · strength · form ·                     drug · decision (state) ·
   state · source · doctor                      source · doctor · quote
```

**Both lanes write the same kind of row** — they just fill it from different places.
Reading fields is free (a computer does it exactly), so the two lists cost no tokens;
only the prose (transcript + note) uses the model. After Step 1 nothing ever looks at the
raw sources again — everything downstream reads the table.

---

## Step 2 · Put every line in one table — the ground truth

Every line from every source becomes **one row in one table**. Six columns and a quote —
that's the whole record, and it's all we need to both *spot* a conflict and *trace it
back to who said it*:

```
   drug         strength  form     state    source      doctor              quote
   ─────────────────────────────────────────────────────────────────────────────────────────
   clopidogrel  75 mg     tablet   active   home        cardiology          —
   clopidogrel  75 mg     tablet   held     inpatient   surgery / Okafor    —
   clopidogrel  —         —        stop     transcript  surgery / Okafor    "holding your Plavix…"
   clopidogrel  75 mg     tablet   resume   note        cardiology / Patel  "resume clopidogrel 75 daily"
```

| column | what it's for |
|---|---|
| **drug** | the key we group on (an ingredient name) |
| **strength**, **form** | to spot dose / formulation changes within a drug |
| **state** | what's happening to it — `active`/`held` from a list, `stop`/`resume`/`start`/`change` from talking |
| **source** | which of the five: home · inpatient · discharge · transcript · note |
| **doctor** | `{ name, specialty }` — to catch two teams clashing, and to cite |
| **quote** | the receipt — the exact words, for anything said or written |

### Two things we keep, three we work out

We only *store* two things about where a line came from — **source** and **doctor** —
because everything else can be worked out from them:

- **on a list, or said/written?** — comes from the source. home/inpatient/discharge are
  list-lines; transcript/note are said/written lines.
- **how much it counts** — comes from the source too: everything on a record counts as
  *signed*; only the transcript is *spoken*. (Used to settle disagreements, below.)
- **drug class + is-it-a-course** — looked up from the drug name in Step 3 (statin,
  antibiotic, …). Needed for the duplicate and orphaned-course checks.

So we don't store "signed vs spoken" or "class" as their own columns — fewer columns to
fill in means fewer things the model can get wrong.

**Why doctor is `{ name, specialty }` and not just a name:** when we check whether two
teams clash, the thing that matters is the *specialty* (surgery vs cardiology), not the
person. Keeping specialty as its own field means later code can compare teams directly
instead of digging it back out of a string.

> **Absence is data.** A drug on the home list with *no* discharge row is exactly the
> "accidentally dropped" case. (Hospital orders split into two sources — `inpatient` and
> `discharge` — so we can tell "held during the stay" from "sent home on it.")

```json
{
  "patient": "Philomena Goodwin",
  "lines": [
    { "drug": "clopidogrel", "strength": "75 mg", "form": "tablet", "state": "active",
      "source": "home",       "doctor": { "name": "prior records", "specialty": "cardiology" } },
    { "drug": "clopidogrel", "strength": "75 mg", "form": "tablet", "state": "held",
      "source": "inpatient",  "doctor": { "name": "Okafor", "specialty": "surgery" } },
    { "drug": "clopidogrel", "state": "stop",
      "source": "transcript", "doctor": { "name": "Okafor", "specialty": "surgery" },
      "quote": "we're holding your Plavix until after the operation" },
    { "drug": "clopidogrel", "strength": "75 mg", "form": "tablet", "state": "resume",
      "source": "note",       "doctor": { "name": "Patel", "specialty": "cardiology" },
      "quote": "resume clopidogrel 75 mg daily at discharge" }
  ]
}
```

### Settling disagreements: trust vs. who said it

Two things above line up neatly with how we settle a clash:

```
   the SOURCE tells us  →  how much to trust a line   →  used when the SAME doctor says two things
   the DOCTOR tells us  →  is it one team or two       →  used to catch DIFFERENT doctors clashing
```

**"Signed beats spoken" only holds within one doctor.** It's there so one doctor's
written record can override their *own* offhand remark — the surgeon says "let's hold the
Plavix" in the room, then signs "resume Plavix": same doctor reconsidering, the signed
line wins, the spoken line becomes the receipt. That's the *only* clash we settle
quietly.

**Across different doctors we never settle it — we flag it.** A spoken "hold" from the
surgeon is *not* beaten by a signed "resume" from cardiology; those are two real,
independent judgments. So:

- **same doctor**, spoken vs signed → keep the signed one (they changed their mind)
- **different doctors** — spoken-vs-signed *or* signed-vs-signed — that disagree → **flag
  it for a human**, show both, don't pick a winner.

Quietly settling is the rare exception, so it needs *proof* it's the same doctor; if we
can't tell who said a spoken line, we **flag it** rather than assume. This is why every
row carries the doctor — it's what tells "one doctor reconsidering" from "two doctors
disagreeing."

The table is now **the one thing every later step reads.** It's still flat — one drug can
be four rows — which the next step fixes.

---

## Step 3 · The Matcher — clean up the drug name, group the table by drug

To compare a drug we first have to *gather* it: clopidogrel is four separate rows right
now. The Matcher pulls every row for the same drug into one group — which is just the
table grouped by drug (drug down the side, source across the top):

```
                 home      inpatient   discharge   transcript      note
   ───────────────────────────────────────────────────────────────────────
   clopidogrel   active    held        ── (gone)   "stop" (spoken) "resume" (signed)
   atorvastatin  active    active      active      ─               ─
   cefdinir      ─         active      active      ─               "7-day course"
```

Once it's grouped, every situation is just a **shape you can read off the row** — no
cleverness later: clopidogrel present home+inpatient but **blank at discharge** = dropped;
cefdinir inpatient/discharge but **not home, no end date** = orphaned course; two teams on
one drug = duplication.

**This is the one step that needs the model,** because "the same drug" is messy:

- `metoprolol tartrate 25mg` vs `metoprolol succinate ER 50mg` — **same drug, different
  form** → must go in **one** group (so we can flag the switch).
- `simvastatin` vs `atorvastatin` — **different drugs, same class** → stay **two** groups
  (that split *is* the duplicate-statin flag).
- `"your water pill"` → resolve to the furosemide group.

It runs as **one model call that loads the grouping rules as its instructions** (like a
reusable rulebook it reads before acting):

1. Group rows with the **same ingredient** (ingredient is the key).
2. **Same ingredient, different strength/form → same group** (a change, not two drugs).
3. **Different ingredient → never merge**, even in the same class (two statins = two
   groups = a duplicate flag).
4. Resolve messy names (brands, `"water pill"`, typos) to the ingredient first.
5. **Tag each group with its class** (statin, antiplatelet…) **and whether it's a course
   drug** (antibiotic/steroid) — the next step needs class for the duplicate check and
   course for orphaned-course.

**Its one tool — `resolve_med(name)`.** Instead of trusting the model's memory for drug
facts, it calls a small lookup backed by **RxNorm / RxClass**: `resolve_med(name) →
{ ingredient, class }`. This is more trustworthy *and* explainable ("grouped because
RxNorm says same ingredient" beats "the model thought so"), and it answers the only two
drug questions we have: identity and class. It is **not** web search — that would be
unpredictable, off-mission (we compare sources, we don't research drugs), and a live-demo
risk. For the demo the lookup is a **small cached file** of real RxNav answers for the
demo drugs; swapping in the live API later is a one-line change.

**A plain-code check runs on the model's output** (it can only *fix*, never *hide*):

```
   the table  ──▶  ┌──────────────────────┐  ──▶  ┌──────────────────────┐  ──▶  drug groups
                   │  Matcher (model)      │       │  check (no model)     │
                   │  loads grouping rules │       │  • no group mixes 2   │
                   │  → groups the rows    │       │    different drugs     │
                   └──────────────────────┘       │  • every row lands in  │
                                                   │    exactly one group   │
                                                   └──────────────────────┘
```

Cheap enough to do all at once: Philomena's table is ~20–40 short rows, so one call
handles it. **Out: the drug groups** (each with its class + course tags) — what the next
step checks.

---

## Step 4 · The Classifier — look down each drug group, give a verdict

This answers the core question — *do the sources agree on whether she takes this, and at
what dose?* — one drug group at a time. **Because the Matcher already did the messy part
(identity + class), this is plain code:** each situation is just a pattern of which
sources are filled and what they say. A truth table, no model.

**The verdict is really home vs. discharge** — what she was on vs. what she's going home
on. The other three sources are *evidence*, not the verdict: `inpatient` says what
happened during the stay, `transcript`/`note` say why. This matters: an inpatient
**`held`** is a temporary hold for surgery, **not** a stop — reading it as a stop is how a
naive tool false-flags a drug (metformin held the morning of surgery, resumed at
discharge = **unchanged**, not discontinued).

```
   WHAT THE GROUP LOOKS LIKE  (verdict = home vs discharge; other sources = evidence)  →  VERDICT
   ─────────────────────────────────────────────────────────────────────────────────────────────
   home active, discharge active, same dose, nothing contradicting it            →  unchanged  (pre-fill)
   home active, discharge active, strength/form differs                          →  dose-changed
   not on home, on discharge, and NOT a course drug                              →  newly-started
   home active, gone at discharge, and someone said "stop"                        →  discontinued (clean)
   home active (+inpatient), gone at discharge, nobody said stop                   →  accidental-drop ⚠
   said/written but no matching order                                            →  said-not-ordered ⚠
   new AND a course drug (antibiotic/steroid) AND no end date                    →  orphaned-course ⚠

   ── same doctor disagrees with themselves → settle it quietly ──────────────────────────────────
   one doctor, spoken vs signed contradict                                       →  keep the signed one; no flag

   ── different doctors disagree → hand to a human ────────────────────────────────────────────────
   same drug, different doctors, contradict (spoken/signed OR signed/signed)      →  cross-team conflict ⚠
   two drugs kept at discharge, same class, different doctors                     →  cross-team duplicate ⚠
```

Three rows lean on things worked out earlier, so this step stays a plain lookup:

- **duplicate** uses the class tag, and only counts drugs **kept at discharge** — a
  duplicate that was already cleaned up isn't a flag; one that *survives to discharge* is.
- **orphaned-course** uses the course tag — without it, every new *chronic* med (a new
  statin has no end date, correctly) would wrongly look orphaned.
- the **cross-team** rows use the doctor's specialty carried on every row.

The thing that decides *settle quietly* vs *flag* is **whose** lines clash. One doctor
reconsidering (spoken then signed) is the only one we settle silently. Different doctors
disagreeing goes to a human with both shown side by side — **whatever the trust levels**:
a spoken "hold" from surgery is not overridden by a signed "resume" from cardiology
(Philomena's surgery / hospitalist / ID moment). If we can't tell who said a spoken line,
we treat it as a different doctor and flag.

**Out: every drug tagged, split into two piles — agreements** (pre-filled, collapsed) and
**flags** (the ⚠ ones headed for the queue).

---

## Step 5 · The Explainer — turn each flag into a card a clinician can act on

A verdict like `accidental-drop` is a machine label, not something you act on. The
Explainer turns each flag into a card. **This is the only fan-out: one model call per
flag, in parallel — and only the flags, never the agreements.** That's the cost story:
the agreements (most drugs) never touch the model after the Matcher, and precision keeps
the flag count small.

Each per-flag call does four things:

1. **Draft the fix** using the trust rule (signed wins — e.g. "Resume clopidogrel 75 mg —
   per signed note"; for a cross-team clash, present both, no auto-pick).
2. **Write the one-line reason** for the clinician.
3. **Write the plain-English "why this changed"** line for the patient summary.
4. **Attach the receipt** — the quote + doctor that raised it.

Plus a **precision gate**: drop weak, low-confidence flags. A quiet queue the clinician
trusts beats a noisy one they ignore — that's the failure mode we design against.

Two rules that keep it honest:

- **It never changes the verdict.** Step 4 already decided *what* the flag is; Step 5 only
  dresses it up. The decision stays plain code and inspectable.
- **The receipt is passed in, not re-found.** The quote + doctor already sit on the row
  (Step 2), so the call *cites* them — it can't invent a quote.
- **Not every flag has a quote.** A silent drop (tacrolimus on home + inpatient, gone at
  discharge, never discussed) has no quote — **the gap itself is the receipt** ("on home
  list + kept inpatient; missing from discharge"). The receipt is either a quote or that
  kind of plain fact.

**Out: the flag cards** — each with its verdict, the fix, the reason, the patient line,
and a receipt.

---

## Step 6 · Assemble + rank — the thing the screen shows

Plain code, no model. Put the two piles together and order the queue so attention lands
where it matters.

**One card per drug.** A drug can trip more than one thing (clopidogrel is both a
cross-team conflict *and* half of a duplicate). Merge by drug so the clinician sees
clopidogrel once, with both issues on it — never the same drug twice.

- **Draft list** = the agreements, pre-filled and collapsed.
- **Queue** = the flag cards, **ranked** by:
  - **how serious the verdict is** — an accidental-drop or a cross-team conflict beats a
    documented dose change. (Without this, a silently dropped transplant drug wouldn't
    rise to the top on drug-class alone.)
  - **high-risk drugs** — blood thinners / antiplatelets / insulin, **plus
    narrow-margin drugs like tacrolimus** (which is Philomena's #1 flag).
  - **the patient** — old age + lots of meds nudge the whole queue up.

  (These only affect *ordering* — no labs, no kidney numbers, no diagnosis list. We rank,
  we don't judge safety.)

```
   final output
   ├─ draft list      ← agreements, pre-filled  (the quiet ~90%)
   └─ disagreements   ← ranked cards, each with a receipt  (the few that need a human)
```

Nothing applies itself. **We line it up and show it; the human decides.**

---

## Stack (hackathon)

**Hand-rolled, calling Claude directly — no heavy agent framework.** The flow is a fixed
pipeline (with a fan-out at Step 5), not something a framework helps with, and every judge
question is "how does it decide?" — hand-rolled keeps that answer visible.

- **Python backend**, **Anthropic Messages API** — plain calls for the prose-read, the
  Matcher, and the Explainer; tool-use only for the Matcher's `resolve_med`.
- **Pydantic** for the shapes passed between steps (also the test/eval schema): the table
  (Step 2), the drug groups (Step 3), the verdicts (Step 4), the final output (Step 6).
  Its real job is checking the model's JSON at each hand-off — reject a bad shape at the
  door instead of letting it crash later.
- **The plain-code steps are just code** (read-the-fields, classifier, the Matcher check,
  assemble/rank) — testable with no model.
- UI: a small React page hitting a FastAPI endpoint that returns the Step 6 output.
