"""
diagnose_segmentation.py (v2)

Runs your REAL analysis.run_analysis() locally against the match_data.csv
pulled from job 76a383379d90, and compares the result to what the job
actually produced (rally_events_stable.csv). This tells us whether the bug
is reproducible locally (real logic bug, dig deeper) or NOT reproducible
(meaning the code/config that ran on Modal differs from what's on disk now
-- a deploy/config mismatch, not a logic bug).

Usage:
    python diagnose_segmentation.py match_data.csv
"""

import sys
import pandas as pd

MATCH_CSV = sys.argv[1] if len(sys.argv) > 1 else "match_data.csv"
LOCAL_OUTPUT = "local_rerun_rally_events.csv"

# Known dead zones: real, continuous ball detection confirmed present, but
# ZERO events in the job's actual rally_events_stable.csv output.
DEAD_ZONES = [
    ("gap before modal rally 2", 282, 387),
    ("gap after modal rally 2 / before modal rally 3", 415, 868),
    ("gap after modal rally 3 / before modal rally 4", 954, 2207),
]

print("=" * 70)
print("Running the REAL analysis.run_analysis() locally")
print("=" * 70)
import analysis

events_df, rallies = analysis.run_analysis(MATCH_CSV, output_path=LOCAL_OUTPUT)

print()
print("=" * 70)
print(f"Local rerun produced {len(rallies)} final rallies. Checking dead zones:")
print("=" * 70)
for name, lo, hi in DEAD_ZONES:
    hits = [r for r in rallies if not (r[1] < lo or r[0] > hi)]
    print(f"  {name} ({lo}-{hi}): {hits if hits else 'STILL NONE FOUND (bug reproduced locally)'}")

print()
print("=" * 70)
print("Full list of local rally boundaries (for manual comparison against")
print("the job's rally_events_stable.csv rally_start_frame/rally_end_frame):")
print("=" * 70)
for r in rallies:
    print(" ", r)

print()
print("=" * 70)
print("READ THIS")
print("=" * 70)
print("""
- If the dead zones are STILL empty above -> reproduced locally. This is a
  real bug in run_analysis()'s pipeline (segment_rallies -> merge -> detect_bounces/
  detect_hits -> split_on_event_gap -> min_sub_rally_length filter), and we can
  now add print statements inside those stages and re-run instantly, without
  touching Modal at all.

- If the dead zones NOW show rallies that the job's real output didn't have ->
  this exact match_data.csv + this exact local analysis.py code does NOT
  reproduce what shipped from Modal. That means the deployed cpu_image is
  running different code or a different config.py value (e.g. RALLY_GAP_FRAMES,
  MIN_RALLY_LENGTH_FRAMES, EVENT_GAP_SPLIT_FRAMES) than what's on disk right
  now -- check for an un-redeployed local fix, or a config value that differs
  between local config.py and whatever got baked into the last `modal deploy`.
""")

print()
print("=" * 70)
print("BONUS — source of load_data(), and a frame-by-frame trace of what")
print("happens to frames 275-412 (the window straddling the first two")
print("modal rallies) as load_data() processes them")
print("=" * 70)
import inspect
try:
    print(inspect.getsource(analysis.load_data))
except Exception as e:
    print(f"(could not get source: {e})")

print()
print("--- ball_df returned by load_data(), frames 275-412 ---")
ball_df, player_df = analysis.load_data(MATCH_CSV)
cols = [c for c in ["frame", "table_x", "table_y", "has_position", "pixel_x", "pixel_y"] if c in ball_df.columns]
window = ball_df[(ball_df["frame"] >= 275) & (ball_df["frame"] <= 412)][cols]
print(window.to_string(index=False))

print()
print("=" * 70)
print("BONUS 2 — source of smooth_trajectory(), and has_position after it")
print("runs, for frames 275-412")
print("=" * 70)
try:
    print(inspect.getsource(analysis.smooth_trajectory))
except Exception as e:
    print(f"(could not get source: {e})")

smoothed = analysis.smooth_trajectory(ball_df)
cols2 = [c for c in ["frame", "table_x", "table_y", "has_position", "pixel_x", "pixel_y"] if c in smoothed.columns]
print()
print("--- ball_df AFTER smooth_trajectory(), frames 275-412 ---")
print(smoothed[(smoothed["frame"] >= 275) & (smoothed["frame"] <= 412)][cols2].to_string(index=False))

# per-frame table_x displacement, to quantify the suspicious speed jump directly
print()
print("--- per-frame table_x displacement, frames 280-300 (pre-smoothing, raw) ---")
raw_window = ball_df[(ball_df["frame"] >= 280) & (ball_df["frame"] <= 300)].reset_index(drop=True)
raw_window["dx"] = raw_window["table_x"].diff()
raw_window["dy"] = raw_window["table_y"].diff()
print(raw_window[["frame", "table_x", "table_y", "dx", "dy"]].to_string(index=False))
