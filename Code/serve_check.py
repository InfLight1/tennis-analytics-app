"""serve_check.py -- serve stats vs ground_truth_points.csv (2026-10-07).
Each labeled row is one serve attempt; a short serve-only row ending in
net/long/wide is a fault. Compares serves seen / in / faults and first-serve %
per end (near/far) over the labeled span.
Usage: python serve_check.py <rally_events_resolved.csv> [ground_truth_points.csv] [-v]"""
import sys
import pandas as pd
import rally_outcomes as ro
from evaluate_rally_outcomes import GT_SERVE_ONLY_MAX_FRAMES, DEFAULT_GT

def truth_attempts(gt):
    g = gt.sort_values("start_frame").reset_index(drop=True)
    fault = (g["end_frame"] - g["start_frame"] <= GT_SERVE_ONLY_MAX_FRAMES) & g["ending"].isin(["net", "long", "wide"]) \
        & (g["winner"] != g["server"])
    att, prev = [], None
    for i in g.index:
        second = prev is not None and prev[0] == g.at[i, "server"] and prev[1] and prev[2] == 1 \
            and g.at[i, "start_frame"] - prev[3] <= ro.SECOND_SERVE_MAX_GAP_S * 30
        a = 2 if second else 1
        att.append(a); prev = (g.at[i, "server"], bool(fault[i]), a, g.at[i, "end_frame"])
    return pd.DataFrame({"start_frame": g["start_frame"], "server": g["server"],
                         "result": ["fault" if f else "in" for f in fault], "attempt": att})

def summary(df):
    out = {}
    for side, d in df.groupby("server"):
        known = d[d["result"] != "unknown"]
        first = known[known["attempt"] == 1]
        out[side] = dict(seen=len(d), known=len(known), in_=int((known.result == "in").sum()),
                         faults=int((known.result == "fault").sum()),
                         first_in_pct=round(100 * (first.result == "in").mean()) if len(first) else None)
    return out

if __name__ == "__main__":
    ev = pd.read_csv(sys.argv[1])
    gt = pd.read_csv(sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else DEFAULT_GT)
    lo, hi = gt["start_frame"].min() - 30, gt["end_frame"].max() + 30
    att = ro.serve_attempts(ro.rally_outcomes(ev))
    att = att[(att.start_frame >= lo) & (att.start_frame <= hi)]
    print("truth   :", summary(truth_attempts(gt)))
    print("pipeline:", summary(att))
    if "-v" in sys.argv:
        print(att.to_string())
