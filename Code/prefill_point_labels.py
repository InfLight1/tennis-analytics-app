"""
prefill_point_labels.py -- a first draft of a match's point labels, written
from what the app called, so labeling a new match means CHECKING rows
instead of stepping through every frame.

Input: the job's rally_events_resolved.csv (download it with
  curl -H "X-Passcode: <code>" <url>/api/debug/<job>/rally_events_resolved.csv).
Output: a CSV in the ground_truth_points.csv format (one row per serve
attempt, two serves count) plus two helper columns:
  video_time  where the point starts in the video (m:ss), to jump there
  check       empty; write "ok" or fix the row while watching

The draft is the APP'S guess. Never score the app against an unchecked
draft: score_test_set.py refuses files that still have empty check cells.

Usage:
  python prefill_point_labels.py <rally_events_resolved.csv> <out.csv> [--fps 30]
"""

import argparse

import pandas as pd

import rally_outcomes
from evaluate_rally_outcomes import _pipeline_ending

FIELDS = ["point_id", "start_frame", "end_frame", "server", "winner", "ending", "video_time", "check"]


def _mmss(frame, fps):
    s = int(frame / fps)
    return f"{s // 60}:{s % 60:02d}"


def prefill(events_path, fps):
    ev = pd.read_csv(events_path)
    out = rally_outcomes.rally_outcomes(ev)
    spans = ev.groupby("rally_id").agg(start=("frame", "min"), end=("frame", "max")).reset_index()
    out = out.merge(spans, on="rally_id").sort_values("start")
    out = out[out["reason"] != "no_hit_detected"]

    rows = []
    for i, r in enumerate(out.itertuples(), start=1):
        ending = _pipeline_ending(r._asdict())
        winner = r.winner if r.winner in ("near", "far") else ""
        if not winner and r.reason in ("first_serve_fault", "serve_fault_unconfirmed") \
                and r.server in ("near", "far"):
            winner = "far" if r.server == "near" else "near"
        rows.append({
            "point_id": i, "start_frame": int(r.start), "end_frame": int(r.end),
            "server": r.server if r.server in ("near", "far") else "",
            # a first-serve fault gives nobody the point; the label still
            # records who "won" that serve attempt (the receiver)
            "winner": winner,
            "ending": ending if ending in ("winner", "net", "long", "wide") else "other",
            "video_time": _mmss(r.start, fps), "check": "",
        })
    return pd.DataFrame(rows, columns=FIELDS)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("events")
    ap.add_argument("out")
    ap.add_argument("--fps", type=float, default=30.0)
    a = ap.parse_args()
    df = prefill(a.events, a.fps)
    df.to_csv(a.out, index=False)
    blanks = int((df["winner"] == "").sum())
    print(f"{len(df)} serve attempts written to {a.out} ({blanks} with no winner called: fill those in).")
