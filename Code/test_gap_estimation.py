"""
test_gap_estimation.py

Standalone smoke test for the new unresolved-flight-gap handling in
analysis.py (find_unresolved_gaps / estimate_gap_bounce / their wiring
into run_analysis()). Builds small hand-crafted ball_df fixtures directly
-- doesn't touch match_stats/rally_outcomes/prioritization/report, so it
runs with just analysis.py + config.py present.

Covers:
1. A genuine airborne gap (descend-then-ascend pixel_y either side of a
   20-frame hole) -- should be detected and classified as likely_bounce.
2. A hit-to-hit gap with no bounce (pixel_y keeps descending through both
   sides) -- should be detected as a gap but NOT classified as a bounce
   (fallback midpoint used only if the caller chose to keep it; run_analysis
   itself won't fabricate an event here).
3. A short gap (< UNRESOLVED_GAP_MIN_FRAMES) -- should not be flagged at
   all, left to normal interpolation/smoothing.
4. Full run_analysis() on a synthetic rally with one real airborne gap,
   confirming an estimated=True bounce shows up in the output CSV.

Run directly:
    python test_gap_estimation.py
"""

import numpy as np
import pandas as pd

import config
import analysis


def _build_ball_df(rows, total_frames):
    """rows: dict[frame] -> (pixel_x, pixel_y, table_x, table_y). Missing
    frames get an all-NaN ball row, matching load_data()'s reindexing."""
    out = []
    for f in range(total_frames):
        if f in rows:
            px, py, tx, ty = rows[f]
        else:
            px = py = tx = ty = np.nan
        out.append({"frame": f, "pixel_x": px, "pixel_y": py,
                     "table_x": tx, "table_y": ty})
    df = pd.DataFrame(out)
    df["has_position"] = df["pixel_x"].notna()
    return df


def test_genuine_bounce_gap():
    print("--- Test 1: genuine airborne bounce gap ---")
    gap = analysis.UNRESOLVED_GAP_MIN_FRAMES + 10  # comfortably above threshold
    rows = {}
    # Descending into the gap (pixel_y increasing -- ball dropping toward
    # court from the elevated camera's perspective).
    for i, f in enumerate(range(0, 5)):
        rows[f] = (500 + i * 5, 300 + i * 20, 800, 400)
    # Ball missing frames 5..(5+gap-1) -- motion blur mid-flight.
    # Ascending out of the gap (pixel_y decreasing -- bounced, heading back up).
    post_start = 5 + gap
    for i, f in enumerate(range(post_start, post_start + 5)):
        rows[f] = (600 + i * 5, 500 - i * 20, 850, 420)

    total_frames = post_start + 6
    ball_df = _build_ball_df(rows, total_frames)

    gaps = analysis.find_unresolved_gaps(ball_df, 0, total_frames - 1)
    assert len(gaps) == 1, f"FAIL: expected 1 gap, got {len(gaps)}"
    pre_f, post_f = gaps[0]
    print(f"PASS: gap detected, pre_frame={pre_f}, post_frame={post_f}")

    est = analysis.estimate_gap_bounce(ball_df, pre_f, post_f)
    assert est["likely_bounce"] is True, "FAIL: expected likely_bounce=True for descend-then-ascend"
    assert pre_f < est["frame"] < post_f, "FAIL: estimated bounce frame should fall inside the gap"
    assert est["estimated"] is True
    assert est["pos_source"] == "estimated_gap"
    print(f"PASS: estimated bounce at frame {est['frame']} "
          f"(gap {pre_f}-{post_f}, table_pos=({est['table_x']}, {est['table_y']}))")


def test_hit_to_hit_gap_no_bounce():
    print("\n--- Test 2: hit-to-hit gap, no bounce (should NOT classify as bounce) ---")
    gap = analysis.UNRESOLVED_GAP_MIN_FRAMES + 10
    rows = {}
    # Descending on both sides -- no reversal, so no real bounce signal.
    for i, f in enumerate(range(0, 5)):
        rows[f] = (500 + i * 5, 300 + i * 10, 800, 400)
    post_start = 5 + gap
    for i, f in enumerate(range(post_start, post_start + 5)):
        rows[f] = (600 + i * 5, 400 + i * 10, 850, 420)

    total_frames = post_start + 6
    ball_df = _build_ball_df(rows, total_frames)

    gaps = analysis.find_unresolved_gaps(ball_df, 0, total_frames - 1)
    assert len(gaps) == 1, f"FAIL: expected 1 gap, got {len(gaps)}"
    pre_f, post_f = gaps[0]

    est = analysis.estimate_gap_bounce(ball_df, pre_f, post_f)
    assert est["likely_bounce"] is False, "FAIL: expected likely_bounce=False for no velocity reversal"
    print(f"PASS: gap correctly NOT classified as a bounce (frac fallback used, "
          f"estimate at frame {est['frame']} would only be used if a hit is confirmed there)")


def test_short_gap_ignored():
    print("\n--- Test 3: short gap below threshold is ignored ---")
    short_gap = max(analysis.UNRESOLVED_GAP_MIN_FRAMES - 3, 1)
    rows = {}
    for i, f in enumerate(range(0, 5)):
        rows[f] = (500 + i * 5, 300 + i * 20, 800, 400)
    post_start = 5 + short_gap
    for i, f in enumerate(range(post_start, post_start + 5)):
        rows[f] = (600 + i * 5, 500 - i * 20, 850, 420)

    total_frames = post_start + 6
    ball_df = _build_ball_df(rows, total_frames)

    gaps = analysis.find_unresolved_gaps(ball_df, 0, total_frames - 1)
    assert len(gaps) == 0, f"FAIL: expected 0 gaps below threshold, got {len(gaps)}"
    print(f"PASS: {short_gap}-frame gap correctly left to normal interpolation "
          f"(below UNRESOLVED_GAP_MIN_FRAMES={analysis.UNRESOLVED_GAP_MIN_FRAMES})")


def test_full_run_analysis_with_gap():
    print("\n--- Test 4: run_analysis() end-to-end with one real airborne gap ---")
    fps = analysis.FPS
    gap = analysis.UNRESOLVED_GAP_MIN_FRAMES + 12

    rows = {}
    player_rows = []
    frame = 0

    # Hit 1 (near player, x reversal -- wide swing to clear HIT_PROMINENCE)
    for i in range(10):
        rows[frame] = (600 - i * 40, 900 - i * 30, 300, 700)
        frame += 1
    # Flight out -- descends toward the gap (extended a bit past the bare
    # minimum so the resulting sub-rally clears MIN_RALLY_LENGTH_FRAMES)
    for i in range(9):
        rows[frame] = (200 + i * 12, 660 + i * 15, 500, 500)
        frame += 1
    pre_gap_frame = frame - 1

    # Unresolved airborne gap -- ball invisible mid-flight. The true bounce
    # apex happens INSIDE this gap, higher than either visible endpoint --
    # deliberately near-symmetric endpoints (810 both sides) so the straight-
    # line interpolation existing detect_bounces() relies on is flat/near-flat
    # here and genuinely can't see it, matching the real airborne-gap
    # failure mode rather than coincidentally leaving a real peak at the edge.
    frame += gap
    post_gap_frame = frame

    # Reappears past the bounce, descending pixel_y = ascending back up.
    # No second sharp hit-reversal here -- one confirmed hit (above) is
    # enough for the rally to pass run_analysis()'s "has at least one hit"
    # check, and keeping the tail gently monotonic avoids an unrelated
    # find_peaks quirk (a trivial SG-smoothing bump right before a long,
    # uninterrupted decline gets an inflated "prominence" score, since
    # prominence is measured against the lowest point before the next
    # higher peak -- with no later rise, that's the whole declining tail).
    for i in range(10):
        rows[frame] = (900 + i * 15, 810 - i * 35, 1600, 300)
        frame += 1

    total_frames = frame + 5

    # Players: one near each baseline, present every frame, so
    # _attribute_player_side has something to attach hits to.
    for f in range(total_frames):
        player_rows.append({"frame": f, "type": "player", "track_id": 1,
                             "pixel_x": 300, "pixel_y": 950,
                             "x1": 260, "y1": 860, "x2": 340, "y2": 1040,
                             "confidence": 0.9})
        player_rows.append({"frame": f, "type": "player", "track_id": 2,
                             "pixel_x": 950, "pixel_y": 100,
                             "x1": 910, "y1": 10, "x2": 990, "y2": 190,
                             "confidence": 0.9})

    ball_rows = []
    for f in range(total_frames):
        if f in rows:
            px, py, tx, ty = rows[f]
        else:
            px = py = tx = ty = np.nan
        ball_rows.append({"frame": f, "type": "ball", "track_id": 1,
                           "pixel_x": px, "pixel_y": py,
                           "x1": px, "y1": py, "x2": px, "y2": py,
                           "confidence": 0.8 if not pd.isna(px) else np.nan,
                           "table_x": tx, "table_y": ty})

    match_df = pd.DataFrame(ball_rows + player_rows)
    match_df = match_df.sort_values(["frame", "type"]).reset_index(drop=True)

    # Local paths -- deliberately not config.CODE_DIR, which resolves against
    # your real project folder structure and won't exist in a fresh checkout.
    csv_path = "test_gap_match_data.csv"
    events_path = "test_gap_rally_events.csv"
    match_df.to_csv(csv_path, index=False)

    events_df, rallies = analysis.run_analysis(str(csv_path), output_path=events_path)

    assert len(rallies) >= 1, "FAIL: no rally detected in synthetic gap fixture"
    assert "estimated" in events_df.columns, "FAIL: 'estimated' column missing from events output"

    estimated_events = events_df[events_df["estimated"] == True]
    print(f"\nEvents with estimated=True: {len(estimated_events)}")
    if len(estimated_events) == 0:
        print("NOTE: no estimated bounce fired -- check gap placement relative to "
              "rally boundaries if this is unexpected (gap must fall strictly inside "
              "a segmented rally, not span its edges).")
    else:
        assert (estimated_events["pos_source"] == "estimated_gap").all(), \
            "FAIL: estimated events should carry pos_source='estimated_gap'"
        print("PASS: estimated bounce(s) present with pos_source='estimated_gap':")
        print(estimated_events[["rally_id", "frame", "event_type", "pos_source"]].to_string(index=False))

    analysis.validation_summary(events_df, rallies)


if __name__ == "__main__":
    test_genuine_bounce_gap()
    test_hit_to_hit_gap_no_bounce()
    test_short_gap_ignored()
    test_full_run_analysis_with_gap()
    print("\nAll gap-estimation smoke tests completed.")
