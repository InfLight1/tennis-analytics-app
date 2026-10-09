"""
player_identity.py

Resolves track_id churn (PROJECT.md 2026-09-10: 10-18 distinct player
track_ids seen across ~20 real rallies, hard-blocking scoring.py) WITHOUT
depending on cross-gap track_id continuity at all.

Approach: within a single rally (a few seconds), tracking is stable --
the churn is specifically BETWEEN rallies, driven by real between-point
pauses (median ~11.5s) far exceeding what even a much larger tracker
buffer could bridge (confirmed empirically -- see config.py's
PLAYER_TRACKER_LOST_BUFFER comment: a 10x buffer increase had zero
effect on ID count). So instead of keeping one track_id stable across
the whole match, each rally's two players are labeled structurally by
their average in-rally court position:
    "near" -- average table_x closer to the near baseline (x=0)
    "far"  -- average table_x closer to the far baseline (x=TABLE_W)
Recomputed fresh every rally directly from real position data --
immune to ID churn by construction.

near/far tells us WHERE a player stood, not WHO they are across rallies.
Converting near/far into a stable identity (player_1/player_2) is
scoring.py's job (see its swap-parity helpers) -- it uses the real
tennis end-change rule against the match state it already tracks,
rather than depending on tracking continuity.

INPUT:
  match_data_df -- match_data.csv rows: frame, type, track_id, table_x,
    table_y, ... (only type=="player" rows used here).
  events_df -- rally_events.csv rows: rally_id, rally_start_frame,
    rally_end_frame, ... (only the rally boundary columns used here).

OUTPUT: compute_rally_near_far_labels() returns
  ({rally_id: {"track_<id>": "near"|"far", ...}}, qa_df)
Rallies that don't clear MIN_FRAMES per candidate, or can't be reduced
to exactly 2 distinguishable players, are OMITTED from the labels dict
entirely -- never guessed at -- and surfaced via qa_df instead (same
data-quality-visibility principle as rally_outcomes.py's own
unknown_outcome handling).
"""

import numpy as np
import pandas as pd

import config

MIN_FRAMES = getattr(config, "PLAYER_IDENTITY_MIN_FRAMES", 5)

# 2026-09-16: reconciliation with detect_hits()'s own player attribution.
# frame-count (near/far by total on-court presence) and hit-attribution
# (who was actually near the ball at each hit) can disagree on messy
# merged rally windows with many competing track IDs (PROJECT.md
# 2026-09-14, rally 22). Validated against real data: every normal rally
# has its top-2 hit-attributed tracks covering 100% of that rally's
# attributed hits; rally 22 (the one confirmed disagreement case, a
# ~193s merged window) has its top-2 covering only 39% of 54 attributed
# hits, spread across 9 distinct tracks. This threshold cleanly separates
# "a real rally with two real hitters" from "a merged window with no
# reliable 2-player resolution" -- ESTIMATED from one real dataset,
# revisit if a genuine 2-player rally is ever seen below it.
HIT_ATTRIBUTION_DOMINANCE_THRESHOLD = getattr(
    config, "PLAYER_IDENTITY_HIT_ATTRIBUTION_DOMINANCE_THRESHOLD", 0.6
)
# A rally with only 1-2 attributed hits total is too little evidence to
# override a frame-count result built from hundreds of position samples --
# found via real regression cases (rally 1, 1 attributed hit to a track
# that WAS one of frame-count's correct top-2; overriding on that alone
# would have discarded a perfectly good frame-count answer). Below this,
# hit attribution is used only to confirm (if the attributed track(s) are
# a subset of frame-count's pick) or flag, never to override.
MIN_ATTRIBUTED_HITS_FOR_CROSS_CHECK = getattr(
    config, "PLAYER_IDENTITY_MIN_ATTRIBUTED_HITS_FOR_CROSS_CHECK", 3
)


def _rally_bounds(events_df):
    """rally_id -> (start_frame, end_frame), from rally_events.csv's own
    rally_start_frame/rally_end_frame columns (falls back to min/max
    event frame if those columns are missing)."""
    if {"rally_start_frame", "rally_end_frame"} <= set(events_df.columns):
        return events_df.groupby("rally_id").agg(
            start_frame=("rally_start_frame", "first"),
            end_frame=("rally_end_frame", "first"),
        )
    return events_df.groupby("rally_id")["frame"].agg(start_frame="min", end_frame="max")


def _hit_attribution_counts(events_df):
    """rally_id -> pd.Series of {track_id (int): n_hits}, sorted descending,
    for hits attributed to a real track (excludes None/'unknown')."""
    hits = events_df[events_df["event_type"] == "hit"].copy()
    hits = hits[hits["player_side"].notna() & (hits["player_side"] != "unknown")]
    hits["track_id"] = hits["player_side"].str.replace("track_", "", regex=False).astype(int)

    out = {}
    for rally_id, group in hits.groupby("rally_id"):
        out[rally_id] = group.groupby("track_id").size().sort_values(ascending=False)
    return out


def _frame_count_candidate(window, eligible):
    """Returns (near_id, far_id, reason) -- reason is None on success,
    else a failure string. Frame-count-only logic, unchanged from the
    original design."""
    top2 = eligible.sort_values(ascending=False).index[:2]
    means = window[window["track_id"].isin(top2)].groupby("track_id")["table_x"].mean()
    near_id, far_id = means.idxmin(), means.idxmax()
    if near_id == far_id:
        return None, None, "indistinguishable_positions"
    return int(near_id), int(far_id), None


def compute_rally_near_far_labels(match_data_df, events_df):
    """Returns (labels, qa_df) -- see module docstring.

    2026-09-16: frame-count's near/far pick is cross-checked against
    detect_hits()'s own player attribution for the same rally (see
    HIT_ATTRIBUTION_DOMINANCE_THRESHOLD above):
      - No attributed hits to check against -> frame-count result stands
        as-is (cross_check='no_hit_data').
      - Hit-attribution's top 2 tracks dominate (>= threshold) and match
        frame-count's top 2 -> both methods agree (cross_check='agree').
      - Hit-attribution's top 2 dominate but DISAGREE with frame-count ->
        hit attribution wins (it's direct evidence -- "this track touched
        the ball" -- vs. frame-count's proxy "probably a player"); near/far
        is recomputed from the hit-attributed tracks' own court position
        (cross_check='overridden_by_hit_attribution').
      - No 2 tracks dominate hit-attribution (attribution spread across
        many competing tracks, e.g. a messy merged rally window) -> the
        rally is NOT guessed at, regardless of what frame-count found
        (cross_check='hit_attribution_disagreement_unresolvable').
    """
    bounds = _rally_bounds(events_df)
    players = match_data_df[match_data_df["type"] == "player"].copy()
    players = players.dropna(subset=["track_id", "table_x", "table_y"])
    hit_counts_by_rally = _hit_attribution_counts(events_df)

    labels = {}
    qa_rows = []

    for rally_id, row in bounds.iterrows():
        start, end = row["start_frame"], row["end_frame"]
        window = players[(players["frame"] >= start) & (players["frame"] <= end)]
        hit_counts = hit_counts_by_rally.get(rally_id)

        if window.empty:
            qa_rows.append({"rally_id": rally_id, "resolved": False,
                             "n_candidate_tracks": 0, "reason": "no_player_data",
                             "cross_check": None, "hit_attributed_top_tracks": None})
            continue

        counts = window.groupby("track_id").size()
        eligible = counts[counts >= MIN_FRAMES]

        if len(eligible) < 2:
            fc_near, fc_far, fc_reason = None, None, "fewer_than_2_tracked_players"
            n_candidates = int(len(eligible))
        else:
            fc_near, fc_far, fc_reason = _frame_count_candidate(window, eligible)
            n_candidates = int(len(eligible))

        def _keep_frame_count(cross_check_label):
            if fc_reason:
                qa_rows.append({"rally_id": rally_id, "resolved": False,
                                 "n_candidate_tracks": n_candidates, "reason": fc_reason,
                                 "cross_check": cross_check_label, "hit_attributed_top_tracks": top_tracks_note})
            else:
                labels[rally_id] = {f"track_{fc_near}": "near", f"track_{fc_far}": "far"}
                qa_rows.append({"rally_id": rally_id, "resolved": True,
                                 "n_candidate_tracks": n_candidates, "reason": None,
                                 "cross_check": cross_check_label, "hit_attributed_top_tracks": top_tracks_note})

        top_tracks_note = (
            ", ".join(f"track_{t}:{n}" for t, n in hit_counts.items()) if hit_counts is not None else None
        )

        # No attributed hits at all, or too few to be meaningful evidence
        # against a frame-count result built from hundreds of position
        # samples -- frame-count result stands as-is (unchanged behavior).
        if hit_counts is None or hit_counts.empty:
            _keep_frame_count("no_hit_data")
            continue
        if hit_counts.sum() < MIN_ATTRIBUTED_HITS_FOR_CROSS_CHECK:
            _keep_frame_count("insufficient_hit_data")
            continue

        top2_hits = hit_counts.head(2)
        dominance = top2_hits.sum() / hit_counts.sum()

        if dominance < HIT_ATTRIBUTION_DOMINANCE_THRESHOLD:
            # Attribution spread across too many competing tracks to trust
            # either method -- flag, don't guess, even if frame-count
            # technically produced an answer.
            qa_rows.append({"rally_id": rally_id, "resolved": False,
                             "n_candidate_tracks": n_candidates,
                             "reason": "hit_attribution_disagreement_unresolvable",
                             "cross_check": f"top2_hit_dominance={dominance:.2f}",
                             "hit_attributed_top_tracks": top_tracks_note})
            continue

        hit_top2_ids = set(int(t) for t in top2_hits.index)

        if not fc_reason and {fc_near, fc_far} == hit_top2_ids:
            _keep_frame_count("agree")
            continue

        if len(hit_top2_ids) < 2:
            # Only one distinct track has enough attributed hits to matter.
            # If it's one of frame-count's two, that's confirming evidence,
            # not a disagreement -- keep frame-count. If it contradicts
            # frame-count (or frame-count itself failed), one track alone
            # can't tell us who the *other* player is -- don't guess.
            if not fc_reason and hit_top2_ids <= {fc_near, fc_far}:
                _keep_frame_count("agree")
            else:
                qa_rows.append({"rally_id": rally_id, "resolved": False,
                                 "n_candidate_tracks": n_candidates,
                                 "reason": fc_reason or "hit_attribution_disagreement_unresolvable",
                                 "cross_check": "insufficient_distinct_hit_tracks",
                                 "hit_attributed_top_tracks": top_tracks_note})
            continue

        # Genuine disagreement (or frame-count itself failed) but
        # hit-attribution has a clear, dominant 2-track answer -- trust it:
        # a hit attribution is direct evidence the track touched the ball,
        # frame-count is only a proxy for "probably a player".
        override_window = window[window["track_id"].isin(hit_top2_ids)]
        means = override_window.groupby("track_id")["table_x"].mean()
        if len(means) < 2 or means.iloc[0] == means.iloc[1]:
            qa_rows.append({"rally_id": rally_id, "resolved": False,
                             "n_candidate_tracks": n_candidates,
                             "reason": "hit_attributed_tracks_no_position_data",
                             "cross_check": "overridden_by_hit_attribution",
                             "hit_attributed_top_tracks": top_tracks_note})
            continue

        near_id, far_id = means.idxmin(), means.idxmax()
        labels[rally_id] = {f"track_{int(near_id)}": "near", f"track_{int(far_id)}": "far"}
        qa_rows.append({"rally_id": rally_id, "resolved": True,
                         "n_candidate_tracks": n_candidates, "reason": None,
                         "cross_check": "overridden_by_hit_attribution",
                         "hit_attributed_top_tracks": top_tracks_note})

    qa_df = pd.DataFrame(qa_rows)
    return labels, qa_df


def relabel_outcomes_to_near_far(outcomes_df, labels):
    """Returns a copy of rally_outcomes.py's outcomes_df with server/
    winner/loser relabeled from raw 'track_<id>' strings to 'near'/'far'
    per-rally, using `labels` (compute_rally_near_far_labels()'s output).

    A value is only relabeled if this rally has a resolved mapping AND
    that exact track_id string appears in it. Anything else (already
    None/'unknown', or a track_id from an unresolved rally, or a stray
    3rd track_id that isn't one of this rally's mapped 2) passes through
    unchanged -- scoring.py's score_match_near_far() treats anything
    that isn't literally 'near'/'far' as unresolved for that rally and
    doesn't guess.

    NOTE: this operates on rally_outcomes.py's already-aggregated
    one-row-per-rally table (server/winner/loser columns only). It does
    NOT touch rally_events.csv's row-level player_side column -- see
    relabel_events_to_near_far() below for that, which is what
    match_stats.py and most of rally_outcomes.py's own per-shot functions
    (per_shot_accuracy, error_location_stats, per_shot_outcomes) actually
    need, since they read player_side directly from events_df rather than
    from this aggregated table.
    """
    out = outcomes_df.copy()
    for col in ("server", "winner", "loser"):
        out[col] = [
            labels.get(rid, {}).get(val, val)
            for rid, val in zip(out["rally_id"], out[col])
        ]
    return out


def relabel_events_to_near_far(events_df, labels):
    """Returns a copy of rally_events.csv's events_df with player_side
    relabeled from raw 'track_<id>' strings to 'near'/'far' per rally,
    using `labels` (compute_rally_near_far_labels()'s output).

    ADDED 2026-09-20 -- closes a real gap found during report-validation:
    relabel_outcomes_to_near_far() (above) only relabels rally_outcomes.py's
    aggregated server/winner/loser table. But per_shot_accuracy(),
    error_location_stats(), and per_shot_outcomes() (all in
    rally_outcomes.py) and shot_placement_stats(), consistency_metrics(),
    and tactical_tendencies() (all in match_stats.py) read player_side
    row-by-row directly from events_df -- none of them were ever touched
    by the outcomes-level relabel, so every one of those functions was
    silently grouping by raw ByteTrack track_id (up to dozens of distinct
    values per real match) instead of the real 2 players.

    Relabel this once, here, BEFORE calling rally_outcomes.py or
    match_stats.py -- rally_outcomes.py's own server/winner/loser fields
    are themselves derived from player_side, so relabeling events_df
    upstream also produces correctly-labeled server/winner/loser without
    needing relabel_outcomes_to_near_far() as a separate step afterward.

    Same passthrough rule as relabel_outcomes_to_near_far(): a value is
    only relabeled if its row's rally has a resolved mapping AND its
    exact track_id string appears in it. None/'unknown'/unresolved-rally
    track_ids pass through unchanged, so existing 'unknown'-handling
    logic downstream (e.g. per_shot_accuracy's `if hit["player_side"] in
    (None, "unknown")`) keeps working exactly as before.

    ADDED 2026-09-27 -- court-half fallback: in a RESOLVED rally, a hit whose
    track_id isn't one of that rally's two mapped tracks (ByteTrack re-ids
    a player mid-rally; inferred far-player gap hits attribute to whichever
    id the far player has at that moment) is assigned near/far by which half
    of the court it was hit from -- in singles only one player is on each
    side. Before this, each such hit became its own fake "player" in the
    report (a dozen single-hit track_N entries on a 14-min match).
    """
    net_x = config.NET_POSITION_OFFSET
    has_x = "table_x" in events_df.columns
    out = events_df.copy()
    sides = []
    for i, (rid, val) in enumerate(zip(out["rally_id"], out["player_side"])):
        mapping = labels.get(rid)
        if mapping is None or val in mapping or not isinstance(val, str) or not val.startswith("track_"):
            sides.append(mapping.get(val, val) if mapping else val)
            continue
        tx = out["table_x"].iloc[i] if has_x else np.nan
        sides.append(val if pd.isna(tx) else ("near" if tx < net_x else "far"))
    out["player_side"] = sides
    return out


if __name__ == "__main__":
    match_data_df = pd.read_csv(config.MATCH_CSV)
    events_df = pd.read_csv(config.EVENTS_CSV)

    labels, qa_df = compute_rally_near_far_labels(match_data_df, events_df)
    print(f"Resolved near/far for {len(labels)}/{len(qa_df)} rallies")
    unresolved = qa_df[~qa_df["resolved"]]
    if len(unresolved):
        print("\nUnresolved rallies:\n", unresolved.to_string(index=False))
