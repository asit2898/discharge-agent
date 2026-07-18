"""Discharge reconciliation copilot — backend package.

A thin FastAPI service that (1) loads the Abridge synthetic-ambient-FHIR dataset,
(2) normalizes each encounter's medications into a common shape, and (3) serves a
*stub* reconciliation so the Epic Discharge Navigator clone + embedded copilot renders
end-to-end today. The stub emits flags in the same taxonomy as the labeled eval set
(`data/`), so the real safety-catch engine can be swapped in behind the same contract.
"""

__version__ = "0.1.0"
