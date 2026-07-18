"""Load and index the Abridge dataset. Pure I/O + light indexing, no clinical logic."""
from __future__ import annotations

import json
from datetime import date, datetime
from functools import lru_cache
from typing import Any, Optional

from . import config

INPATIENT_HINTS = ("admission", "hospital", "inpatient", "skilled nursing", "snf", "hospice")


@lru_cache(maxsize=1)
def load_records() -> dict[str, dict[str, Any]]:
    """Return {record_id: record} for the 25-encounter dataset."""
    records: dict[str, dict[str, Any]] = {}
    if not config.DATASET_JSONL.exists():
        return records
    with config.DATASET_JSONL.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            records[rec["id"]] = rec
    return records


def get_record(record_id: str) -> Optional[dict[str, Any]]:
    return load_records().get(record_id)


def is_inpatient(record: dict[str, Any]) -> bool:
    title = (record.get("metadata", {}).get("visit_title") or "").lower()
    vtype = (record.get("metadata", {}).get("visit_type") or "").lower()
    return any(h in title or h in vtype for h in INPATIENT_HINTS)


def compute_age(birth_date: Optional[str], as_of: Optional[str]) -> Optional[int]:
    if not birth_date:
        return None
    try:
        bd = datetime.fromisoformat(birth_date[:10]).date()
    except ValueError:
        return None
    ref: date
    try:
        ref = datetime.fromisoformat(as_of[:10]).date() if as_of else date(2026, 7, 18)
    except (ValueError, TypeError):
        ref = date(2026, 7, 18)
    return ref.year - bd.year - ((ref.month, ref.day) < (bd.month, bd.day))
