"""
metrics.py — Day 3 deliverable.

Consumes rally_events.csv (output of analysis.py) and derives per-rally
performance metrics:
  - shot count (total hits, split by attributed player side)
  - rally length (frames + seconds)
  - ball speed (avg + max, cm/s)
  - ball placement (2x3 table-zone grid, as % of in-bounds bounces)

Writes one consolidated row per rally to METRICS_CSV.

Schema note: EVENTS_CSV rows are individual hit/bounce events with columns:
  rally_id, rally_start_frame, rally_end_frame, event_type, frame,
  player_side, table_x, table_y, pos_source, pos_offset_frames

  - player_side is only populated on 'hit' rows.
  - table_x/table_y can be NaN (pos_source == 'unavailable') or fall
    outside the table's physical bounds (known high-arc homography gap).
  - pos_source == 'nearby' means the coordinate was borrowed from a
    frame `pos_offset_frames` away from the event's own `frame`; this
    is accounted for when computing elapsed time between positions.
"""

from pathlib import Path
import numpy as np
import pandas as pd

from config import EVENTS_CSV, TRACKER_FRAME_RATE, TABLE_W, TABLE_H, CODE_DIR

try:
    from config import METRICS_CSV
except ImportError:
    METRICS_CSV = CODE_DIR / "rally_metrics.csv"

# Table-space units are 10 px/cm (per config.py comment on TABLE_W/TABLE_H).
UNITS_PER_CM = 10.0

# Zone grid: 3 columns along table length (TABLE_W axis), 2 rows along
# table width (TABLE_H axis) -> 6 zones, numbered 1-6 in row-major order:
#   zone_1 zone_2 zone_3
#   zone_4 zone_5 zone_6
ZONE_COLS = 3
ZONE_ROWS = 2
N_ZONES = ZONE_COLS * ZONE_ROWS


def _effective_frame(row):
    """Best-estimate frame at which a table_x/table_y coordinate was
    actually measured, correcting for 'nearby'-sourced positions."""
    offset = row["pos_offset_frames"]
    if pd.isna(offset):
        offset = 0.0
    return row["frame"] - offset


def compute_shot_counts(rally_df):
    hits = rally_df[rally_df["event_type"] == "hit"]
    return {
        "num_hits": len(hits),
        "hits_track_1": int((hits["player_side"] == "track_1").sum()),
        "hits_track_2": int((hits["player_side"] == "track_2").sum()),
    }


def compute_rally_length(rally_df):
    start = rally_df["rally_start_frame"].iloc[0]
    end = rally_df["rally_end_frame"].iloc[0]
    frames = end - start + 1
    return {
        "rally_frames": int(frames),
        "rally_seconds": round(frames / TRACKER_FRAME_RATE, 3),
    }


def compute_ball_speed(rally_df):
    """Frame-to-frame speed between consecutive valid ball positions
    (hits + bounces combined, since both carry a ball location)."""
    pts = rally_df.dropna(subset=["table_x", "table_y"]).copy()
    pts = pts.sort_values("frame")

    if len(pts) < 2:
        return {"avg_speed_cms": np.nan, "max_speed_cms": np.nan, "speed_samples_used": 0}

    eff_frames = pts.apply(_effective_frame, axis=1).to_numpy()
    xs = pts["table_x"].to_numpy()
    ys = pts["table_y"].to_numpy()

    speeds = []
    for i in range(1, len(pts)):
        dt_frames = eff_frames[i] - eff_frames[i - 1]
        if dt_frames <= 0:
            continue  # guard against nearby-offset ties/inversions
        dist_cm = np.hypot(xs[i] - xs[i - 1], ys[i] - ys[i - 1]) / UNITS_PER_CM
        dt_sec = dt_frames / TRACKER_FRAME_RATE
        speeds.append(dist_cm / dt_sec)

    if not speeds:
        return {"avg_speed_cms": np.nan, "max_speed_cms": np.nan, "speed_samples_used": 0}

    return {
        "avg_speed_cms": round(float(np.mean(speeds)), 2),
        "max_speed_cms": round(float(np.max(speeds)), 2),
        "speed_samples_used": len(speeds),
    }


def compute_placement_zones(rally_df):
    """2x3 grid over in-bounds bounce coordinates. Off-table bounces
    (high-arc homography gap) and missing coords are excluded from the
    denominator rather than forced into a zone."""
    bounces = rally_df[rally_df["event_type"] == "bounce"].dropna(subset=["table_x", "table_y"])
    in_bounds = bounces[
        (bounces["table_x"] >= 0) & (bounces["table_x"] <= TABLE_W)
        & (bounces["table_y"] >= 0) & (bounces["table_y"] <= TABLE_H)
    ]

    result = {"bounces_used": len(in_bounds)}
    zone_counts = np.zeros(N_ZONES, dtype=int)

    if len(in_bounds) > 0:
        col_idx = np.clip((in_bounds["table_x"] // (TABLE_W / ZONE_COLS)).astype(int), 0, ZONE_COLS - 1)
        row_idx = np.clip((in_bounds["table_y"] // (TABLE_H / ZONE_ROWS)).astype(int), 0, ZONE_ROWS - 1)
        zone_idx = row_idx * ZONE_COLS + col_idx
        for z in zone_idx:
            zone_counts[z] += 1

    for z in range(N_ZONES):
        pct = (zone_counts[z] / len(in_bounds) * 100) if len(in_bounds) > 0 else np.nan
        result[f"zone_{z + 1}_pct"] = round(pct, 1) if not np.isnan(pct) else np.nan

    return result


def compute_rally_metrics(events_df):
    rows = []
    for rally_id, rally_df in events_df.groupby("rally_id"):
        row = {"rally_id": rally_id}
        row.update(compute_shot_counts(rally_df))
        row.update(compute_rally_length(rally_df))
        row.update(compute_ball_speed(rally_df))
        row.update(compute_placement_zones(rally_df))
        rows.append(row)

    metrics_df = pd.DataFrame(rows).sort_values("rally_id").reset_index(drop=True)

    col_order = (
        ["rally_id", "num_hits", "hits_track_1", "hits_track_2",
         "rally_frames", "rally_seconds",
         "avg_speed_cms", "max_speed_cms", "speed_samples_used",
         "bounces_used"]
        + [f"zone_{i + 1}_pct" for i in range(N_ZONES)]
    )
    return metrics_df[col_order]


def run_metrics(events_csv_path, output_path):
    events_df = pd.read_csv(events_csv_path)
    if events_df.empty:
        raise RuntimeError(
            f"{events_csv_path} is empty — no rally events to compute metrics from. "
            f"Check analysis.py output (zero rallies detected upstream?)."
        )
    metrics_df = compute_rally_metrics(events_df)
    metrics_df.to_csv(output_path, index=False)
    print(f"Wrote {len(metrics_df)} rally rows to {output_path}")
    return metrics_df


if __name__ == "__main__":
    run_metrics(EVENTS_CSV, METRICS_CSV)
