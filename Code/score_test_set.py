"""
score_test_set.py -- one accuracy number over every labeled match, split
into matches used for tuning ("train") and matches the app has never been
tuned on ("test"). Only the "test" number may be claimed publicly.

Manifest (CSV, one row per match):
  match_id,date,role,type,court,spot,events,truth
  m01,2026-11-01,train,singles,Home courts,fence-high,m01/rally_events_resolved.csv,m01/points.csv
Paths are relative to the manifest's folder. role = train | test.
type = singles | doubles. Truth files are ground_truth_points.csv format;
a truth file with a "check" column must have every row checked.

Usage:
  python score_test_set.py <matches.csv> [-v]
"""

import argparse
import contextlib
import io
from pathlib import Path

import pandas as pd

from evaluate_rally_outcomes import evaluate


def _checked(truth_path):
    t = pd.read_csv(truth_path)
    if "check" not in t.columns:
        return True
    return t["check"].fillna("").astype(str).str.strip().ne("").all()


def score(manifest, verbose=False):
    base = Path(manifest).resolve().parent
    m = pd.read_csv(manifest)
    rows = []
    for r in m.itertuples():
        truth = base / r.truth
        if not _checked(truth):
            print(f"  {r.match_id}: SKIPPED, labels not fully checked yet")
            continue
        quiet = io.StringIO()
        with contextlib.redirect_stdout(quiet):
            df = evaluate(base / r.events, truth)
        if verbose:
            print(quiet.getvalue())
        rows.append({"match": r.match_id, "role": r.role, "type": r.type, "court": r.court,
                     "spot": r.spot, "right": int(df["winner_ok"].sum()), "points": len(df)})
    res = pd.DataFrame(rows)
    if res.empty:
        print("No checked matches yet.")
        return res
    res["pct"] = (100 * res["right"] / res["points"]).round(0).astype(int)
    print(res.to_string(index=False))
    print()
    for role in ("test", "train"):
        g = res[res["role"] == role]
        if len(g):
            right, pts = int(g["right"].sum()), int(g["points"].sum())
            print(f"{role.upper():5}  {right} of {pts} points right ({100 * right / pts:.0f}%) "
                  f"over {len(g)} match{'es' if len(g) != 1 else ''}")
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    score(a.manifest, a.verbose)
