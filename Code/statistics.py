"""
statistics.py
DRAFT (Day 3). Net-new for this project -- ping pong's analysis.py stopped
at event detection, there's no equivalent to port (PROJECT.md §7 priority 4).

Consumes rally_events.csv (analysis.py output: rally_id, event_type, frame,
player_side, table_x, table_y, ...) plus the raw player tracking rows for
coverage. Untested end-to-end -- no usable footage yet, so this has not run
against real data. Structure and zone definitions are the real Day 5-6 plan
(PROJECT.md Day 5 TODO), drafted early so Day 5-6 isn't starting blank.

Court-space convention (matches calibration.py): (0,0) = near-baseline-left,
x runs 0..TABLE_W along the baseline, y runs 0..TABLE_H toward the far
baseline. Net sits at y = config.NET_POSITION_OFFSET.
"""

import pandas as pd
import numpy as np

import config


# ---------------------------------------------------------------------------
# Court zones
# ---------------------------------------------------------------------------
# Singles court split into a 2 (deuce/ad side) x 3 (net / mid-court / baseline)
# grid -- a standard-enough breakdown for shot placement and doesn't require
# shot-type classification (which is explicitly post-MVP). Zone boundaries
# are estimates based on config's court dimensions + net offset; revisit once
# real table_x/table_y data exists to sanity-check against.

def _depth_band(table_y, net_y=config.NET_POSITION_OFFSET, court_h=config.TABLE_H):
    """Buckets a y-position into net / mid / baseline, independently of
    which side of the net it's on."""
    dist_from_net = abs(table_y - net_y)
    half_court = max(net_y, court_h - net_y)
    frac = dist_from_net / half_court if half_court else 0
    if frac < 0.33:
        return "net"
    elif frac < 0.7:
        return "mid"
    return "baseline"


def _side_band(table_x, court_w=config.TABLE_W):
    """Deuce (right, table_x > half) vs ad (left, table_x <= half) side,
    using the server's-perspective convention -- confirm this matches
    whatever convention detection.py/transform.py end up using once footage
    is in hand."""
    return "deuce" if table_x > court_w / 2 else "ad"


def get_zone(table_x, table_y):
    """Returns a zone label like 'deuce_baseline', or None if the position
    is unknown (NaN table_x/table_y -- common given the flagged coverage-gap
    risk, callers should handle None separately rather than dropping rows
    silently)."""
    if pd.isna(table_x) or pd.isna(table_y):
        return None
    return f"{_side_band(table_x)}_{_depth_band(table_y)}"


# ---------------------------------------------------------------------------
# Shot placement
# ---------------------------------------------------------------------------

def shot_placement_stats(events_df):
    """Zone distribution of hits, broken out by player_side. Bounces are
    excluded here -- placement is about where a player sent the ball
    (hit location), not where it landed (that's closer to a "landing spot"
    metric, which needs bounce table_x/table_y quality checked separately
    once real data exists)."""
    hits = events_df[events_df["event_type"] == "hit"].copy()
    hits["zone"] = hits.apply(lambda r: get_zone(r["table_x"], r["table_y"]), axis=1)

    unknown_rate = hits["zone"].isna().mean() if len(hits) else np.nan

    zone_counts = (
        hits.dropna(subset=["zone"])
        .groupby(["player_side", "zone"])
        .size()
        .rename("count")
        .reset_index()
    )

    return {
        "zone_counts": zone_counts,
        "unknown_position_rate": unknown_rate,  # proxy for coverage-gap impact
    }


# ---------------------------------------------------------------------------
# Rally length / pattern metrics
# ---------------------------------------------------------------------------

def rally_length_stats(events_df, fps=config.TRACKER_FRAME_RATE):
    """Per-rally shot count and duration, plus summary stats across all
    rallies. Rally length (shots and duration) is the main proxy this MVP
    uses for consistency -- longer rallies suggest fewer unforced errors,
    though that's an approximation, not a direct measurement (no
    winner/error classification in scope)."""
    if len(events_df) == 0:
        return {"per_rally": pd.DataFrame(), "summary": {}}

    per_rally = (
        events_df.groupby("rally_id")
        .agg(
            start_frame=("rally_start_frame", "first"),
            end_frame=("rally_end_frame", "first"),
            n_hits=("event_type", lambda s: (s == "hit").sum()),
            n_bounces=("event_type", lambda s: (s == "bounce").sum()),
        )
        .reset_index()
    )
    per_rally["duration_sec"] = (per_rally["end_frame"] - per_rally["start_frame"] + 1) / fps

    summary = {
        "n_rallies": len(per_rally),
        "avg_shots_per_rally": per_rally["n_hits"].mean(),
        "median_shots_per_rally": per_rally["n_hits"].median(),
        "max_shots_in_rally": per_rally["n_hits"].max(),
        "avg_rally_duration_sec": per_rally["duration_sec"].mean(),
    }

    return {"per_rally": per_rally, "summary": summary}


# ---------------------------------------------------------------------------
# Consistency metrics
# ---------------------------------------------------------------------------

def consistency_metrics(events_df):
    """First-pass consistency proxy per player: shots hit before a rally
    ends. Without shot-type/error classification (post-MVP), this can't
    distinguish "player won the point" from "player made the error" --
    flagged clearly as an approximation, not a real winner/error rate."""
    hits = events_df[events_df["event_type"] == "hit"]
    if len(hits) == 0:
        return pd.DataFrame()

    per_player = (
        hits.groupby("player_side")
        .agg(
            total_hits=("frame", "count"),
            rallies_participated=("rally_id", "nunique"),
        )
        .reset_index()
    )
    per_player["avg_hits_per_rally"] = (
        per_player["total_hits"] / per_player["rallies_participated"]
    )
    return per_player


# ---------------------------------------------------------------------------
# Court coverage (movement heatmap)
# ---------------------------------------------------------------------------
# Lowest-confidence metric per PROJECT.md — camera-angle coverage gaps hit
# this hardest since it needs continuous player position, not just event
# frames. Scope down (e.g. near-side player only) if far-side data is too
# sparse once real footage/transform quality is known.

def court_coverage(player_df, grid_rows=6, grid_cols=4,
                    court_w=config.TABLE_W, court_h=config.TABLE_H):
    """Bins each player's table-space position into a grid_rows x grid_cols
    occupancy grid. Requires player_df to already have table_x/table_y
    columns populated (i.e. run after the transform is applied) -- NOT the
    same player_df analysis.py uses today, which only needs pixel_x. Wiring
    this up is a Day 6 task once real transform output exists."""
    df = player_df.dropna(subset=["table_x", "table_y"]).copy()
    if len(df) == 0:
        return pd.DataFrame()

    df["col"] = np.clip((df["table_x"] / court_w * grid_cols).astype(int), 0, grid_cols - 1)
    df["row"] = np.clip((df["table_y"] / court_h * grid_rows).astype(int), 0, grid_rows - 1)

    coverage = (
        df.groupby(["track_id", "row", "col"])
        .size()
        .rename("frame_count")
        .reset_index()
    )
    return coverage


# ---------------------------------------------------------------------------
# Tactical tendencies
# ---------------------------------------------------------------------------
# Kept to one simple, shippable metric per PROJECT.md Day 6 note: shot
# zone preference by player. Direction (cross-court vs. down-the-line)
# would need consecutive-hit geometry and is a reasonable fast-follow, not
# MVP.

def tactical_tendencies(events_df):
    """Per-player zone preference: which zone each player hits from most,
    as a simple first tactical signal."""
    placement = shot_placement_stats(events_df)["zone_counts"]
    if len(placement) == 0:
        return pd.DataFrame()

    totals = placement.groupby("player_side")["count"].transform("sum")
    placement = placement.assign(pct_of_shots=placement["count"] / totals)
    return placement.sort_values(["player_side", "pct_of_shots"], ascending=[True, False])


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def generate_stats_report(events_csv, player_csv=None):
    """Runs all metrics and returns a dict ready for report.py to format.
    player_csv is optional (only needed for court_coverage) since it depends
    on transform output that doesn't exist yet -- pass None to skip."""
    events_df = pd.read_csv(events_csv)

    report = {
        "shot_placement": shot_placement_stats(events_df),
        "rally_lengths": rally_length_stats(events_df),
        "consistency": consistency_metrics(events_df),
        "tactical_tendencies": tactical_tendencies(events_df),
    }

    if player_csv is not None:
        player_df = pd.read_csv(player_csv)
        report["court_coverage"] = court_coverage(player_df)
    else:
        report["court_coverage"] = None  # deferred until transform output exists

    return report


if __name__ == "__main__":
    # NOTE: will not produce meaningful output until real rally_events.csv
    # exists (blocked on footage, same as analysis.py/calibration.py).
    report = generate_stats_report(config.EVENTS_CSV)
    print("Rally length summary:", report["rally_lengths"]["summary"])
    print("\nConsistency (per player):\n", report["consistency"])
    print("\nTactical tendencies (top zones per player):\n", report["tactical_tendencies"])
