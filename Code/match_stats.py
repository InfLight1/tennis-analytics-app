"""
match_stats.py
DRAFT (Day 3). Net-new for this project -- ping pong's analysis.py stopped
at event detection, there's no equivalent to port (PROJECT.md §7 priority 4).

RENAMED from statistics.py (Day 3): the original name shadows Python's
built-in `statistics` module. Since this project's own files import from
the same directory it's run in, `import statistics` anywhere else in the
codebase would silently pull in this file instead of the stdlib module --
renamed before that could bite anyone.

Consumes rally_events.csv (analysis.py output: rally_id, event_type, frame,
player_side, table_x, table_y, ...) plus the raw player tracking rows for
coverage. Untested end-to-end -- no usable footage yet, so this has not run
against real data. Structure and zone definitions are the real Day 5-6 plan
(PROJECT.md Day 5 TODO), drafted early so Day 5-6 isn't starting blank.

Court-space convention (matches config.py / calibration.py, corrected Day 3):
x runs 0..TABLE_W along the baseline-to-baseline axis (net sits at
x = config.NET_POSITION_OFFSET), y runs 0..TABLE_H along the sideline-to-
sideline axis (deuce/ad divide sits at y = TABLE_H / 2). Net/baseline depth
uses table_x; deuce/ad side uses table_y -- the reverse of this file's first
draft, which had the same x/y mix-up caught and fixed in calibration.py's
reference-point schema.
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

def _depth_band(table_x, net_x=config.NET_POSITION_OFFSET, court_w=config.TABLE_W):
    """Buckets an x-position (baseline-to-baseline axis) into net / mid /
    baseline, independently of which baseline it's closer to. table_x is
    the depth axis per config.py's convention (net sits at TABLE_W / 2)."""
    dist_from_net = abs(table_x - net_x)
    half_court = max(net_x, court_w - net_x)
    frac = dist_from_net / half_court if half_court else 0
    if frac < 0.33:
        return "net"
    elif frac < 0.7:
        return "mid"
    return "baseline"


def _side_band(table_y, court_h=config.TABLE_H):
    """Deuce vs ad side, using table_y (the sideline-to-sideline axis) --
    confirm the deuce/ad-to-y-value mapping matches whatever convention
    detection.py/transform.py end up using once footage is in hand; this
    picks a direction arbitrarily since there's no real data yet to anchor
    it against."""
    return "deuce" if table_y > court_h / 2 else "ad"


def get_zone(table_x, table_y):
    """Returns a zone label like 'deuce_baseline', or None if the position
    is unknown (NaN table_x/table_y -- common given the flagged coverage-gap
    risk, callers should handle None separately rather than dropping rows
    silently)."""
    if pd.isna(table_x) or pd.isna(table_y):
        return None
    return f"{_side_band(table_y)}_{_depth_band(table_x)}"


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

def rally_length_bucket(n_hits, short_max=config.RALLY_LENGTH_SHORT_MAX_HITS,
                         long_min=config.RALLY_LENGTH_LONG_MIN_HITS):
    """Buckets a rally's shot count into 'short' / 'medium' / 'long'.
    Thresholds live in config.py (RALLY_LENGTH_SHORT_MAX_HITS /
    RALLY_LENGTH_LONG_MIN_HITS) as the single source of truth shared with
    prioritization.py's per-player point-loss join -- see config.py's
    comment for why this was consolidated (Day 6), same drift-prevention
    reasoning as COURT_GRID_ROWS/COLS."""
    if n_hits <= short_max:
        return "short"
    elif n_hits >= long_min:
        return "long"
    return "medium"


def rally_length_stats(events_df, fps=config.TRACKER_FRAME_RATE):
    """Per-rally shot count and duration, plus summary stats across all
    rallies, PLUS the short/medium/long bucket distribution -- this is
    the literal "Rally length distribution (short/medium/long buckets)"
    MVP stat (PROJECT.md §2). Previously this function computed
    avg/median/max shots per rally but never actually produced the
    bucketed distribution the MVP stat calls for; added Day 6.

    Rally length (shots and duration) remains a proxy signal here, not a
    real winner/error measurement -- for actual per-player point-loss by
    rally-length bucket, see prioritization.extract_rally_length_loss_patterns(),
    which joins this table's per_rally output against rally_outcomes.py's
    real winner/loser data. This function stays frequency-only by design,
    consistent with the rest of match_stats.py (outcome joins live in
    prioritization.py, not here)."""
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
    per_rally["length_bucket"] = per_rally["n_hits"].apply(rally_length_bucket)

    bucket_counts = per_rally["length_bucket"].value_counts()
    n_rallies = len(per_rally)
    length_distribution = {
        bucket: {
            "count": int(bucket_counts.get(bucket, 0)),
            "pct": round(100.0 * bucket_counts.get(bucket, 0) / n_rallies, 1) if n_rallies else 0.0,
        }
        for bucket in ("short", "medium", "long")
    }

    summary = {
        "n_rallies": n_rallies,
        "avg_shots_per_rally": per_rally["n_hits"].mean(),
        "median_shots_per_rally": per_rally["n_hits"].median(),
        "max_shots_in_rally": per_rally["n_hits"].max(),
        "avg_rally_duration_sec": per_rally["duration_sec"].mean(),
        "length_distribution": length_distribution,
    }

    return {"per_rally": per_rally, "summary": summary}


# ---------------------------------------------------------------------------
# Consistency metrics
# ---------------------------------------------------------------------------

def consistency_metrics(events_df):
    """Engagement proxy per player: total hits and avg hits per rally.
    This does NOT measure in/out accuracy or winner/error rate -- it only
    counts how much a player is hitting, which is a weak, indirect signal
    at best.

    UPDATED (Day 6): as of rally_outcomes.py (Day 5), a real in/out
    accuracy measurement now exists -- see
    rally_outcomes.per_shot_accuracy() (shots_in/shots_out/
    rally_accuracy_pct, real winner/error data, not a proxy). That is now
    the correct source for "how consistent is this player," and is what
    prioritization.extract_rally_accuracy_patterns() uses. This function
    is kept because "hits per rally" (engagement/participation) is still
    a distinct, valid signal on its own -- but it should no longer be
    read as a consistency/accuracy approximation now that a real one
    exists elsewhere. Previously this docstring implied it stood in for a
    real measurement that didn't exist yet; that's no longer accurate,
    so the claim is corrected here rather than left stale."""
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

def court_coverage(player_df, grid_rows=config.COURT_GRID_ROWS, grid_cols=config.COURT_GRID_COLS,
                    court_w=config.TABLE_W, court_h=config.TABLE_H):
    """Bins each player's table-space position into a grid_rows x grid_cols
    occupancy grid. Requires player_df to already have table_x/table_y
    columns populated (i.e. run after the transform is applied) -- NOT the
    same player_df analysis.py uses today, which only needs pixel_x. Wiring
    this up is a Day 6 task once real transform output exists.

    grid_rows/grid_cols now default to config.COURT_GRID_ROWS/COURT_GRID_COLS
    (previously hardcoded 6/4 here) so prioritization.py's
    extract_coverage_point_loss_patterns() can't silently drift out of
    sync with this function's actual grid resolution."""
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

def run_statistics(events_csv, output_path, player_csv=None):
    """Orchestration entry point for main.py (Day 3, new) -- mirrors the
    call shape of ping pong's metrics.run_metrics(events_csv,
    output_path=metrics_csv). Runs generate_stats_report() and flattens the
    scalar summary metrics (rally-length summary + per-player consistency)
    into a single CSV row per player for a quick, pipeline-friendly output;
    the richer structures (zone_counts, tactical_tendencies, court_coverage)
    aren't flat and are left as an in-memory dict for now -- report.py
    (Day 7) will need to decide how those get written out."""
    report = generate_stats_report(events_csv, player_csv=player_csv)

    consistency = report["consistency"]
    if len(consistency) > 0:
        # DAY 6 FIX: rally_lengths["summary"] now includes a nested
        # length_distribution dict (short/medium/long counts + pct) --
        # dumping that straight into a CSV cell via consistency[key] =
        # value would have serialized a Python dict as a single opaque
        # string per row. Flattened into individual scalar columns
        # instead (e.g. rally_length_pct_short), consistent with every
        # other column in this CSV being a plain scalar.
        for key, value in report["rally_lengths"]["summary"].items():
            if key == "length_distribution":
                for bucket, bucket_stats in value.items():
                    consistency[f"rally_length_count_{bucket}"] = bucket_stats["count"]
                    consistency[f"rally_length_pct_{bucket}"] = bucket_stats["pct"]
            else:
                consistency[key] = value
        consistency.to_csv(output_path, index=False)
        print(f"Saved {output_path}")
    else:
        print(f"No hit events to summarize — skipped writing {output_path}")

    return report


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
