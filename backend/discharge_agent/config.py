"""Paths and small runtime config. No secrets here."""
from __future__ import annotations

import os
from pathlib import Path

# repo root = two levels up from this file (backend/discharge_agent/config.py)
REPO_ROOT = Path(__file__).resolve().parents[2]

# The Abridge-provided dataset (25 real encounters, our data substrate).
DATASET_JSONL = REPO_ROOT / "synthetic-ambient-fhir-25" / "synthetic-ambient-fhir-25.jsonl"

# Our own labeled discrepancy sample (drop-in for the future real engine + eval).
SAMPLE_JSONL = REPO_ROOT / "data" / "samples" / "discrepancy-check-sample.jsonl"
SAMPLE_LABELS = REPO_ROOT / "data" / "samples" / "discrepancy-check-sample.labels.jsonl"

# CORS origin for the Vite dev server.
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")
