"""
find_trailing_bounce.py

PROPOSED PATCH for analysis.py -- addresses the rally-window truncation bug
found 2026-09-13: when a rally's last classified event is a hit, the rally's
frame window (rally_end_frame) stops at that hit, so any bounce that occurs
afterward -- even when the raw ball trajectory data makes it geometrically
obvious -- is never scanned and the rally is left permanently 'ambiguous'.

Confirmed on real data (rally 6, rally 16 in tennis1_clip2.mp4): both have
dense, continuous, real post-hit ball trajectories showing an unambiguous
resolution (an explicit out-of-bounds crossing / a clean position reversal)
within ~100-160 frames of the last hit -- entirely outside the previously-
scanned window.

This module does NOT touch prominence thresholds (those were correctly
re-derived already). It extends the SEARCH WINDOW forward from the last hit
before giving up, using two checks in order of cheapness/reliability:

  1. Geometric out-of-bounds crossing -- if the raw trajectory ever crosses
     a court boundary after the last hit, that's a resolvable 'out' call
     with no peak-detection needed at all (rally 6's case).
  2. Peak-detection reversal (scipy.find_peaks) on the extended window, same
     method already used elsewhere, just given a wider look than before
     (rally 16's case: a clean reversal existed, just past the old window).

If neither resolves before ball detection has a genuine gap larger than
TRAILING_BOUNCE_MAX_GAP_FRAMES, this correctly returns None -- the rally
stays 'ambiguous', honestly, rather than fabricating a call (rally 5's
case: a real 537-frame detection blackout should NOT be papered over).

Integration point: call this from wherever analysis.py currently finalizes
a rally that ends on an unmatched hit (i.e. exactly the condition
rally_outcomes.py currently reports as reason='ambiguous' with
last_event_type='hit'). On a resolved result, append a new bounce row to
that rally's events with pos_source='trailing_window_extension' so it
stays visibly distinct from a normally-detected bounce -- same
surface-don't-silently-hide principle as `estimated` / `has_hit`.
"""

import numpy as np
import pandas as pd
import config

# Max gap (frames) between consecutive real ball detections while still
# extending the search window forward. Reuses the same order of magnitude
# as EVENT_GAP_SPLIT_FRAMES (real inter-rally gaps start at >=100 frames;
# real intra-point gaps top out well under that) so a genuine end-of-point
# blackout (e.g. rally 5's 537-frame gap) still correctly bails out rather
# than being bridged. ESTIMATED -- not yet cross-checked against a larger
# ground-truth set beyond this session's 3 cases.
TRAILING_BOUNCE_MAX_GAP_FRAMES = getattr(config, "EVENT_GAP_SPLIT_FRAMES", 90)

# How far forward (frames) we're willing to keep extending in total, even
# if every individual gap is small -- a safety cap so this can't silently
# absorb the start of the NEXT rally if gaps all happen to be short.
TRAILING_BOUNCE_MAX_TOTAL_FRAMES = 400


def _out_of_bounds_frame(window_df):
    """First row (in frame order) where the raw table position is outside
    the court rectangle PLUS config.OFF_TABLE_MARGIN -- the same tolerance
    the rest of the pipeline uses for in/out calls (reprojection error
    means a point just past the raw line isn't a confirmed 'out' by this
    pipeline's own standard). Returns that row, or None."""
    margin = config.OFF_TABLE_MARGIN
    oob = window_df[
        (window_df["table_x"] < -margin) | (window_df["table_x"] > config.TABLE_W + margin)
        | (window_df["table_y"] < -margin) | (window_df["table_y"] > config.TABLE_H + margin)
    ]
    if len(oob) == 0:
        return None
    return oob.iloc[0]


# NOTE: an earlier draft of this module also tried a hand-rolled
# find_peaks-based reversal detector here, extending the same idea to
# catch cases like rally 16 (a real, cleanly-reversing trajectory) without
# needing an explicit out-of-bounds crossing. It was DROPPED after testing
# against real data: on rally 5's window, a single-frame misdetection
# (frame 4698: table_x/y jump to 133/-30 for exactly one frame, then snap
# back, same confidence as its stable neighbors) was read as a genuine
# reversal peak -- a false positive a real Savgol-smoothing pass would
# filter out but a raw find_peaks call over unsmoothed match_data does
# not. Reimplementing that smoothing safely (rather than re-deriving a
# parallel, less-tested copy of it here) is a real piece of work, not a
# quick add. See the module docstring's integration note: the right fix
# is to re-run analysis.py's OWN already-validated detect_bounces() over
# the extended window, not to duplicate its logic in this module.


def find_trailing_bounce(ball_df, last_hit_frame):
    """
    ball_df: raw per-frame ball rows (frame, table_x, table_y, ...), NOT
        limited to the current rally window -- must include frames after
        last_hit_frame.
    last_hit_frame: the frame of the rally's final (unmatched) hit.

    Returns a dict describing a resolved OUT call, or None if nothing
    resolves before a genuine gap/cap is hit (stays ambiguous, honestly):
        {"frame": int, "table_x": float, "table_y": float,
         "in_bounds": False, "method": "out_of_bounds_crossing"}

    Only handles the out-of-bounds-crossing case. Does NOT attempt bounce
    detection via position reversal -- that needs analysis.py's real,
    Savgol-smoothed detect_bounces() re-run over the extended window, not
    a parallel reimplementation here (see note above _out_of_bounds_frame).
    A rally that resolves via a clean in-bounds bounce past the old
    window (rally 16's case) is NOT yet fixed by this module alone.
    """
    after = ball_df[ball_df["frame"] > last_hit_frame].sort_values("frame")
    after = after.dropna(subset=["table_x", "table_y"])
    if len(after) == 0:
        return None

    frames = after["frame"].to_numpy()
    gaps = np.diff(frames, prepend=last_hit_frame)
    cutoff_idx = np.argmax(gaps > TRAILING_BOUNCE_MAX_GAP_FRAMES) if np.any(gaps > TRAILING_BOUNCE_MAX_GAP_FRAMES) else len(frames)
    window = after.iloc[:cutoff_idx]
    if len(window) == 0:
        return None  # first gap after the hit already exceeds the cutoff -- genuine blackout, stay ambiguous

    window = window[window["frame"] <= last_hit_frame + TRAILING_BOUNCE_MAX_TOTAL_FRAMES]
    if len(window) == 0:
        return None

    oob_row = _out_of_bounds_frame(window)
    if oob_row is not None:
        return {
            "frame": int(oob_row["frame"]), "table_x": float(oob_row["table_x"]),
            "table_y": float(oob_row["table_y"]), "in_bounds": False,
            "method": "out_of_bounds_crossing",
        }

    return None
