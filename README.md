# discharge-agent

An Abridge-powered agent that **pre-reconciles a patient's discharge medication
list** from three sources — the ambient **transcript** (intent), the **FHIR** record
(system truth), and the **active prescriptions** — surfacing every discrepancy with a
citation back to what was actually said, so a nurse/pharmacist *verifies* instead of
*hunts*.

> Every existing tool has either the **conversation** or the **structured record**.
> We reconcile the two against each other — three-way (transcript ↔ FHIR ↔
> prescriptions), across **multiple prescribers**, with the **transcript quote as the
> evidence** for each flag.

See [`PROJECT.md`](./PROJECT.md) for the full brief: the validated problem, the
pharmacist-absence gap, the multi-specialist hero scenario, the Epic (SMART on FHIR)
integration story, and the competitive landscape.

## Repo layout

- `PROJECT.md` — project brief / pitch
- `synthetic-ambient-fhir-25/` — provided Abridge dataset (25 synthetic ambient +
  FHIR encounters) used as the data substrate

Built for the Abridge "Future of Agentic AI in Healthcare" hackathon.
