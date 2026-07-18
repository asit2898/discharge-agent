# Discrepancy-Detector Training / Eval Dataset

100 ambient-visit records in Abridge's **exact** `synthetic-ambient-fhir` 8-field
schema, each built on a **real Synthea FHIR-R4 patient chart** and carrying a
**known, labeled clinical discrepancy** (or a clean control). This is the substrate
for building *and scoring* the Safety-Catch agent.

## How it's generated (two-stage, `use synthea`)

1. **Synthea** (`synthea/`) generates a real FHIR-R4 population — 160 adults age
   40–90 (California, US-Core IG) + a younger-female batch for pregnancies. Command
   is deterministic under its seed. Real charts → real demographics, ~20–60 encounters
   each, real problem lists, real active medications, real allergies, real labs.
2. **`synthea_to_records.py`** takes each real bundle, picks a real ambulatory index
   encounter, reconciles the patient's **real** active meds / allergies / problems /
   labs into the record, then plants **one labeled discrepancy** — *preferring real
   substrate and only synthesizing what the chart lacks*, recording provenance either
   way.

**Grounding provenance (this build):** every drug–allergy case uses a **real Synthea
allergy** (Lisinopril, Aspirin, Penicillin…); 30 med-interaction/duplicate/dropped
cases cite a **real active MedicationRequest**; 35 renal/result cases cite a **real
eGFR Observation** (some as low as 7 mL/min, MDRD). **62 of 78** positive labels point
at an actual Synthea-generated resource; the remaining 16 are the deliberately injected
substrate, tagged `injected` in each label's `grounding` field. All 100 records use a
**real Synthea US-Core encounter**; all 100 validate against Abridge's `schema.json`.

`generate_dataset.py` (pure-template, no Synthea) remains as an offline fallback that
emits the identical schema + label taxonomy.

## Why we generated our own set

Abridge's shipped `synthetic-ambient-fhir-25` is a great **format reference** but it
is **not** an eval set for a safety agent:

| What the safety checks need | In Abridge's 25? |
|---|---|
| `AllergyIntolerance` resources (drug–allergy check) | ❌ **zero** |
| Active outpatient med list (dropped / duplicate / interaction checks) | ❌ meds are inpatient/`completed`, `medication_labels` empty |
| Renal labs paired with a conflicting order (eGFR check) | ❌ not engineered to conflict |
| **Ground-truth labels** of what's wrong | ❌ the records are "clean" |

Synthea alone wouldn't fix this either — it emits clean charts (no allergy-vs-order
conflicts) and **no transcripts/notes**. So the real work is a generator that plants
a *grounded, labeled* discrepancy in each encounter. That's this dataset.

## Files

| File | What it is |
|---|---|
| `discrepancy-train.jsonl` | 100 records, **one per line**, Abridge 8-field schema (canonical) |
| `discrepancy-train.json` | same 100 records as a single array |
| `discrepancy-train.labels.jsonl` | **ground truth**, keyed by `id` — kept *separate* so the detector never sees the answer key |
| `summary.json` | index + label distribution |
| `schema.json` | JSON Schema for one record (identical field-set to Abridge's) |
| `synthea_to_records.py` | **primary** builder: real Synthea bundles → labeled records |
| `generate_dataset.py` | offline fallback generator + the shared clinical KBs/injectors |
| `synthea/` | the Synthea jar + generated FHIR-R4 population (`output_main/`, `output_preg/`) |

The detector must read only the **record** files. `labels.jsonl` is joined on `id`
at scoring time only.

## Record shape

Identical top-level fields to Abridge: `id`, `metadata`, `patient_context`,
`encounter_fhir`, `transcript`, `note`, `after_visit_summary`,
`after_visit_summary_provenance`. Every record validates against `schema.json`.

Two deliberate, documented enrichments (still schema-valid) put the checks' substrate
into the record where the agent can ground on it:

- `encounter_fhir.related_resources` includes the **reconciled active med list**
  (`MedicationRequest`, `status:"active"`, authored earlier), the patient's
  **`AllergyIntolerance`** resources, and relevant **lab `Observation`s** (eGFR, K, A1c,
  INR, TSH) — i.e. what a real med-rec-at-visit surfaces.
- `patient_context.longitudinal_summary` adds an `allergy_labels` list alongside the
  standard `condition_labels` / `medication_labels`.

## Label taxonomy (what's planted)

Detector **#1 – Record Discrepancy** targets `discrepancies[]`; Detector **#2 – Drug
Adverse-Effect** targets `adverse_events[]`. One primary label per record.

| Type | n | Severity | The catch |
|---|---|---|---|
| `drug_allergy_conflict` | 11 | high | order cross-reacts with a charted allergy (e.g. amoxicillin + penicillin allergy) |
| `renal_dose_conflict` | 10 | high | renally-cleared drug at a contraindicated eGFR (**metformin at eGFR 24**) |
| `drug_drug_interaction` | 12 | high/mod | new order interacts with an active home med (NSAID+warfarin, SSRI+tramadol, nitrate+sildenafil) |
| `duplicate_therapy` | 8 | mod | new order duplicates a home med's class (two ACE inhibitors / two statins) |
| `dropped_home_med` | 10 | high/mod | active chart med the patient stopped; plan never addresses it |
| `history_mismatch` | 8 | mod | visit denies a condition that's an active charted problem |
| `drug_condition_conflict` | 4 | high | teratogen prescribed in a charted pregnancy |
| `dropped_result` (temporal) | 5 | high/mod | prior abnormal lab (K 5.8 / INR 4.6 / A1c 9.8) raised but deferred with no follow-up |
| `adverse_drug_event` (**Detector #2**) | 10 | mod | new symptom matches a known ADR of an active med (ACEi cough, statin myalgia, amlodipine edema) |
| clean **control** | 22 | — | no discrepancy; some are near-misses (safe drug in a related class, metformin at normal eGFR) to stress false-positive control |

Every positive label carries **both-sided grounding**:
`transcript_evidence` (a verbatim line from the transcript) **and**
`chart_evidence` (`resource_type` + resolved `resource_id` + `display`), plus an
`explanation`, `severity`, and a drafted `suggested_fix`. Validated: 100% of the 78
positive labels have a verbatim transcript span and a resolvable FHIR resource id.

## Regenerate

```bash
# 1. (only if synthea/output_* is missing) regenerate the real population — needs Java 17+
cd synthea
java -jar synthea-with-dependencies.jar -s 20260718 -p 160 -a 40-90 \
     --exporter.fhir.use_us_core_ig true --generate.only_alive_patients true \
     --exporter.baseDirectory ./output_main California
java -jar synthea-with-dependencies.jar -s 424242 -p 60 -a 20-40 -g F \
     --exporter.fhir.use_us_core_ig true --generate.only_alive_patients true \
     --exporter.baseDirectory ./output_preg California
# 2. build the labeled dataset from the real bundles (deterministic)
cd .. && python3 synthea_to_records.py
```

Synthea is deterministic under its seed, so step 1 reproduces the same population;
step 2 reproduces the same 100 records. The records are self-contained (they embed the
real resources), so the ~1.1 GB `synthea/output_*` can be pruned after step 2 and
regenerated on demand.

## Caveats

- **Fully synthetic.** No PHI — Synthea patients are simulated. RxNorm/SNOMED/LOINC on
  the real resources are Synthea's; codes on injected resources are plausible, not audited.
- **Transcripts are templated** (compact, ~250–400 words) — perfect for building and
  scoring the agent, but plainer than Abridge's hand-crafted 25. An optional **LLM
  "naturalization" pass** (Claude rewrites the transcript to read naturally while
  preserving the planted line + real values verbatim) can be run over the ~10–15 demo
  records — keeping the API budget for the live agent.
- **Injected substrate is labeled as such** (`grounding: injected`) so you can filter to
  the 62/78 fully-real-grounded findings if you want a stricter eval slice.
