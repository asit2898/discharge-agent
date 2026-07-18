"""Offline eval harness — the quantitative story.

Run the engine on the hero (and any labeled sample) and JOIN its derived flags to the
answer key by (type, drug), reporting precision / recall / F1 per type. The engine under
test NEVER reads the labels — this module is the only place they are opened.

    python -m discharge_agent.eval            # hero case
    python -m discharge_agent.eval --verbose  # + per-flag match detail
"""
from __future__ import annotations

import json
import sys

from . import hero, kb
from .engine import reconcile


def _norm_drug(name: str | None) -> str | None:
    return kb.resolve_drug(name) if name else None


# Relationship / visit-level flags aren't about one specific drug — the "lead" drug in
# the med_name is arbitrary (a pair or a service conflict), so match these on type alone.
_TYPE_ONLY = {"cross_prescriber_conflict", "history_mismatch", "dropped_result"}


def _match(pred, gold) -> bool:
    """A predicted flag matches a label if the type agrees and the drug (KB-resolved)
    agrees — or the type is relationship/visit-level, where type alone suffices."""
    if pred.type != gold.get("type"):
        return False
    if pred.type in _TYPE_ONLY:
        return True
    pd, gd = _norm_drug(pred.med_name), _norm_drug(gold.get("med_name"))
    if pd is None and gd is None:
        return True
    return pd == gd


def evaluate(record_id: str, labels: list[dict], verbose: bool = False) -> dict:
    recon = reconcile(record_id)
    preds = recon.flags
    matched_labels: set[int] = set()
    tp = 0
    for p in preds:
        hit = next((i for i, g in enumerate(labels)
                    if i not in matched_labels and _match(p, g)), None)
        if hit is not None:
            matched_labels.add(hit)
            tp += 1
            if verbose:
                print(f"  ✓ TP  {p.type:<24} {p.med_name}")
        elif verbose:
            print(f"  ✗ FP  {p.type:<24} {p.med_name}")
    fp = len(preds) - tp
    fn = len(labels) - len(matched_labels)
    if verbose:
        for i, g in enumerate(labels):
            if i not in matched_labels:
                print(f"  ✗ FN  {g['type']:<24} {g.get('med_name')}")
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1,
            "n_pred": len(preds), "n_gold": len(labels)}


def main() -> None:
    verbose = "--verbose" in sys.argv
    labels = json.loads((hero._LABELS_PATH).read_text())["discrepancies"]
    print(f"=== Hero eval — {hero.HERO_ID} ===")
    m = evaluate(hero.HERO_ID, labels, verbose=verbose)
    print(f"\npredicted={m['n_pred']}  gold={m['n_gold']}  TP={m['tp']} FP={m['fp']} FN={m['fn']}")
    print(f"precision={m['precision']:.2f}  recall={m['recall']:.2f}  F1={m['f1']:.2f}")


if __name__ == "__main__":
    main()
