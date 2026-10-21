"""
test_rally_outcomes.py

Rules added 2026-10-21 (accuracy pass), on small hand-made rallies:
1. A serve that lands out is a fault even if the receiver swats the ball back.
2. A "fault" followed by a real rally (3+ hits) is a misread bounce, not a fault.
3. A near-player serve clearly past the far service line is long.
4. An unreturned single shot from the wrong end mid service game is the ball
   being hit back to the server between points (no point).

Run directly:
    python Code/test_rally_outcomes.py
"""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rally_outcomes as ro  # noqa: E402

FAILED = []


def check(name, ok):
    print(("PASS  " if ok else "FAIL  ") + name)
    if not ok:
        FAILED.append(name)


def ev(rally, frame, kind, side=None, x=None, y=None, in_bounds=None):
    return {"rally_id": rally, "frame": frame, "event_type": kind, "player_side": side,
            "table_x": x, "table_y": y, "in_bounds": in_bounds, "has_hit": True}


def outcomes(rows):
    return ro.rally_outcomes(pd.DataFrame(rows)).set_index("rally_id")


if __name__ == "__main__":
    # 1. far serve lands behind the near service line, receiver swats it into the net
    o = outcomes([ev(1, 100, "hit", "far", 3000, 100), ev(1, 128, "bounce", None, 417, 210, True),
                  ev(1, 138, "hit", "near", 166, -10), ev(1, 157, "net", None, 1188)])
    check("swatted-back fault is a serve fault", bool(o.loc[1, "serve_fault"]) and o.loc[1, "error_type"] == "long")

    # 2. same first bounce, but play goes on for several shots
    o = outcomes([ev(1, 100, "hit", "far", 3000, 100), ev(1, 128, "bounce", None, 417, 210, True),
                  ev(1, 138, "hit", "near", 166, 300), ev(1, 170, "bounce", None, 2000, 300, True),
                  ev(1, 190, "hit", "far", 2400, 300), ev(1, 220, "bounce", None, 3000, 300, False)])
    check("rally after a 'fault' is played out (far hit long -> near wins)",
          not o.loc[1, "serve_fault"] and o.loc[1, "winner"] == "near")

    # 3. near serve bouncing 2.3 m past the far service line, nobody touches it
    o = outcomes([ev(1, 100, "hit", "near", 0, 600), ev(1, 127, "bounce", None, 2061, 595, True)])
    check("clearly long near-player serve is a fault", o.loc[1, "error_type"] == "long" and pd.isna(o.loc[1, "winner"]))
    o = outcomes([ev(1, 100, "hit", "near", 0, 600), ev(1, 125, "bounce", None, 1608, 638, True)])
    check("near-player serve inside the box is not a fault", not o.loc[1, "serve_fault"])

    # 4. near player's service game with two far "aces" in the middle
    rows, f = [], 0
    for rid, server in enumerate(["near", "near", "far", "near", "far", "near", "near"], start=1):
        if server == "far":
            rows += [ev(rid, f, "hit", "far", 3000, 300), ev(rid, f + 25, "bounce", None, 700, 300, True)]
        else:
            rows += [ev(rid, f, "hit", "near", 0, 600), ev(rid, f + 25, "bounce", None, 1600, 300, True),
                     ev(rid, f + 50, "hit", "far", 2400, 300), ev(rid, f + 80, "bounce", None, 3000, 300, False)]
        f += 600
    o = outcomes(rows)
    check("between-point knock-backs give no point",
          list(o.loc[[3, 5], "reason"]) == ["between_points", "between_points"])
    check("real points around them are kept", o.loc[[1, 2, 4, 6, 7], "winner"].eq("near").all())

    print("\nAll rally-outcome checks passed." if not FAILED else f"\n{len(FAILED)} check(s) FAILED")
    sys.exit(1 if FAILED else 0)
