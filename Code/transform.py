"""
Takes the raw per-frame detections CSV, interpolates short gaps in the
ball's pixel position, and applies the saved perspective transform to
convert both ball and player pixel coordinates into table coordinates.

CHECKED Day 3: no changes needed. table_w/table_h/off_table_margin are
already parameterized from config.py (now real tennis values), and this
file only ever applies whatever matrix calibration.py saved -- it doesn't
care whether that matrix came from a 4-point exact fit or the new
multi-point homography, so calibration.py's Day 3 rework doesn't affect
this file at all.

Run this standalone after detection.py:
    python transform.py
"""

import os

import cv2
import numpy as np
import pandas as pd

import config


def _interpolate_short_gaps(series, max_gap):
    """
    Linearly interpolates ONLY runs of consecutive NaNs that are:
      (a) no longer than max_gap frames, AND
      (b) bounded by a real (non-NaN) value on BOTH sides.

    Found via real-footage validation (2026-09): plain
    pd.Series.interpolate(method="linear", limit=N) does NOT behave this
    way. It finds the nearest real value on each side no matter how far
    apart they are -- e.g. two real ball detections 320 frames apart --
    draws a straight line across the ENTIRE gap, and only *truncates* the
    output to the first N frames of that line. Those N frames are not a
    real short-gap interpolation; they're the first few points of a
    fabricated straight line spanning a completely different, much larger
    gap the ball could have done anything inside. Confirmed on real data:
    this produced 10 frames of smoothly-drifting "detected" ball position
    across a real 320-frame detection void, which fed a fabricated event
    straight into analysis.py.

    Separately, pandas also flat-extrapolates (holds the last real value)
    past the end of a track when no further real value exists at all --
    also confirmed on real data (a track's tail repeating one exact pixel
    position for 9+ frames). That's extrapolation, not interpolation, and
    is never appropriate here.

    This function fixes both: a gap is only ever filled if it is short
    AND has real anchors on both sides. Wider gaps and open-ended
    (leading/trailing) gaps are left as NaN -- exactly like a normal
    tracking dropout that's too long to trust.
    """
    values = series.to_numpy(dtype=float, copy=True)
    n = len(values)
    isnan = np.isnan(values)

    i = 0
    n_filled_gaps = 0
    n_left_open = 0
    while i < n:
        if isnan[i]:
            j = i
            while j < n and isnan[j]:
                j += 1
            gap_len = j - i
            has_left = i > 0 and not isnan[i - 1]
            has_right = j < n and not isnan[j]
            if has_left and has_right and gap_len <= max_gap:
                left_val, right_val = values[i - 1], values[j]
                step = (right_val - left_val) / (gap_len + 1)
                for k in range(gap_len):
                    values[i + k] = left_val + step * (k + 1)
                n_filled_gaps += 1
            else:
                n_left_open += 1
            i = j
        else:
            i += 1

    return pd.Series(values, index=series.index), n_filled_gaps, n_left_open


def _foot_point(x1, x2, y2):
    """Bottom-center of a player's bounding box -- an approximation of
    where their feet meet the ground, i.e. the actual ground-plane point
    homography assumes it's given.

    FIX (2026-09-18, real-footage finding): player rows were being
    transformed using (pixel_x, pixel_y) -- the box CENTER (roughly torso
    height), not a ground point. For a near player this vertical offset
    barely matters (real data: table_x populated ~97-99% of the time).
    For a far player under this project's elevated, oblique, behind-
    baseline camera, the same torso-height offset in pixel space maps to
    a large systematic error in the homography-projected point -- close
    to a full body's worth of extra "depth" pushed onto their true ground
    position. Confirmed on real data: far-player table_x values that DID
    survive clustered right at 2467-2527, i.e. pinned at exactly
    TABLE_W + OFF_TABLE_MARGIN (2377 + 150 = 2527) -- not noise, a
    systematic push just past the off-court cutoff. This silently nulled
    the far player's position for 50-100% of frames in the affected
    rallies, which is what player_identity.py was surfacing as
    'fewer_than_2_tracked_players' -- detection and tracking were both
    fine; only the ground-plane projection was wrong.

    Uses x2/y2 from the box (bottom edge) rather than pixel_x/pixel_y
    (box center) for the y-coordinate, keeping x centered between x1/x2
    same as before.
    """
    if pd.isna(x1) or pd.isna(x2) or pd.isna(y2):
        return np.nan, np.nan
    return (x1 + x2) / 2, y2


def _to_table_coords(px, py, M, table_w, table_h, margin, side_margin=None):
    """Converts a single pixel (px, py) to table coordinates using M.
    Returns (None, None) if the point is missing or falls far outside
    the table (treated as off-table / invalid). `margin` applies behind the
    baselines, `side_margin` (default: same) outside the sidelines."""
    if pd.isna(px) or pd.isna(py):
        return None, None
    if side_margin is None:
        side_margin = margin

    pt = np.array([[[float(px), float(py)]]], dtype=np.float32)
    result = cv2.perspectiveTransform(pt, M)[0][0]
    tx, ty = float(result[0]), float(result[1])

    if tx < -margin or tx > table_w + margin or ty < -side_margin or ty > table_h + side_margin:
        return None, None

    return tx, ty


def _project_unclipped(px, py, M):
    """Same projection as _to_table_coords but never nulled for being
    off-court. The homography assumes a ground-plane point, so a ball in
    the AIR projects past where it really is (above the far baseline it can
    land metres beyond it) -- analysis.py uses this to tell a genuinely
    off-court ball (wide of the sidelines / behind the near baseline) from
    an in-flight one, instead of discarding every in-flight point."""
    if pd.isna(px) or pd.isna(py):
        return np.nan, np.nan
    pt = np.array([[[float(px), float(py)]]], dtype=np.float32)
    tx, ty = cv2.perspectiveTransform(pt, M)[0][0]
    return float(tx), float(ty)


def interpolate_and_transform(
    raw_csv_path,
    matrix_path,
    output_csv_path,
    table_w=config.TABLE_W,
    table_h=config.TABLE_H,
    interpolation_limit=config.INTERPOLATION_LIMIT,
    off_table_margin=config.OFF_TABLE_MARGIN,
):
    """
    Loads raw_csv_path, interpolates ball pixel positions over gaps up to
    interpolation_limit frames, transforms both ball and player positions
    into table coordinates, merges everything back together, and saves to
    output_csv_path.

    Returns
    -------
    pd.DataFrame
        The final merged, transformed dataframe.
    """
    try:
        M = np.load(matrix_path)
    except (FileNotFoundError, ValueError) as e:
        raise RuntimeError(
            f"Could not load perspective matrix at {matrix_path}. "
            f"Run calibration.py first, or delete a corrupted file and re-run. ({e})"
        ) from e

    df = pd.read_csv(raw_csv_path)
    if df.empty:
        raise RuntimeError(
            f"{raw_csv_path} is empty — detection likely produced no rows. "
            f"Check detection.py output before continuing."
        )
    df["pixel_x"] = pd.to_numeric(df["pixel_x"], errors="coerce")
    df["pixel_y"] = pd.to_numeric(df["pixel_y"], errors="coerce")
    df["confidence"] = pd.to_numeric(df["confidence"], errors="coerce")

    print(f"Loaded {len(df)} rows from raw detections")
    print(f"  Ball rows:   {len(df[df['type'] == 'ball'])}")
    print(f"  Player rows: {len(df[df['type'] == 'player'])}")

    # ── Interpolate ball positions ────────────────────────────────────────
    print("\nInterpolating ball positions...")
    ball_df = df[df["type"] == "ball"].copy().sort_values("frame").reset_index(drop=True)

    n_real_before = ball_df["pixel_x"].notna().sum()
    ball_df["pixel_x"], n_gaps_x, n_open_x = _interpolate_short_gaps(ball_df["pixel_x"], interpolation_limit)
    ball_df["pixel_y"], n_gaps_y, n_open_y = _interpolate_short_gaps(ball_df["pixel_y"], interpolation_limit)
    n_real_after = ball_df["pixel_x"].notna().sum()

    print(f"  Real ball detections before interpolation: {n_real_before} / {len(ball_df)}")
    print(f"  Short gaps bridged (<= {interpolation_limit} frames, anchored both sides): {n_gaps_x}")
    print(f"  Gaps left as-is (too wide and/or open-ended, not extrapolated): {n_open_x}")
    print(f"  Ball positions after interpolation: {n_real_after} / {len(ball_df)}")

    # ── Apply transform to ball positions ─────────────────────────────────
    print("Applying perspective transform to ball positions...")
    ball_table = ball_df.apply(
        lambda r: pd.Series(_to_table_coords(r["pixel_x"], r["pixel_y"], M, table_w, table_h, off_table_margin)),
        axis=1,
    )
    ball_df["table_x"] = ball_table[0]
    ball_df["table_y"] = ball_table[1]
    ball_proj = ball_df.apply(
        lambda r: pd.Series(_project_unclipped(r["pixel_x"], r["pixel_y"], M)), axis=1,
    )
    ball_df["proj_x"] = ball_proj[0]
    ball_df["proj_y"] = ball_proj[1]

    # ── Apply transform to player positions ───────────────────────────────
    # Uses each player's foot point (bottom-center of their box), not the
    # box center -- see _foot_point()'s docstring. The box center is well
    # above the true ground-contact point, and homography assumes ground-
    # plane input; using it was pushing far-side players' projected
    # position systematically past the true baseline.
    print("Applying perspective transform to player positions...")
    player_df = df[df["type"] == "player"].copy()
    foot_points = player_df.apply(
        lambda r: pd.Series(_foot_point(r["x1"], r["x2"], r["y2"])), axis=1
    )
    player_table = pd.DataFrame({0: foot_points[0], 1: foot_points[1]}).apply(
        lambda r: pd.Series(_to_table_coords(r[0], r[1], M, table_w, table_h,
                                             config.PLAYER_BASELINE_MARGIN, config.PLAYER_SIDE_MARGIN)),
        axis=1,
    )
    player_df["table_x"] = player_table[0]
    player_df["table_y"] = player_table[1]

    # ── Merge back together ────────────────────────────────────────────────
    final_df = pd.concat([ball_df, player_df]).sort_values(["frame", "type"]).reset_index(drop=True)
    final_df.to_csv(output_csv_path, index=False)

    # ── Summary ────────────────────────────────────────────────────────────
    ball_rows = final_df[final_df["type"] == "ball"]
    player_rows = final_df[final_df["type"] == "player"]

    # output_csv_path may be a plain str (e.g. when called from modal_app.py
    # with an f-string path) or a pathlib.Path -- os.path.basename handles
    # both, unlike .name which only exists on Path.
    print(f"\n── {os.path.basename(output_csv_path)} summary ───────────────────────────────────────")
    print(f"  Total rows:              {len(final_df)}")
    print(f"  Ball frames (total):     {len(ball_rows)}")
    print(f"  Ball on table:           {ball_rows['table_x'].notna().sum()}")
    print(f"  Player detections:       {len(player_rows)}")
    print(f"  Unique player IDs:       {player_rows['track_id'].nunique()}")

    ids = sorted(player_rows["track_id"].dropna().unique().astype(int))
    print(f"  Player IDs:              {ids}")
    print(f"\nSaved {output_csv_path}")

    return final_df


if __name__ == "__main__":
    interpolate_and_transform(
        raw_csv_path=config.RAW_CSV,
        matrix_path=config.MATRIX_PATH,
        output_csv_path=config.MATCH_CSV,
    )
