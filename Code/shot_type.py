"""
shot_type.py

Rule-based shot-type classification for each hit event: serve, volley, or
groundstroke. Per PROJECT.md §2/§14, this ships in MVP as a low-risk
heuristic off hit-event geometry — no pose estimation needed.
Forehand/backhand stays deferred past MVP (needs pose estimation / varied
player footage), unaffected by this module.

INPUT: analysis.py's rally_events.csv schema (or the equivalent
DataFrame) — one row per event: rally_id, event_type, frame, player_side,
table_x, table_y, pos_source, in_bounds, estimated, ... Only
event_type=='hit' rows get classified; bounce rows pass through with
shot_type=None.

RULES:
  - serve: the FIRST hit (by frame order) within a rally. Purely
    structural — a rally starts with the serve by definition, so this
    needs no position/geometry at all and is the most robust of the
    three labels (can't be thrown off by a detection/geometry gap the
    way volley/groundstroke can).
  - volley vs groundstroke (all other hits): primary signal is
    STRUCTURAL, not geometric — whether a bounce event occurred between
    the previous hit (either player) and this one. A volley is BY
    DEFINITION struck before the ball bounces, so this is a hard fact,
    not an approximation, and (unlike geometry) doesn't need table_x to
    be resolvable at all.
  - REVISED 2026-09-23, after validating against the real 40-min video's
    rally_events.csv: the original design used hit-event geometry
    (distance from net vs config.VOLLEY_ZONE_HALF_WIDTH_CM) as the
    PRIMARY label and the bounce check as a secondary cross-check. On
    real data this disagreed with the bounce check on 62.2% of non-serve
    hits (120/193) — VOLLEY_ZONE_HALF_WIDTH_CM (~640cm, the full
    net-to-service-line distance) turned out to cover nearly the entire
    forecourt, so most groundstrokes hit anywhere short of the baseline
    were being mislabeled as volleys (141 volley vs 52 groundstroke,
    implausible for real baseline-camera rally footage). Swapped which
    signal is primary: bounce-based is now the label, geometry is now
    the secondary cross-check (same disagreement-rate mechanism, flag
    unchanged: shot_type_geometry_bounce_disagreement=True when they
    conflict). Re-run on the same real data gives 128 groundstroke / 65
    volley / 102 serve — a far more plausible split. Disagreement rate is
    unchanged at 62.2% (it's symmetric either way) — that number is now a
    signal that VOLLEY_ZONE_HALF_WIDTH_CM itself is miscalibrated and
    worth re-deriving, not a signal about which label is trustworthy.
  - NEITHER signal is ground truth. label_ground_truth.py only logs
    bounce/hit/net timing, not shot type — there is currently NO manually
    verified shot-type dataset for this project, real or synthetic-only.
    A 0% disagreement rate would mean the two heuristics agree with each
    other, not that either is correct. Before trusting this for real
    coaching output, budget a small manual validation pass (eyeball
    20-30 real hits in the video, note true shot type, compare) — the
    same pattern already used to validate bounce/hit detection.
  - Geometry cross-check is skipped (disagreement flag stays None) when
    table_x isn't resolvable (pos_source == "unavailable") — this no
    longer blocks the primary shot_type label, which is a real
    improvement over the old geometry-primary design: bounce status is
    always computable regardless of position resolution, so shot_type is
    only ever "unknown" if truly nothing can be inferred (should not
    occur for hit rows in practice; kept as a defensive fallback).

OUT OF SCOPE (per PROJECT.md, deferred past MVP): forehand/backhand.
"""

import pandas as pd

import config

NET_X = config.NET_POSITION_OFFSET
VOLLEY_ZONE_HALF_WIDTH = config.VOLLEY_ZONE_HALF_WIDTH_CM


def classify_shot_types(events_df):
    """
    Returns events_df with two new columns:
      shot_type: 'serve' | 'volley' | 'groundstroke' | 'unknown' | None
        (None for non-hit rows, i.e. bounces). Primary label is the
        bounce-since-last-hit signal (structural), NOT geometry — see
        module docstring's 2026-09-23 revision note.
      shot_type_geometry_bounce_disagreement: bool | None — only set for
        non-serve hits with a resolvable position; True when the
        geometry-based check and the bounce-based label disagree.
    """
    df = events_df.copy()
    df["shot_type"] = None
    df["shot_type_geometry_bounce_disagreement"] = None

    for rally_id, rally in df.groupby("rally_id"):
        rally = rally.sort_values("frame")
        hit_rows = rally[rally["event_type"] == "hit"]
        if hit_rows.empty:
            continue

        first_hit_idx = hit_rows.index[0]
        df.loc[first_hit_idx, "shot_type"] = "serve"

        bounced_since_last_hit = False
        for idx, row in rally.iterrows():
            if row["event_type"] == "bounce":
                bounced_since_last_hit = True
                continue
            if row["event_type"] != "hit":
                continue
            if idx == first_hit_idx:
                bounced_since_last_hit = False
                continue

            # PRIMARY: structural bounce fact — always computable, no
            # position needed.
            bounce_label = "groundstroke" if bounced_since_last_hit else "volley"
            df.loc[idx, "shot_type"] = bounce_label

            # SECONDARY: geometry cross-check, only when position resolvable.
            table_x = row["table_x"]
            if not pd.isna(table_x):
                dist_from_net = abs(table_x - NET_X)
                geometry_label = "volley" if dist_from_net <= VOLLEY_ZONE_HALF_WIDTH else "groundstroke"
                df.loc[idx, "shot_type_geometry_bounce_disagreement"] = (geometry_label != bounce_label)

            bounced_since_last_hit = False

    return df


def shot_type_summary(classified_df):
    """Quick counts for a sanity check / report.py input."""
    hits = classified_df[classified_df["event_type"] == "hit"]
    counts = hits["shot_type"].value_counts(dropna=False).to_dict()
    n_disagree = hits["shot_type_geometry_bounce_disagreement"].sum()
    n_checked = hits["shot_type_geometry_bounce_disagreement"].notna().sum()
    return {
        "counts": counts,
        "geometry_bounce_disagreements": int(n_disagree),
        "non_serve_hits_checked": int(n_checked),
        "disagreement_rate": round(n_disagree / n_checked, 3) if n_checked else None,
    }


if __name__ == "__main__":
    events_df = pd.read_csv(config.EVENTS_CSV)
    classified = classify_shot_types(events_df)
    print(classified[classified["event_type"] == "hit"][
        ["rally_id", "frame", "player_side", "table_x", "shot_type", "shot_type_geometry_bounce_disagreement"]
    ].to_string(index=False))
    print("\nSummary:", shot_type_summary(classified))
