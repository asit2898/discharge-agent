# discharge-agent

An Abridge-powered agent that does the tedious **prep** for discharge medication
reconciliation: it **pre-populates** a draft reconciled list from every source (home
meds, inpatient orders, and the ambient **transcript**), then **surfaces exactly
where the sources disagree** — each conflict shown side-by-side with the transcript
quote and prescriber as evidence. The clinician still makes every call; we just turn
*"assemble the picture from scratch, then decide"* into *"the picture is already
assembled and the disagreements are highlighted — decide."*

**Decision support, not decision replacement.** We make the decision easy, not the
decision.

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
