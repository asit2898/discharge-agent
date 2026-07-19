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
- `docs/` — ideation, data-pipeline notes
- `data/` — our own 100-record labeled discrepancy eval set + generators
- `synthetic-ambient-fhir-25/` — provided Abridge dataset (25 synthetic ambient +
  FHIR encounters) used as the data substrate
- `backend/discharge_agent/` — FastAPI service: dataset loader → med normalizer →
  Chart Compiler → **orchestrator agent** (`agent.py`, a Claude tool-use loop over the
  grounded KB checks in `checks.py`), with a deterministic no-LLM workflow as fallback
- `frontend/` — Vite + React + TS **Epic Discharge Navigator clone** with the
  Reconciliation Copilot embedded as a SMART-on-FHIR extension panel

## Running the scaffold

Two processes. Backend (port 8000):

```bash
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/uvicorn discharge_agent.main:app --app-dir backend --reload --port 8000
```

Frontend (port 5173, proxies `/api` → 8000):

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:5173. It boots on the **hero discharge** (a hip-fracture ORIF
with new AF + UTI + AKI, four prescribing teams) showing grounded catches, with the
**orchestrator agent's reasoning trace** expandable above the med-rec workspace; the top
switcher also loads the real 25 encounters. With an `ANTHROPIC_API_KEY` present the agent
drives the reconciliation live (deciding which checks to run, investigating the
transcript, drafting each order action); without a key the deterministic workflow produces
the same output shape so the UI works offline.

Set `DISCHARGE_AGENTIC=0` to force the deterministic workflow even with a key.

### API

- `GET /api/encounters` — hero first, then the real 25
- `GET /api/encounters/{id}` — header, transcript, note, AVS, normalized meds
- `GET /api/encounters/{id}/reconcile` — draft med list + ranked flag queue + stats

Built for the Abridge "Future of Agentic AI in Healthcare" hackathon.
