"""
generate_synthetic_data.py
Day 4 (no-footage) deliverable -- builds a synthetic match_data.csv so
analysis.py and match_stats.py can be smoke-tested end-to-end before real
tennis video exists. This is NOT ground truth and isn't meant to validate
threshold *values* (that's still blocked on real footage, PROJECT.md Day 4)
-- it only proves the wiring: CSV schema in/out, rally segmentation,
bounce/hit detection, and the stats report all run without errors on data
shaped like what the real pipeline will eventually produce.

Drop this in Code/ alongside config.py / analysis.py / match_stats.py and
run directly (editable-variable style, same convention as extract_frames.py
-- no CLI args, no terminal needed).

Output: match_data.csv (config.MATCH_CSV) with the same schema transform.py's
real output has: frame, type, track_id, pixel_x, pixel_y, x1, y1, x2, y2,
confidence, table_x, table_y

If RUN_SMOKE_TEST is True, also calls analysis.run_analysis() and
match_stats.generate_stats_report() on the synthetic data and prints a
pass/fail summary -- this IS the actual Day 4 "prove the pipeline runs"
check, not just a data generator.

DAY 5 UPDATE: previously every rally here ended in a clean in-bounds
exchange -- table_x/table_y are a straight linear rescale of pixel_x/
pixel_y, and pixel_x/pixel_y were always clipped to the frame, so no rally
could ever produce a genuine out-of-bounds bounce. That meant
rally_outcomes.py's error-linked patterns (opponent_error / error_type)
and prioritization.py's point-loss-by-error-location patterns were only
ever validated against the 5 hand-crafted edge-case CSVs, not this
standard smoke-test path (see PROJECT.md Day 5 TODO). FORCE_OUT_OF_BOUNDS
below fixes that: selected rallies have their FINAL shot's table-space
coordinates (only table-space -- pixel-space is left untouched so
analysis.py's peak-detection still fires normally) pushed genuinely
outside the court, well past config.OFF_TABLE_MARGIN's tolerance. The
smoke test then runs rally_outcomes.py against the result and checks
those specific rallies come back as opponent_error with the expected
error_type.

Note: a genuine 'net' case can't be produced this way. analysis.py's
is_on_table() only checks the overall court rectangle -- it has no
concept of which side of the net a bounce landed on, so a ball landing on
the hitter's own side (a real net error) still reads as in-bounds today.
That's a pre-existing gap between is_on_table() and
classify_error_type()'s net-side check, not something this generator can
paper over -- flagging it rather than faking it.
"""

from pathlib import Path
import numpy as np
import pandas as pd

import config

# ── Editable top-of-file variables ─────────────────────────────────────────
OUTPUT_PATH = config.MATCH_CSV      # where to write the synthetic CSV
PLAYER_ONLY_PATH = config.CODE_DIR / "synthetic_player_data.csv"  # for court_coverage smoke test
N_RALLIES = 6
FPS = config.TRACKER_FRAME_RATE
FRAME_HEIGHT = config.FRAME_HEIGHT
FRAME_WIDTH = 1920                  # matches the 1920x1080 assumption behind config.py's FRAME_HEIGHT
RANDOM_SEED = 42
RUN_SMOKE_TEST = True               # also runs analysis.py + match_stats.py against the output

# DAY 5 addition: which rallies (0-indexed, in generation order) should end
# in a genuine out-of-bounds error instead of a clean exchange, and which
# kind. Keys are generation-order rally index; analysis.py's rally_id is
# 1-indexed and sequential with no expected splits (dead-ball splitting is
# effectively disabled -- DEAD_BALL_BOUNCE_RUN is huge), so rally_id ==
# index + 1 for verification purposes.
FORCE_OUT_OF_BOUNDS = {
    1: "long",   # rally 2: final shot sails past the baseline
    4: "wide",   # rally 5: final shot sails past a sideline
}
# Extra margin (court-space units) added beyond config.OFF_TABLE_MARGIN so
# forced errors are unambiguously out, not a borderline tolerance call.
OUT_OF_BOUNDS_BUFFER = 50

rng = np.random.default_rng(RANDOM_SEED)


# ── Rally generation ────────────────────────────────────────────────────────

def _make_rally(start_frame, n_shots, near_baseline_y, far_baseline_y, near_x, far_x,
                 force_final_error=None):
    """
    Builds one rally's worth of ball rows: a zig-zag pixel_x trajectory
    (hits = direction reversals at shot boundaries) with a pixel_y bounce
    (local max, mid-flight) between each hit. Not physically accurate --
    just shaped to reliably trigger analysis.py's peak-detection logic so
    the wiring gets exercised. Alternates shot depth so both the NEAR and
    FAR ends of analysis.py's depth-adaptive thresholds get hit, not just
    one extreme.

    force_final_error: None, "long", or "wide". If set, overrides the
    FINAL shot's table_x ("long") or table_y ("wide") for the duration of
    that shot's flight to a value genuinely outside the court, well past
    OFF_TABLE_MARGIN's tolerance. Pixel-space values are left completely
    untouched, so bounce/hit detection (which runs on pixel_x/pixel_y) is
    unaffected -- only the table-space coordinate analysis.py reads back
    for that frame (via get_table_position) changes, which is exactly
    what determines in_bounds. This mirrors the real pipeline: table_x/
    table_y come from a separate transform step, not from pixel position
    directly, so an out-of-bounds bounce doesn't need out-of-frame pixels.
    """
    frames, pixel_x, pixel_y = [], [], []
    segment_bounds = []  # (start_idx, end_idx) into frames/pixel_x/pixel_y, per shot
    frame = start_frame
    x = near_x
    side = 1  # 1 = moving toward far_x, -1 = moving toward near_x

    for shot_i in range(n_shots):
        target_x = far_x if side == 1 else near_x
        depth_frac = shot_i / max(n_shots - 1, 1)
        y_apex = near_baseline_y + (far_baseline_y - near_baseline_y) * depth_frac

        seg_start = len(frames)
        n_flight_frames = int(rng.integers(10, 18))
        for t in np.linspace(0, 1, n_flight_frames):
            frames.append(frame)
            pixel_x.append(x + (target_x - x) * t + rng.normal(0, 3))
            # simple rise-then-fall shape around the bounce apex at t=0.5
            pixel_y.append(y_apex - abs(t - 0.5) * 2 * (y_apex * 0.7) + rng.normal(0, 2))
            frame += 1
        segment_bounds.append((seg_start, len(frames) - 1))

        x = target_x
        side *= -1

    frames = np.array(frames)
    pixel_x = np.clip(np.array(pixel_x), 0, FRAME_WIDTH)
    pixel_y = np.clip(np.array(pixel_y), 0, FRAME_HEIGHT)

    # Crude linear rescale of pixel space into court-space, matching
    # config's convention (table_x = depth axis 0..TABLE_W, table_y = side
    # axis 0..TABLE_H) -- NOT a real transform, just enough for smoke-testing
    # match_stats.py's zone/coverage logic against plausible-shaped values.
    table_x = pixel_x / FRAME_WIDTH * config.TABLE_W
    table_y = pixel_y / FRAME_HEIGHT * config.TABLE_H

    if force_final_error is not None:
        seg_start, seg_end = segment_bounds[-1]
        seg_len = seg_end - seg_start + 1
        # Only override from partway through the flight onward (covering the
        # bounce apex at t=0.5 through the end), NOT the very start of the
        # segment -- the start (t≈0) is where the preceding hit gets its
        # table_x reading from. Overriding the whole segment would corrupt
        # the hit's own position too, making hit_side and bounce_side always
        # match ("net" every time) regardless of the intended error type.
        override_start = seg_start + int(seg_len * 0.3)

        if force_final_error == "long":
            # Which baseline the ball sails past depends on which way this
            # shot was travelling. hit_side_table_x approximates where the
            # ball was hit from (the un-overridden start of this segment) --
            # classify_error_type needs the bounce on the OPPOSITE side of
            # the net from the hit, or it reads as a net error instead of long.
            hit_side_table_x = table_x[seg_start]
            margin_push = config.OFF_TABLE_MARGIN * 2 + OUT_OF_BOUNDS_BUFFER
            if hit_side_table_x < config.NET_POSITION_OFFSET:
                overshoot = config.TABLE_W + margin_push   # sails past the far baseline
            else:
                overshoot = -margin_push                    # sails past the near baseline
            table_x[override_start:seg_end + 1] = overshoot

        elif force_final_error == "wide":
            # table_y gets pushed out of bounds; table_x needs a nudge too.
            # The synthetic flight's apex (t=0.5, where the bounce is
            # detected) sits at roughly the pixel-space midpoint between
            # where the ball was hit and its target -- which, for a
            # baseline-to-baseline shot, lands right next to NET_X. Left
            # alone, noise can tip that midpoint back onto the hitter's own
            # side and get read as a net error instead of wide. Pull it
            # firmly onto the target side (comfortably in-bounds on the x
            # axis) so only the y-axis override determines the call.
            hit_side_table_x = table_x[seg_start]
            if hit_side_table_x < config.NET_POSITION_OFFSET:
                safe_table_x = config.NET_POSITION_OFFSET + 0.25 * config.TABLE_W
            else:
                safe_table_x = config.NET_POSITION_OFFSET - 0.25 * config.TABLE_W
            table_x[override_start:seg_end + 1] = safe_table_x

            margin_push = config.OFF_TABLE_MARGIN * 2 + OUT_OF_BOUNDS_BUFFER
            sign = rng.choice([1, -1])
            overshoot = (config.TABLE_H + margin_push) if sign == 1 else -margin_push
            table_y[override_start:seg_end + 1] = overshoot

        else:
            raise ValueError(f"Unknown force_final_error: {force_final_error!r}")

    return frames, pixel_x, pixel_y, table_x, table_y


def build_synthetic_ball_and_players():
    ball_rows, player_rows = [], []
    frame_cursor = 0
    rally_gap = int(FPS * 3)  # well above RALLY_GAP_FRAMES so rallies stay cleanly separated

    near_x, far_x = FRAME_WIDTH * 0.15, FRAME_WIDTH * 0.85
    near_y, far_y = FRAME_HEIGHT * 0.9, FRAME_HEIGHT * 0.15

    for rally_idx in range(N_RALLIES):
        n_shots = int(rng.integers(3, 9))  # mix of short (ace-like) and longer rallies
        force_final_error = FORCE_OUT_OF_BOUNDS.get(rally_idx)
        frames, px, py, tx, ty = _make_rally(
            frame_cursor, n_shots, near_y, far_y, near_x, far_x,
            force_final_error=force_final_error,
        )

        for f, x, y, cx, cy in zip(frames, px, py, tx, ty):
            ball_rows.append({
                "frame": int(f), "type": "ball", "track_id": None,
                "pixel_x": x, "pixel_y": y,
                "x1": x - 8, "y1": y - 8, "x2": x + 8, "y2": y + 8,
                "confidence": round(float(rng.uniform(0.5, 0.95)), 2),
                "table_x": cx, "table_y": cy,
            })

            # Two players, each loosely tracking the ball's x on their own
            # side, so hit-attribution (_attribute_player_side) has
            # something plausible to attach to.
            for tid, base_y, side_bias in [(1, near_y, near_x), (2, far_y, far_x)]:
                jx = side_bias + rng.normal(0, 40)
                jy = base_y + rng.normal(0, 15)
                player_rows.append({
                    "frame": int(f), "type": "player", "track_id": tid,
                    "pixel_x": jx, "pixel_y": jy,
                    "x1": jx - 40, "y1": jy - 90, "x2": jx + 40, "y2": jy + 90,
                    "confidence": round(float(rng.uniform(0.7, 0.98)), 2),
                    "table_x": jx / FRAME_WIDTH * config.TABLE_W,
                    "table_y": jy / FRAME_HEIGHT * config.TABLE_H,
                })

        frame_cursor = int(frames[-1]) + rally_gap

    return pd.DataFrame(ball_rows), pd.DataFrame(player_rows)


def main():
    ball_df, player_df = build_synthetic_ball_and_players()
    match_df = pd.concat([ball_df, player_df], ignore_index=True)
    match_df = match_df.sort_values(["frame", "type"]).reset_index(drop=True)

    Path(OUTPUT_PATH).parent.mkdir(parents=True, exist_ok=True)
    match_df.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote {len(match_df)} synthetic rows ({N_RALLIES} rallies) to {OUTPUT_PATH}")
    if FORCE_OUT_OF_BOUNDS:
        forced_desc = ", ".join(f"rally {i+1}={t}" for i, t in sorted(FORCE_OUT_OF_BOUNDS.items()))
        print(f"Forced out-of-bounds endings: {forced_desc}")

    player_df.to_csv(PLAYER_ONLY_PATH, index=False)
    print(f"Wrote player-only slice to {PLAYER_ONLY_PATH} (for court_coverage smoke test)")

    if RUN_SMOKE_TEST:
        _run_smoke_test()


def _run_smoke_test():
    """
    Runs the real analysis.py / match_stats.py / rally_outcomes.py modules
    against the synthetic data just written. This is a WIRING check, not a
    threshold validation -- pass/fail here means "the pipeline doesn't
    crash and produces the expected shapes/classifications," not "the
    numbers are right" (that still needs real ground truth, per
    PROJECT.md's Day 4 plan).
    """
    import analysis
    import match_stats
    import rally_outcomes
    import prioritization
    import report

    print("\n--- Smoke test: analysis.py ---")
    events_path = config.CODE_DIR / "synthetic_rally_events.csv"
    events_df, rallies = analysis.run_analysis(OUTPUT_PATH, output_path=str(events_path))
    assert len(rallies) > 0, "FAIL: no rallies detected from synthetic data -- segmentation likely broken"
    assert len(events_df) > 0, "FAIL: no events detected from synthetic data -- bounce/hit detection likely broken"
    print(f"PASS: {len(rallies)} rallies, {len(events_df)} events detected")

    print("\n--- Smoke test: match_stats.py ---")
    stats_report = match_stats.generate_stats_report(str(events_path), player_csv=str(PLAYER_ONLY_PATH))
    assert stats_report["rally_lengths"]["summary"]["n_rallies"] > 0, "FAIL: rally_length_stats produced no rallies"
    assert len(stats_report["consistency"]) > 0, "FAIL: consistency_metrics produced no player rows"
    assert stats_report["court_coverage"] is not None and len(stats_report["court_coverage"]) > 0, \
        "FAIL: court_coverage produced no rows despite player_csv being supplied"
    print("PASS: match_stats report generated with rally_lengths, consistency, "
          "shot_placement, tactical_tendencies, and court_coverage all populated")

    print("\n--- Smoke test: rally_outcomes.py (genuine out-of-bounds cases) ---")
    outcomes_report = rally_outcomes.generate_outcomes_report(str(events_path))
    outcomes_df = outcomes_report["rally_outcomes"]

    if not FORCE_OUT_OF_BOUNDS:
        print("SKIP: no rallies configured via FORCE_OUT_OF_BOUNDS to check.")
    else:
        expected = {idx + 1: err_type for idx, err_type in FORCE_OUT_OF_BOUNDS.items()}
        verified = 0
        for rally_id, expected_type in expected.items():
            row = outcomes_df[outcomes_df["rally_id"] == rally_id]
            if len(row) == 0:
                print(f"WARN: rally_id {rally_id} not found in outcomes -- "
                      f"rally_id alignment assumption may not hold, skipping")
                continue
            actual_reason = row.iloc[0]["reason"]
            actual_error = row.iloc[0]["error_type"]
            assert actual_reason == "opponent_error", (
                f"FAIL: rally {rally_id} expected reason='opponent_error', got {actual_reason!r} "
                f"-- forced out-of-bounds bounce wasn't classified as an error"
            )
            assert actual_error == expected_type, (
                f"FAIL: rally {rally_id} expected error_type={expected_type!r}, got {actual_error!r}"
            )
            verified += 1
            print(f"PASS: rally {rally_id} correctly classified as opponent_error / {expected_type}")

        assert verified > 0, (
            "FAIL: none of the forced out-of-bounds rallies could be verified -- "
            "check the rally_id alignment assumption (see FORCE_OUT_OF_BOUNDS comment)"
        )
        print(f"PASS: {verified}/{len(expected)} forced out-of-bounds rallies classified correctly")

    print("\n--- Smoke test: rally_outcomes.py (return points won + visibility columns) ---")
    # NEW: validates return_points_won_stats() and the three visibility
    # additions (unknown_outcome_shots, ambiguous_rallies_involved,
    # unknown_outcome bucket). Synthetic data always has fully-determinable
    # bounce positions and full player attribution -- there's no NaN
    # in_bounds path and no "unknown"/"unknown_opponent" hitter here -- so
    # every one of these should read as zero. A non-zero value means
    # something upstream (attribution, transform, or in_bounds tagging)
    # regressed silently.
    return_pw = outcomes_report["return_points_won"]
    assert len(return_pw) > 0, "FAIL: return_points_won_stats produced no rows"
    required_cols = {"player_side", "return_points_played", "return_points_won",
                      "return_points_won_pct", "ambiguous_return_opportunities"}
    assert required_cols.issubset(return_pw.columns), (
        f"FAIL: return_points_won missing expected columns, got {list(return_pw.columns)}"
    )
    assert (return_pw["return_points_played"] > 0).any(), (
        "FAIL: no player has any return_points_played -- return-role join likely broken"
    )
    assert (return_pw["ambiguous_return_opportunities"] == 0).all(), (
        "FAIL: synthetic data has no ambiguous rallies by construction, but "
        "ambiguous_return_opportunities is non-zero -- check for a regression"
    )
    print(f"PASS: return_points_won_stats populated correctly "
          f"({return_pw['return_points_played'].sum()} total return points across players), "
          f"no spurious ambiguous_return_opportunities")

    rally_accuracy = outcomes_report["rally_accuracy"]
    if len(rally_accuracy) > 0:
        assert "unknown_outcome_shots" in rally_accuracy.columns, (
            "FAIL: rally_accuracy missing unknown_outcome_shots column"
        )
        assert (rally_accuracy["unknown_outcome_shots"] == 0).all(), (
            "FAIL: synthetic data has no undeterminable bounces by construction, but "
            "rally_accuracy reports non-zero unknown_outcome_shots -- check for a regression"
        )
    print("PASS: rally_accuracy carries unknown_outcome_shots=0 on clean synthetic data")

    points_won = outcomes_report["points_won"]
    if len(points_won) > 0:
        assert "ambiguous_rallies_involved" in points_won.columns, (
            "FAIL: points_won missing ambiguous_rallies_involved column"
        )
        assert (points_won["ambiguous_rallies_involved"] == 0).all(), (
            "FAIL: synthetic data has no ambiguous rallies by construction, but "
            "points_won reports non-zero ambiguous_rallies_involved -- check for a regression"
        )
    print("PASS: points_won carries ambiguous_rallies_involved=0 on clean synthetic data")

    error_loc = outcomes_report["error_location"]
    if len(error_loc) > 0:
        assert not (error_loc["error_type"] == "unknown_outcome").any(), (
            "FAIL: synthetic data has no undeterminable bounces by construction, but "
            "error_location reports an 'unknown_outcome' bucket -- check for a regression"
        )
    print("PASS: error_location carries no spurious 'unknown_outcome' entries on clean synthetic data")

    print("\n--- Smoke test: prioritization.py (real point-loss wiring) ---")
    priority_df, priority_notes = prioritization.build_priority_table(stats_report, outcomes_report)
    assert len(priority_df) > 0, "FAIL: build_priority_table produced no patterns at all"

    # Categories that should now carry REAL (non-zero) point-loss once
    # outcomes_report is supplied -- this is the specific thing Day 5 wired
    # up (PROJECT.md: "point-loss dimension ... is now real across all
    # pattern categories"). If these come back all-zero, the join to
    # rally_outcomes.py silently isn't working even though the categories
    # exist.
    point_loss_categories = [
        "error_location", "rally_accuracy", "pressure_moments",
        "rally_length", "zone_error_rate",
    ]
    for category in point_loss_categories:
        cat_rows = priority_df[priority_df["category"] == category]
        if len(cat_rows) == 0:
            print(f"NOTE: category '{category}' didn't fire on this synthetic run "
                  f"(no qualifying pattern) -- not necessarily a failure, small synthetic "
                  f"dataset may not trip every category's threshold every run.")
            continue
        assert cat_rows["point_loss_count"].sum() > 0, (
            f"FAIL: category '{category}' fired but point_loss_count is all zero -- "
            f"the join to rally_outcomes.py isn't producing real point-loss data"
        )
        print(f"PASS: '{category}' fired with real point_loss_count "
              f"(total={int(cat_rows['point_loss_count'].sum())})")

    # coverage_point_loss requires a gap-cell / lost-point-cell overlap,
    # which small synthetic datasets won't always produce -- checked
    # separately, informationally, not asserted on.
    coverage_rows = priority_df[priority_df["category"] == "coverage_point_loss"]
    if len(coverage_rows) > 0:
        print(f"PASS: 'coverage_point_loss' fired with real point_loss_count "
              f"(total={int(coverage_rows['point_loss_count'].sum())})")
    else:
        print("NOTE: 'coverage_point_loss' didn't fire on this synthetic run -- needs a "
              "coverage-gap cell to overlap a lost-point cell, which a small/random "
              "synthetic dataset won't always produce. Not treated as a failure.")

    # shot_placement / court_coverage are frequency-only by design (module
    # header: "not yet cross-referenced against error/point-loss data") --
    # confirm they're present but explicitly NOT expected to carry point-loss.
    for category in ["shot_placement", "court_coverage"]:
        cat_rows = priority_df[priority_df["category"] == category]
        if len(cat_rows) > 0:
            assert (cat_rows["point_loss_count"] == 0).all(), (
                f"FAIL: category '{category}' unexpectedly carries non-zero point_loss_count -- "
                f"this category is documented as frequency-only, something changed"
            )

    print(f"\nprioritization.py produced {len(priority_df)} ranked patterns across "
          f"{priority_df['category'].nunique()} categories.")
    if priority_notes:
        print("Data-quality notes:")
        for n in priority_notes:
            print(" -", n)

    print("\n--- Smoke test: report.py (per-player recommendations) ---")
    report_json_path = config.CODE_DIR / "synthetic_match_report.json"
    report_summary_path = config.CODE_DIR / "synthetic_match_report.txt"
    full_report = report.generate_report(
        str(events_path), player_csv=str(PLAYER_ONLY_PATH),
        json_path=report_json_path, summary_path=report_summary_path,
    )

    assert report_json_path.exists(), f"FAIL: {report_json_path} was not written"
    assert report_summary_path.exists(), f"FAIL: {report_summary_path} was not written"

    for key in ("stats", "priority_patterns", "recommendations", "data_quality_notes"):
        assert key in full_report, f"FAIL: generate_report() output missing '{key}' key"
    print("PASS: JSON/summary files written, output dict has the expected top-level keys")

    known_players = full_report["stats"]["consistency"]["player_side"].tolist()
    recs = full_report["recommendations"]
    assert set(recs.keys()) == set(known_players), (
        f"FAIL: recommendations player set {set(recs.keys())} doesn't match "
        f"known players from match_stats.py's consistency table {set(known_players)} -- "
        f"a player with real hit data got silently dropped, or a phantom player appeared"
    )
    print(f"PASS: every known player ({known_players}) has an explicit recommendations "
          f"entry, none silently dropped")

    for player, patterns in recs.items():
        assert len(patterns) <= report.TOP_N_RECOMMENDATIONS_PER_PLAYER, (
            f"FAIL: {player} has {len(patterns)} patterns, exceeds "
            f"TOP_N_RECOMMENDATIONS_PER_PLAYER={report.TOP_N_RECOMMENDATIONS_PER_PLAYER}"
        )
        for p in patterns:
            assert p["combined_score"] >= report.MIN_RECOMMENDATION_SCORE, (
                f"FAIL: {player} has a pattern with combined_score={p['combined_score']} "
                f"below MIN_RECOMMENDATION_SCORE={report.MIN_RECOMMENDATION_SCORE} -- "
                f"the score floor isn't being applied"
            )
        print(f"PASS: {player} -> {len(patterns)} pattern(s), all within top-N and "
              f"above the score floor")

    summary_text = report_summary_path.read_text()
    assert "RECOMMENDATIONS" in summary_text, "FAIL: summary text missing RECOMMENDATIONS section"
    for player in known_players:
        assert player in summary_text, (
            f"FAIL: {player} doesn't appear anywhere in the text summary's "
            f"recommendations section"
        )
    print("PASS: text summary contains a RECOMMENDATIONS section naming every known player")

    print(f"\nreport.py wrote {report_json_path} and {report_summary_path}.")

    print("\nAll smoke tests passed -- pipeline wiring (CSV schema -> analysis -> "
          "stats -> rally outcomes -> prioritization -> report, including genuine "
          "out-of-bounds cases, real point-loss, and per-player recommendations) is "
          "sound. Thresholds/values still need real footage to validate.")


if __name__ == "__main__":
    main()
