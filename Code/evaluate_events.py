"""
evaluate_events.py -- score a rally_events CSV against the hand-labeled
ground-truth set (ground_truth_events.csv).

Matching is one-to-one: each ground-truth event can be claimed by at most
one predicted event (closest-in-time first), within TOLERANCE frames.
Only predictions inside the labeled span (first GT frame - tol .. last GT
frame + tol) are scored, since the rest of the clip is unlabeled.

Reports, for both "frame-only" and "frame + event type" matching:
  recall    = matched GT / total GT
  precision = matched predictions / predictions inside the labeled span
  F1

Usage:
  python evaluate_events.py <rally_events.csv> [ground_truth.csv] [--tol N] [-v]
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

DEFAULT_GT = Path(__file__).resolve().parent.parent / "ground_truth_events.csv"
DEFAULT_TOLERANCE = 5


def _match(gt, pred, tol, require_type):
    """Greedy global matching on |frame difference|, smallest first."""
    pairs = []
    for gi, g in gt.iterrows():
        for pi, p in pred.iterrows():
            d = abs(int(g["frame"]) - int(p["frame"]))
            if d > tol:
                continue
            if require_type and g["event_type"] != p["event_type"]:
                continue
            pairs.append((d, gi, pi))
    pairs.sort()
    used_g, used_p, matches = set(), set(), []
    for d, gi, pi in pairs:
        if gi in used_g or pi in used_p:
            continue
        used_g.add(gi)
        used_p.add(pi)
        matches.append((gi, pi, d))
    return matches


def evaluate(pred_path, gt_path=DEFAULT_GT, tol=DEFAULT_TOLERANCE, verbose=False):
    gt = pd.read_csv(gt_path)[["frame", "event_type"]].reset_index(drop=True)
    pred = pd.read_csv(pred_path)
    pred = pred[["frame", "event_type"]].drop_duplicates().reset_index(drop=True)

    lo, hi = gt["frame"].min() - tol, gt["frame"].max() + tol
    pred = pred[(pred["frame"] >= lo) & (pred["frame"] <= hi)].reset_index(drop=True)

    results = {}
    for label, require_type in (("frame_only", False), ("frame_and_type", True)):
        m = _match(gt, pred, tol, require_type)
        recall = len(m) / len(gt) if len(gt) else 0.0
        precision = len(m) / len(pred) if len(pred) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        results[label] = {"matched": len(m), "gt": len(gt), "pred": len(pred),
                          "recall": recall, "precision": precision, "f1": f1,
                          "matches": m}

    # Per-type recall (type-strict)
    typed = results["frame_and_type"]["matches"]
    per_type = {}
    for t, grp in gt.groupby("event_type"):
        hit = sum(1 for gi, _, _ in typed if gt.loc[gi, "event_type"] == t)
        per_type[t] = (hit, len(grp))
    results["per_type"] = per_type

    if verbose:
        loose = {gi: pi for gi, pi, _ in results["frame_only"]["matches"]}
        strict = {gi for gi, _, _ in typed}
        print("\n GT frame  GT type   -> predicted")
        for gi, g in gt.iterrows():
            if gi in strict:
                pi = next(p for g2, p, _ in typed if g2 == gi)
                tag = f"OK      {pred.loc[pi, 'event_type']}@{pred.loc[pi, 'frame']}"
            elif gi in loose:
                pi = loose[gi]
                tag = f"TYPE?   {pred.loc[pi, 'event_type']}@{pred.loc[pi, 'frame']}"
            else:
                tag = "MISSED"
            print(f" {g['frame']:>7}  {g['event_type']:<8}  {tag}")
        matched_p = {pi for _, pi, _ in typed}
        fps = pred[~pred.index.isin(matched_p)]
        print(f"\n Unmatched predictions ({len(fps)}): "
              + ", ".join(f"{r.event_type}@{r.frame}" for r in fps.itertuples()))

    return results


def print_summary(name, r):
    fo, ft = r["frame_only"], r["frame_and_type"]
    pt = "  ".join(f"{t}: {h}/{n}" for t, (h, n) in r["per_type"].items())
    print(f"{name}\n"
          f"  frame-only     : recall {fo['matched']}/{fo['gt']} = {fo['recall']:.0%}  "
          f"precision {fo['matched']}/{fo['pred']} = {fo['precision']:.0%}  F1 {fo['f1']:.2f}\n"
          f"  frame + type   : recall {ft['matched']}/{ft['gt']} = {ft['recall']:.0%}  "
          f"precision {ft['matched']}/{ft['pred']} = {ft['precision']:.0%}  F1 {ft['f1']:.2f}\n"
          f"  per-type recall: {pt}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("pred")
    ap.add_argument("gt", nargs="?", default=str(DEFAULT_GT))
    ap.add_argument("--tol", type=int, default=DEFAULT_TOLERANCE)
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    res = evaluate(a.pred, a.gt, a.tol, a.verbose)
    print_summary(a.pred, res)
    sys.exit(0)
