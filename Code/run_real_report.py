"""
run_real_report.py

One-off orchestration script to validate match_stats.py -> prioritization.py
-> report.py against REAL pipeline output (analysis.py's rally_events.csv,
which carries raw track_id-level player_side -- see PROJECT.md 2026-09-19/20
and player_identity.py's module docstring).

TWO relabel passes happen before report.py ever runs, because there are
two distinct identity problems, not one:

  Pass 1 (player_identity.py): raw ByteTrack track_id -> "near"/"far" per
    rally. Fixes track_id churn WITHIN reading a single rally's data, but
    "near"/"far" is only a POSITION at that moment -- it is NOT a stable
    identity across the match (a real end-change means whoever was "near"
    in rally 5 may be "far" in rally 6). Confirmed directly in
    player_identity.py's own docstring.

  Pass 2 (scoring.py): "near"/"far" -> a match-stable "player_1"/
    "player_2" identity, via score_match_near_far()'s swap-parity state
    machine (the real tennis end-change rule, tracked against games
    completed). This is the step that was MISSING from the first version
    of this script -- without it, match_stats.py's per-player rollups
    (consistency, shot placement, tactical tendencies, and every
    prioritization.py pattern built on them) silently blend two different
    real players together across any rally where an end-change happened,
    even though the report LOOKS correctly labeled ("near"/"far" instead
    of track_id).

Court coverage is still explicitly SKIPPED (player_csv=None). See the
original module docstring reasoning -- court_coverage() groups by raw
numeric track_id with no rally-id context, so neither relabel pass here
can fix it; it needs its own rally-aware rewrite as a separate task.

Run once real match_data.csv and rally_events.csv exist (i.e. after
detection.py -> transform.py -> analysis.py have all run against real
footage):
    python run_real_report.py
"""

import pandas as pd

import config
import player_identity
import rally_outcomes
import scoring
import report


RESOLVED_EVENTS_CSV = config.CODE_DIR / "rally_events_resolved.csv"
STABLE_EVENTS_CSV = config.CODE_DIR / "rally_events_stable.csv"


def build_rally_stable_labels(per_point_df):
    """rally_id -> {"near": <stable id>, "far": <stable id>}, from
    scoring.py's score_match_near_far() per_point_df output.

    Built for EVERY rally regardless of whether that rally's point was
    actually scored -- score_match_near_far() computes swap parity from
    match state at the top of its loop for every row, independent of
    whether the winner/loser for that specific rally were resolvable. So
    an identity-unresolved-but-swap-parity-known rally still gets a
    correct near/far -> player_1/player_2 mapping here, which is what we
    want: this mapping is about WHERE each stable player was standing,
    not whether that particular rally's outcome could be scored.
    """
    return {
        int(row.rally_id): {"near": row.near_player, "far": row.far_player}
        for row in per_point_df.itertuples()
    }


def relabel_near_far_to_stable(events_df, rally_stable_labels):
    """Second relabel pass: events_df's player_side values of literally
    'near'/'far' (output of player_identity.py's per-rally resolution)
    get converted to a match-stable 'player_1'/'player_2' identity, using
    scoring.py's end-change-aware mapping (rally_stable_labels).

    Anything that ISN'T literally 'near' or 'far' -- a raw track_id
    string from a rally player_identity.py couldn't resolve, 'unknown',
    or None -- passes through unchanged. Same passthrough principle as
    player_identity.py's own relabel functions: never guess, let
    unresolved stay visibly unresolved downstream.
    """
    out = events_df.copy()
    out["player_side"] = [
        rally_stable_labels.get(rid, {}).get(val, val)
        for rid, val in zip(out["rally_id"], out["player_side"])
    ]
    return out


def main():
    match_data_df = pd.read_csv(config.MATCH_CSV)
    events_df = pd.read_csv(config.EVENTS_CSV)

    # ── Pass 1: raw track_id -> near/far, per rally ─────────────────────
    labels, qa_df = player_identity.compute_rally_near_far_labels(match_data_df, events_df)
    n_total = len(qa_df)
    n_resolved = len(labels)
    print(f"[Pass 1] Player identity: resolved near/far for {n_resolved}/{n_total} rallies")
    if n_resolved < n_total:
        unresolved = qa_df[~qa_df["resolved"]]
        print(f"  {len(unresolved)} unresolved -- reason breakdown:")
        print(unresolved["reason"].value_counts().to_string())

    resolved_events_df = player_identity.relabel_events_to_near_far(events_df, labels)
    resolved_events_df.to_csv(RESOLVED_EVENTS_CSV, index=False)
    print(f"[Pass 1] Saved near/far-resolved events to {RESOLVED_EVENTS_CSV}")

    # ── Pass 2: near/far -> match-stable player_1/player_2 ──────────────
    # rally_outcomes.rally_outcomes()'s winner/loser/server are DERIVED
    # from player_side, so calling it on the Pass-1-relabeled events
    # produces an outcomes_df whose winner/loser/server already read
    # near/far -- exactly the input shape score_match_near_far() expects.
    outcomes_df = rally_outcomes.rally_outcomes(resolved_events_df)

    per_point_df, score_summary = scoring.score_match_near_far(outcomes_df)
    print(f"\n[Pass 2] Scoring summary:")
    for k, v in score_summary.items():
        print(f"  {k}: {v}")

    rally_stable_labels = build_rally_stable_labels(per_point_df)
    stable_events_df = relabel_near_far_to_stable(resolved_events_df, rally_stable_labels)
    stable_events_df.to_csv(STABLE_EVENTS_CSV, index=False)
    print(f"[Pass 2] Saved stable-identity events to {STABLE_EVENTS_CSV}")

    n_still_positional = stable_events_df["player_side"].isin(["near", "far"]).sum()
    n_still_track_id = stable_events_df["player_side"].astype(str).str.startswith("track_").sum()
    print(f"Rows still 'near'/'far' (not converted to stable id): {n_still_positional} "
          f"-- expected 0 unless a rally_id in events_df wasn't in per_point_df.")
    print(f"Rows still raw track_id (Pass 1 never resolved these): {n_still_track_id}")

    # ── Step 3: run match_stats -> prioritization -> report on STABLE data ──
    full_report = report.generate_report(str(STABLE_EVENTS_CSV), player_csv=None)
    return full_report


if __name__ == "__main__":
    main()
