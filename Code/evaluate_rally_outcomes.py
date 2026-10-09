"""
evaluate_rally_outcomes.py -- score the pipeline's per-point outcomes (the
input to prioritization, i.e. the product's differentiator) against
ground_truth_points.csv from label_rally_outcomes.py.

Input: a rally_events_resolved.csv (player_side already near/far -- written
by modal_app.run_cpu_pipeline_remote / run_real_report.py). Outcomes are
recomputed with rally_outcomes.rally_outcomes() so this always measures
the current code.

Each labeled point is matched to the pipeline rallies overlapping it
(+/- SLACK frames); the rally with the most overlap is "its" rally. Reports:
  found        labeled points with any overlapping pipeline rally
  fragmented   labeled points split across >1 pipeline rally
  decided      found points whose rally got a winner (not ambiguous/no-hit)
  winner OK    decided points with the right winner (near/far)
  ending OK    decided points with the right ending (winner/net/long/wide)
  server OK    found points whose first hit side = labeled server
  END-TO-END   points with the right winner / ALL labeled points
               (the number the diagnosis actually depends on)

Usage:
  python evaluate_rally_outcomes.py <rally_events_resolved.csv> [ground_truth_points.csv] [-v]
"""

import argparse
from pathlib import Path

import pandas as pd

import rally_outcomes

DEFAULT_GT = Path(__file__).resolve().parent.parent / "ground_truth_points.csv"
SLACK = 30
GT_SERVE_ONLY_MAX_FRAMES = 40   # labeled serve-only points are <= 22 frames; real rallies >= 48
ENDING_MAP = {"opponent_no_return": "winner"}   # opponent_error -> its error_type


def _pipeline_ending(row):
    if row["reason"] in ("opponent_error", "first_serve_fault", "serve_fault_unconfirmed"):
        return row["error_type"] if row["error_type"] in ("net", "long", "wide") else "unclassified"
    return ENDING_MAP.get(row["reason"])


def gt_first_serve_faults(gt, fps=None):
    """Which labeled rows are first-serve faults under two-serve rules
    (rally_outcomes.TWO_SERVES): a serve-only point lost by the server on a
    net/long/wide, with the same server serving the next labeled point
    within SECOND_SERVE_MAX_GAP_S -- unless it is itself the second serve."""
    fps = fps or rally_outcomes.config.TRACKER_FRAME_RATE
    max_gap = rally_outcomes.SECOND_SERVE_MAX_GAP_S * fps
    g = gt.sort_values("start_frame").reset_index(drop=True)
    fault = ((g["end_frame"] - g["start_frame"] <= GT_SERVE_ONLY_MAX_FRAMES)
             & g["ending"].isin(["net", "long", "wide"]) & (g["winner"] != g["server"]))
    first = pd.Series(False, index=g.index)
    pending = None
    for i in g.index:
        if fault[i]:
            if pending is not None and pending[0] == g.at[i, "server"] \
                    and g.at[i, "start_frame"] - pending[1] <= max_gap:
                pending = None
                continue
            if i + 1 in g.index and g.at[i + 1, "server"] == g.at[i, "server"] \
                    and g.at[i + 1, "start_frame"] - g.at[i, "end_frame"] <= max_gap:
                first[i] = True
                pending = (g.at[i, "server"], g.at[i, "end_frame"])
                continue
        pending = None
    return dict(zip(g["point_id"], first))


def evaluate(events_path, gt_path=DEFAULT_GT, verbose=False):
    gt = pd.read_csv(gt_path)
    first_fault = gt_first_serve_faults(gt) if rally_outcomes.TWO_SERVES else {}
    ev = pd.read_csv(events_path)
    out = rally_outcomes.rally_outcomes(ev)
    spans = ev.groupby("rally_id").agg(start=("frame", "min"), end=("frame", "max")).reset_index()
    out = out.merge(spans, on="rally_id")

    rows = []
    for p in gt.itertuples():
        lo, hi = p.start_frame - SLACK, p.end_frame + SLACK
        ov = out[(out["end"] >= lo) & (out["start"] <= hi)].copy()
        ov["overlap"] = ov.apply(lambda r: min(r["end"], hi) - max(r["start"], lo), axis=1)
        real = ov[ov["reason"] != "no_hit_detected"]
        best = (real if len(real) else ov).sort_values("overlap", ascending=False).head(1)
        r = best.iloc[0] if len(best) else None
        decided = r is not None and r["reason"] in ("opponent_no_return", "opponent_error") \
            and r["winner"] in ("near", "far")
        is_first = bool(first_fault.get(p.point_id, False))
        rows.append({
            "point": p.point_id, "frames": f"{p.start_frame}-{p.end_frame}",
            "gt_server": p.server, "gt_winner": p.winner, "gt_ending": p.ending,
            "found": r is not None, "n_rallies": len(real),
            "rally": None if r is None else int(r["rally_id"]),
            "reason": None if r is None else r["reason"],
            "server": None if r is None else r["server"],
            "winner": None if r is None else r["winner"],
            "ending": None if r is None else _pipeline_ending(r),
            "decided": decided,
            "gt_first_fault": is_first,
        })
    df = pd.DataFrame(rows)
    # A labeled first-serve fault is right when the pipeline also calls it a
    # first-serve fault (no point awarded); anything else needs the winner.
    pipe_first = df["reason"].isin(["first_serve_fault", "serve_fault_unconfirmed"])
    df["decided"] = df["decided"] | pipe_first
    df["winner_ok"] = (df["gt_first_fault"] & pipe_first) | \
        (~df["gt_first_fault"] & ~pipe_first & df["decided"] & (df["winner"] == df["gt_winner"]))
    df["ending_ok"] = df["decided"] & (df["ending"] == df["gt_ending"])
    df["server_ok"] = df["found"] & (df["server"] == df["gt_server"])

    n = len(df)
    found, dec = df["found"].sum(), df["decided"].sum()
    known_end = df["decided"] & (df["gt_ending"] != "other")

    def pct(a, b):
        return f"{a}/{b} ({100 * a / b:.0f}%)" if b else f"{a}/0"

    print(f"Rally outcomes vs {Path(gt_path).name} ({n} labeled points)")
    print(f"  found        {pct(found, n)}")
    print(f"  fragmented   {pct(int((df['n_rallies'] > 1).sum()), int(found))}")
    print(f"  decided      {pct(int(dec), int(found))}   (rest: ambiguous / no hit / unknown opponent)")
    print(f"  winner OK    {pct(int(df['winner_ok'].sum()), int(dec))}")
    print(f"  ending OK    {pct(int((df['ending_ok'] & known_end).sum()), int(known_end.sum()))}")
    print(f"  server OK    {pct(int(df['server_ok'].sum()), int(found))}")
    print(f"  END-TO-END   {pct(int(df['winner_ok'].sum()), n)}  <- points the diagnosis gets right")
    if first_fault:
        nf = int(df["gt_first_fault"].sum())
        print(f"    of which   first-serve faults {pct(int((df['winner_ok'] & df['gt_first_fault']).sum()), nf)}, "
              f"real points {pct(int((df['winner_ok'] & ~df['gt_first_fault']).sum()), n - nf)}")
    if verbose:
        print()
        print(df[["point", "frames", "gt_server", "gt_winner", "gt_ending", "gt_first_fault", "rally", "n_rallies",
                  "reason", "server", "winner", "ending"]].to_string(index=False))
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("events")
    ap.add_argument("gt", nargs="?", default=str(DEFAULT_GT))
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    evaluate(a.events, a.gt, a.verbose)
