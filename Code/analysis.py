"""
analysis.py (reconstructed from session content for local diagnostic use)
"""

import pandas as pd
import numpy as np
from scipy.signal import savgol_filter, find_peaks

import config


FPS = config.TRACKER_FRAME_RATE

RALLY_GAP_FRAMES = int(round(FPS * 1.5))
MIN_RALLY_LENGTH_FRAMES = int(round(FPS * 0.5))
SAVGOL_WINDOW = 5
SAVGOL_POLYORDER = 2
MAX_TABLE_LOOKUP_WINDOW = 5

BOUNCE_PROMINENCE_NEAR_PX = 9.0
BOUNCE_PROMINENCE_FAR_PX = 2.5
BOUNCE_MIN_SEPARATION_FRAMES = 6
BOUNCE_PROMINENCE_WLEN_FRAMES = BOUNCE_MIN_SEPARATION_FRAMES * 4

TABLE_LENGTH_UNITS = config.TABLE_W
TABLE_WIDTH_UNITS = config.TABLE_H
# In/out call tolerance. FIX 2026-09-27: this used to be config.OFF_TABLE_MARGIN
# (150 cm -- the "is this detection even near the court" margin), so a ball
# landing up to 1.5 m long was called IN, and one landing further out lost its
# position entirely (ambiguous). Result: every real match showed 0% out.
# 10 cm ~ line width + calibration slack; a ball touching the line is in.
TABLE_EDGE_TOLERANCE_UNITS = config.IN_OUT_TOLERANCE_CM
BOUNCE_POSITION_MAX_OFF_COURT_CM = 1000   # beyond this, an unclipped projection is treated as bad data

HIT_PROMINENCE_NEAR_PX = 180
HIT_PROMINENCE_FAR_PX = 60
HIT_MIN_SEPARATION_FRAMES = 8
HIT_PROMINENCE_WLEN_FRAMES = HIT_MIN_SEPARATION_FRAMES * 4

HIT_ATTRIBUTION_SEARCH_FRAMES = 3

PLAYER_PROXIMITY_MARGIN_NEAR_PX = 260
PLAYER_PROXIMITY_MARGIN_FAR_PX = 110

DEAD_BALL_BOUNCE_RUN = 10_000

# NEW 2026-09-14: single-frame-outlier rejection in smooth_rally_window().
# Confirmed real bug (frame 4698 in the merged rally-5 window, PROJECT.md
# 2026-09-13 Risks table): a one-frame anomalous position that jumps far
# from both neighbors and snaps back at the very next frame -- within
# OFF_TABLE_MARGIN so the existing off-court nulling doesn't catch it --
# gets fed into Savgol smoothing and read as a genuine detect_hits() peak
# once enough surrounding real data is in a merged window.
# Threshold empirically derived from real consecutive-frame ball
# displacement in match_data.csv: 95th percentile is ~35px, 99th jumps to
# ~1394px -- a clean bimodal split. Legitimate real ball motion (including
# fast post-bounce frames) essentially never exceeds ~150-200px in one
# frame at 30fps; the confirmed real outlier at frame 4698 jumped ~1530px,
# squarely in the same range as other confirmed-spurious jumps (1700-2100px)
# in this dataset. CAVEAT: derived from one real clip's distribution --
# revisit if real fast-motion footage (e.g. serves) shows legitimate
# single-frame jumps approaching this range.
OUTLIER_JUMP_THRESHOLD_PX = 400

EVENT_GAP_SPLIT_FRAMES = 90

UNRESOLVED_GAP_MIN_FRAMES = config.INTERPOLATION_LIMIT

# ── Impulse event detector (2026-09-27) ──────────────────────────────────
# Replaces detect_hits()'s pixel_x-reversal peaks and detect_bounces()'s
# pixel_y peaks, both inherited from the ping-pong app's SIDE-ON camera.
# This tennis camera sits behind the baseline: a hit mostly reverses the
# ball's DEPTH direction (image y), not x, and a bounce is a kink in the
# trajectory, not necessarily a y-peak. Both are a sudden change in
# velocity, so: fit the velocity over IMPULSE_FIT_FRAMES before and after
# each frame and flag frames where it jumps. The jump is measured in ball
# diameters per frame (divided by the ball box's own size), which
# normalizes out perspective without separate near/far constants.
# Tuned on job 76a383379d90 ground truth + checked on the tennis1_clip hold-out: events 2.3-13, background mostly < 2.
USE_IMPULSE_EVENTS = True
IN_PLAY_MARGIN_UNITS = 600          # cm wide of sidelines / behind near baseline before a ball is "off court" (players hit from 2-3m wide; in-flight height pushes the projection further out)
IMPULSE_FIT_FRAMES = 4
IMPULSE_MIN_POINTS_PER_SIDE = 2
IMPULSE_THRESHOLD = 2.4             # ball diameters / frame; F1 flat across 2.2-2.6 on both labeled clips
IMPULSE_MIN_SEPARATION_FRAMES = 8     # real hits/bounces in play are >= ~10 frames apart; one event can give two nearby peaks
IMPULSE_MAX_FIT_GAP_FRAMES = 6      # don't fit velocity across a longer detection gap
DUPLICATE_FRAME_PX = 1.5            # repeated video frame (see ball_linker.py)
# Hit vs bounce, by what the ball does AFTER the impulse (image-y speed
# over the next few frames, in ball diameters/frame; negative = moving up
# the image = away from this behind-baseline camera). A "ball inside the
# player's box" test does NOT work here: the camera is elevated behind the
# near player, so a bounce a few metres in front of them is drawn right on
# top of their body. Real data (job 76a383379d90): after a near-player hit
# the ball leaves at -2.5..-5 diam/frame; after a bounce it rises at most
# ~-1.5. A far-player hit sends the ball back TOWARD the camera (+).
HIT_DIRECTION_FRAMES = 6
NEAR_HIT_MAX_VY_AFTER = -2.0        # diam/frame after the event
FAR_HIT_MIN_VY_AFTER = 0.8
FAR_HIT_MAX_VY_BEFORE = 0.3
EVENT_SNAP_FRAMES = 3              # near-half events snap to the lowest image point within this many frames
REFINE_BOUNCE_KINK = True           # then bounces move to the trajectory's kink (see _kink_frame)
KINK_SEARCH_FRAMES = 4
KINK_BASELINE_FRAMES = 2

# Far-player hits inferred from a detection gap (2026-09-27). The ball model
# rarely sees the ball at the far player's contact (7/12 missed job-clip
# hits), but the trajectory around it is tracked: the ball heads away,
# vanishes, and reappears in the far half already coming back toward the
# camera ~11-17 frames after contact (serves: after the between-point pause).
# That return trip can only follow a far-player hit.
USE_GAP_HITS = True
GAP_HIT_MIN_GAP = 4                  # frames with no real ball detection
GAP_HIT_MAX_GAP = 200
GAP_HIT_NEW_POINT_GAP = 45           # longer gap = a new point, i.e. a far serve
GAP_HIT_MIN_VY_AFTER = 8.0           # px/frame toward the camera after reappearing
GAP_HIT_REAPPEAR_OFFSET = 13         # contact ~13 frames before the ball reappears (measured)
GAP_HIT_FAR_PROJ_X = 1500            # reappears over the far half (cm; in-air projection runs long)
GAP_HIT_DEDUPE_FRAMES = 20
GAP_HIT_CROSS_WITHIN = 40           # frames after reappearing to cross into the near half
GAP_HIT_MAX_RISE_PX = 25            # image-y pull-back allowed before crossing (a bounce is larger)

# Overhead contact (serves/smashes, 2026-09-29). A tossed ball is high in
# the air, so its ground projection lands past the net and the direction
# rule above can't call a near-player serve a hit (points 5/6 of
# ground_truth_points.csv). Contact ABOVE a player's head is unambiguous: a
# bounce can't happen there. Two guards against a far-court ball drawn
# above the near player's head: the ball box must be near-player sized
# relative to the player box, and the ball must leave much faster than it
# arrived (a toss falls slowly; a bounce loses speed).
USE_OVERHEAD_HITS = True
OVERHEAD_ABOVE_FRAC = 0.6            # contact zone: from 0.6 box-heights above the box top...
OVERHEAD_BELOW_FRAC = 0.25           # ...to 0.25 box-heights below it
OVERHEAD_SIDE_FRAC = 0.25            # box widths either side
OVERHEAD_MIN_BALL_TO_BOX = 0.028     # ball box size / player box height (near: ~26/720; far-court ball ~13)
OVERHEAD_MIN_SPEEDUP = 2.0           # speed after / speed before
OVERHEAD_MIN_SPEED_AFTER = 3.0       # ball diameters / frame
OVERHEAD_KEEP_FRAMES = 8             # keep "off-court" projections this close to an overhead detection
# A near-player serve flies AWAY from the camera, so on screen it can leave
# no faster than the toss fell and the speed-up rule misses it (point 7 of
# ground_truth_points.csv, 2026-10-21). The ball falling and then climbing
# the image above a player's head is a contact too: gravity can't reverse it
# there. The ball-size guard above still keeps far-court bounces out.
OVERHEAD_REVERSAL = True
OVERHEAD_REVERSAL_MIN_VY = 0.5       # ball diameters / frame, down before and up after

# Ball stopped by the net (2026-09-29). 7 of the 20 labeled points end in
# the net (mostly near-player serves) and the pipeline had no such event:
# the rally ended on a hit ("ambiguous"), was dropped as too short, or the
# dribble was read as a bounce IN the hitter's court (= hitter "won"). In
# the image the ball runs into the net band and stalls: x stops moving,
# only small dribbles in y. Its ground projection stays just past the net
# line (bottom of the net = the line; higher = further).
USE_NET_EVENTS = True
NET_STALL_WINDOW = 15                # frames after the stall starts
NET_STALL_MIN_POINTS = 6
NET_STALL_MAX_X_RANGE_PX = 70
NET_STALL_MAX_Y_RANGE_PX = 160
NET_STALL_MIN_SPEED_BEFORE = 10.0    # px/frame: the ball was in flight
NET_STALL_MIN_APPROACH_PX = 60       # travel across / down the image in the 10 frames before (real nets: 86-335 px)
NET_STALL_MAX_RISE_PX = 30           # a netted ball drops or dribbles; it doesn't climb the image
NET_STALL_PROJ_MIN = -100            # cm relative to the net line
NET_STALL_PROJ_MAX = 800
NET_STALL_MAX_AFTER_HIT = 60         # frames: must follow a hit
PRE_SERVE_FILTER = True
PRE_SERVE_NO_HIT_FRAMES = 60         # no hit this long before = the ball is dead
PRE_SERVE_MAX_TRAVEL = 0.5          # ball stayed within this many player-heights over the last 30 frames
NET_IMPACT_FRAMES = 15               # an impulse this close before the stall is the net impact itself
NET_IMPACT_MAX_DIST_CM = 300         # ...if the ball is this close to the net line (a hit there = the ball off the tape)


def _interp_by_depth(pixel_y, frame_height, near_value, far_value):
    if pd.isna(pixel_y):
        return (near_value + far_value) / 2
    t = np.clip(pixel_y / frame_height, 0.0, 1.0)
    return far_value + t * (near_value - far_value)


def get_bounce_prominence(pixel_y, frame_height=config.FRAME_HEIGHT):
    return _interp_by_depth(pixel_y, frame_height,
                             BOUNCE_PROMINENCE_NEAR_PX, BOUNCE_PROMINENCE_FAR_PX)


def get_hit_prominence(pixel_y, frame_height=config.FRAME_HEIGHT):
    return _interp_by_depth(pixel_y, frame_height,
                             HIT_PROMINENCE_NEAR_PX, HIT_PROMINENCE_FAR_PX)


def get_player_proximity_margin(pixel_y, frame_height=config.FRAME_HEIGHT):
    return _interp_by_depth(pixel_y, frame_height,
                             PLAYER_PROXIMITY_MARGIN_NEAR_PX, PLAYER_PROXIMITY_MARGIN_FAR_PX)


def load_data(csv_path):
    df = pd.read_csv(csv_path)

    if df.empty:
        raise RuntimeError(
            f"{csv_path} is empty — no tracking data to analyze. "
            f"Check that detection/transform produced valid output upstream."
        )

    min_frame, max_frame = df["frame"].min(), df["frame"].max()
    full_index = pd.DataFrame({"frame": range(min_frame, max_frame + 1)})

    ball = df[df["type"] == "ball"].copy()
    ball = full_index.merge(ball, on="frame", how="left")
    ball = ball.sort_values("frame").reset_index(drop=True)

    player = df[df["type"] == "player"].copy().sort_values("frame").reset_index(drop=True)

    return ball, player


def _overhead_of_player(ball_df, player_df):
    """Boolean Series: ball detection sits in an on-court player's overhead
    contact zone (see USE_OVERHEAD_HITS) -- a serve toss or smash."""
    inside = pd.Series(False, index=ball_df.index)
    if player_df is None or len(player_df) == 0:
        return inside
    p = player_df
    if "table_x" in p.columns:
        p = p[p["table_x"].notna()]
    b = ball_df.loc[ball_df["pixel_x"].notna(), ["frame", "pixel_x", "pixel_y", "x1", "x2", "y1", "y2"]]
    b = b.rename(columns={"x1": "bx1", "x2": "bx2", "y1": "by1", "y2": "by2"}).reset_index()
    m = b.merge(p[["frame", "x1", "x2", "y1", "y2"]], on="frame")
    w, h = m["x2"] - m["x1"], m["y2"] - m["y1"]
    size = np.minimum(m["bx2"] - m["bx1"], m["by2"] - m["by1"])
    hit = ((m["pixel_x"] >= m["x1"] - OVERHEAD_SIDE_FRAC * w) & (m["pixel_x"] <= m["x2"] + OVERHEAD_SIDE_FRAC * w)
           & (m["pixel_y"] >= m["y1"] - OVERHEAD_ABOVE_FRAC * h) & (m["pixel_y"] <= m["y1"] + OVERHEAD_BELOW_FRAC * h)
           & (size >= OVERHEAD_MIN_BALL_TO_BOX * h))
    inside.loc[m.loc[hit, "index"].unique()] = True
    return inside


def _null_off_court_detections(ball_df, player_df=None):
    off_court = ball_df["pixel_x"].notna() & ball_df["table_x"].isna()
    if "proj_x" in ball_df.columns:
        # FIX 2026-09-27: table_x is nulled by transform.py whenever the
        # GROUND projection leaves court+OFF_TABLE_MARGIN -- but a ball in
        # the air always projects beyond its true position (past the far
        # baseline for a ball over the far court), so the old rule deleted
        # in-flight ball positions mid-trajectory. Only discard a point
        # that's wide of the sidelines or behind the near baseline, where
        # height can't explain it. See transform._project_unclipped.
        m = IN_PLAY_MARGIN_UNITS
        off_court = ball_df["pixel_x"].notna() & (
            ball_df["proj_x"].isna()
            | (ball_df["proj_x"] < -m)
            | (ball_df["proj_y"] < -m)
            | (ball_df["proj_y"] > TABLE_WIDTH_UNITS + m)
        )
        if USE_OVERHEAD_HITS:
            # A toss / overhead above an on-court player is far off the
            # ground, so its projection lands anywhere -- keep it.
            # The first frames after contact are still high (and already
            # outside the player's zone) -- they're the "after" half of the
            # hit's velocity fit, so keep a few frames either side too.
            over_frames = ball_df.loc[_overhead_of_player(ball_df, player_df), "frame"].to_numpy()
            if len(over_frames):
                d = np.abs(ball_df["frame"].to_numpy()[:, None] - over_frames[None, :]).min(axis=1)
                off_court &= ~pd.Series(d <= OVERHEAD_KEEP_FRAMES, index=ball_df.index)
    ball_df = ball_df.copy()
    ball_df.loc[off_court, ["pixel_x", "pixel_y"]] = np.nan
    return ball_df, int(off_court.sum())


def smooth_trajectory(ball_df, player_df=None):
    ball_df, n_nulled = _null_off_court_detections(ball_df, player_df)
    ball_df["has_position"] = ball_df["pixel_x"].notna()
    if n_nulled:
        print(f"  Nulled {n_nulled} off-court ball detections "
              f"(real pixel data, but transform.py flagged table_x/table_y as off-court)")
    return ball_df


def _reject_single_frame_outliers(x, y, threshold=OUTLIER_JUMP_THRESHOLD_PX):
    """Flags interior points that jump far from BOTH neighbors and snap
    back at the very next point -- a distinct failure mode from the
    existing off-court check (is_on_table()), which only catches points
    that land outside the court's own boundaries. A misdetection can land
    at a *plausible* on-court coordinate (see frame 4698: table_x=133.7,
    table_y=-30.9, both within OFF_TABLE_MARGIN) while still being wildly
    inconsistent with the ball's actual real motion on either side of it.

    Returns a boolean mask (True = reject this point) rather than
    mutating x/y directly, so the caller can null exactly those points
    and re-run the normal gap-interpolation over them -- treating a
    rejected single-frame outlier the same as any other short real gap,
    not a special case.
    """
    n = len(x)
    reject = np.zeros(n, dtype=bool)
    for i in range(1, n - 1):
        if pd.isna(x[i]) or pd.isna(x[i - 1]) or pd.isna(x[i + 1]):
            continue
        d_prev = np.hypot(x[i] - x[i - 1], y[i] - y[i - 1])
        d_next = np.hypot(x[i + 1] - x[i], y[i + 1] - y[i])
        d_skip = np.hypot(x[i + 1] - x[i - 1], y[i + 1] - y[i - 1])
        # Both hops touching this point are large jumps, but the neighbors
        # on either side of it are close to each other -- i.e. the real
        # trajectory barely moved across this frame, this one point is the
        # anomaly, not a genuine fast-motion stretch.
        if d_prev > threshold and d_next > threshold and d_skip < threshold:
            reject[i] = True
    return reject


def smooth_rally_window(ball_df, start_frame, end_frame,
                         window=SAVGOL_WINDOW, polyorder=SAVGOL_POLYORDER):
    window_df = ball_df[(ball_df["frame"] >= start_frame) & (ball_df["frame"] <= end_frame)]
    window_df = window_df.sort_values("frame").reset_index(drop=True)

    raw_x = window_df["pixel_x"].to_numpy()
    raw_y = window_df["pixel_y"].to_numpy()
    outlier_mask = _reject_single_frame_outliers(raw_x, raw_y)
    n_outliers = int(outlier_mask.sum())
    if n_outliers:
        window_df.loc[outlier_mask, ["pixel_x", "pixel_y"]] = np.nan
        print(f"  Rejected {n_outliers} single-frame ball-position outlier(s) in window "
              f"{start_frame}-{end_frame} (jump-and-snap-back pattern, not caught by off-court check)")

    window_df["pixel_x_interp"] = window_df["pixel_x"].interpolate(
        limit=config.INTERPOLATION_LIMIT, limit_area="inside"
    )
    window_df["pixel_y_interp"] = window_df["pixel_y"].interpolate(
        limit=config.INTERPOLATION_LIMIT, limit_area="inside"
    )

    window_df = window_df.dropna(subset=["pixel_x_interp", "pixel_y_interp"]).reset_index(drop=True)

    n = len(window_df)
    if n == 0:
        window_df["pixel_x_smooth"] = pd.Series(dtype=float)
        window_df["pixel_y_smooth"] = pd.Series(dtype=float)
        return window_df

    win = min(window, n if n % 2 == 1 else n - 1)
    if win < polyorder + 2:
        window_df["pixel_x_smooth"] = window_df["pixel_x_interp"]
        window_df["pixel_y_smooth"] = window_df["pixel_y_interp"]
    else:
        window_df["pixel_x_smooth"] = savgol_filter(
            window_df["pixel_x_interp"].values, win, polyorder
        )
        window_df["pixel_y_smooth"] = savgol_filter(
            window_df["pixel_y_interp"].values, win, polyorder
        )

    return window_df


def segment_rallies(ball_df, gap_threshold=RALLY_GAP_FRAMES,
                     min_length=MIN_RALLY_LENGTH_FRAMES):
    has_pos = ball_df["has_position"].values
    frames = ball_df["frame"].values

    rallies = []
    in_rally = False
    start_idx = None
    gap_count = 0

    for i, present in enumerate(has_pos):
        if present:
            if not in_rally:
                in_rally = True
                start_idx = i
            gap_count = 0
        else:
            if in_rally:
                gap_count += 1
                if gap_count >= gap_threshold:
                    end_idx = i - gap_count
                    if frames[end_idx] - frames[start_idx] + 1 >= min_length:
                        rallies.append((frames[start_idx], frames[end_idx]))
                    in_rally = False
                    gap_count = 0

    if in_rally:
        end_idx = len(has_pos) - 1 - gap_count
        if frames[end_idx] - frames[start_idx] + 1 >= min_length:
            rallies.append((frames[start_idx], frames[end_idx]))

    return rallies


def merge_nearby_coarse_rallies(coarse_rallies, merge_gap_threshold=EVENT_GAP_SPLIT_FRAMES):
    if not coarse_rallies:
        return coarse_rallies

    ordered = sorted(coarse_rallies, key=lambda r: r[0])
    merged = [list(ordered[0])]
    for start, end in ordered[1:]:
        if start - merged[-1][1] <= merge_gap_threshold:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    return [(s, e) for s, e in merged]


def _court_xy(row):
    """Court position for one ball row. Prefers transform.py's clipped
    table_x/y, but falls back to the unclipped projection (proj_x/y) --
    at a bounce the ball is ON the ground, so the projection is valid even
    when it lands well outside the court (the out calls this app needs)."""
    tx, ty = row["table_x"], row["table_y"]
    if pd.notna(tx) and pd.notna(ty):
        return tx, ty
    px, py = row.get("proj_x", np.nan), row.get("proj_y", np.nan)
    m = BOUNCE_POSITION_MAX_OFF_COURT_CM
    if pd.notna(px) and pd.notna(py) and -m <= px <= TABLE_LENGTH_UNITS + m             and -m <= py <= TABLE_WIDTH_UNITS + m:
        return px, py
    return np.nan, np.nan


def get_table_position(ball_df, frame, window=MAX_TABLE_LOOKUP_WINDOW):
    row = ball_df[ball_df["frame"] == frame]
    if len(row) == 0:
        return np.nan, np.nan, "unavailable", None

    tx, ty = _court_xy(row.iloc[0])
    if pd.notna(tx) and pd.notna(ty):
        return tx, ty, "measured", 0

    for offset in range(1, window + 1):
        for candidate_frame in (frame - offset, frame + offset):
            row = ball_df[ball_df["frame"] == candidate_frame]
            if len(row) == 0:
                continue
            tx, ty = _court_xy(row.iloc[0])
            if pd.notna(tx) and pd.notna(ty):
                return tx, ty, "nearby", offset

    return np.nan, np.nan, "unavailable", None


def is_on_table(table_x, table_y, tolerance=TABLE_EDGE_TOLERANCE_UNITS):
    if pd.isna(table_x) or pd.isna(table_y):
        return None
    y_lo, y_hi = config.rally_width_bounds()   # alleys count in doubles
    return (
        -tolerance <= table_x <= TABLE_LENGTH_UNITS + tolerance
        and y_lo - tolerance <= table_y <= y_hi + tolerance
    )


def detect_bounces(ball_df, start_frame, end_frame,
                    min_separation=BOUNCE_MIN_SEPARATION_FRAMES):
    rally = smooth_rally_window(ball_df, start_frame, end_frame)
    frames = rally["frame"].values
    py = rally["pixel_y_smooth"].values

    mid_prominence = get_bounce_prominence(np.nanmedian(py))
    peak_indices, properties = find_peaks(
        py, prominence=mid_prominence, distance=min_separation,
        wlen=BOUNCE_PROMINENCE_WLEN_FRAMES,
    )

    bounces = []
    for idx, prom in zip(peak_indices, properties["prominences"]):
        local_threshold = get_bounce_prominence(py[idx])
        if prom < local_threshold:
            continue

        frame = int(frames[idx])
        tx, ty, source, offset = get_table_position(ball_df, frame)
        on_table = is_on_table(tx, ty)
        bounces.append({
            "frame": frame,
            "table_x": tx,
            "table_y": ty,
            "pos_source": source,
            "pos_offset_frames": offset,
            "in_bounds": on_table,
        })

    return bounces


def find_unresolved_gaps(ball_df, start_frame, end_frame, min_gap=UNRESOLVED_GAP_MIN_FRAMES):
    window = ball_df[(ball_df["frame"] >= start_frame) & (ball_df["frame"] <= end_frame)]
    window = window.sort_values("frame")
    frames = window["frame"].values
    present = window["pixel_x"].notna().values

    gaps = []
    run_start = None
    for i, ok in enumerate(present):
        if not ok and run_start is None:
            run_start = i
        elif ok and run_start is not None:
            if run_start > 0 and (i - run_start) >= min_gap:
                gaps.append((int(frames[run_start - 1]), int(frames[i])))
            run_start = None

    return gaps


def estimate_gap_bounce(ball_df, pre_frame, post_frame, velocity_lookback=3):
    pre = ball_df[ball_df["frame"] <= pre_frame].dropna(subset=["pixel_y"]).tail(velocity_lookback)
    post = ball_df[ball_df["frame"] >= post_frame].dropna(subset=["pixel_y"]).head(velocity_lookback)

    gap_len = post_frame - pre_frame
    frac = 0.5
    likely_bounce = False

    if len(pre) >= 2 and len(post) >= 2:
        vy_pre = pre["pixel_y"].diff().mean()
        vy_post = post["pixel_y"].diff().mean()
        if pd.notna(vy_pre) and pd.notna(vy_post) and vy_pre > 0 and vy_post < 0:
            likely_bounce = True
            frac = abs(vy_pre) / (abs(vy_pre) + abs(vy_post))

    event_frame = int(round(pre_frame + gap_len * frac))
    tx, ty, source, offset = get_table_position(ball_df, post_frame)

    return {
        "frame": event_frame,
        "table_x": tx,
        "table_y": ty,
        "pos_source": "estimated_gap",
        "pos_offset_frames": offset,
        "in_bounds": is_on_table(tx, ty),
        "estimated": True,
        "gap_frames": gap_len,
        "likely_bounce": likely_bounce,
    }


def detect_hits(ball_df, player_df, start_frame, end_frame,
                 min_separation=HIT_MIN_SEPARATION_FRAMES):
    rally = smooth_rally_window(ball_df, start_frame, end_frame)
    frames = rally["frame"].values
    px = rally["pixel_x_smooth"].values
    py = rally["pixel_y_smooth"].values
    px_raw = rally["pixel_x_interp"].values
    py_raw = rally["pixel_y_interp"].values

    mid_prominence = get_hit_prominence(np.nanmedian(py))
    peak_indices, peak_props = find_peaks(
        px, prominence=mid_prominence, distance=min_separation,
        wlen=HIT_PROMINENCE_WLEN_FRAMES,
    )
    trough_indices, trough_props = find_peaks(
        -px, prominence=mid_prominence, distance=min_separation,
        wlen=HIT_PROMINENCE_WLEN_FRAMES,
    )

    candidates = list(zip(peak_indices, peak_props["prominences"])) + \
                 list(zip(trough_indices, trough_props["prominences"]))
    candidates.sort(key=lambda c: c[0])

    accepted_indices = []
    for idx, prom in candidates:
        local_threshold = get_hit_prominence(py[idx])
        if prom < local_threshold:
            continue
        if all(abs(frames[idx] - frames[a]) >= min_separation for a in accepted_indices):
            accepted_indices.append(idx)

    hits = []
    for idx in accepted_indices:
        frame = int(frames[idx])
        side = _attribute_player_side_windowed(player_df, frames, px_raw, py_raw, idx)
        tx, ty, source, offset = get_table_position(ball_df, frame)
        hits.append({
            "frame": frame,
            "player_side": side,
            "table_x": tx,
            "table_y": ty,
            "pos_source": source,
            "pos_offset_frames": offset,
        })

    return hits


def _attribute_player_side(player_df, frame, ball_px, ball_py, return_dist=False):
    margin = get_player_proximity_margin(ball_py)

    nearby = player_df[player_df["frame"] == frame]
    if len(nearby) == 0:
        nearby = player_df[(player_df["frame"] >= frame - 3) & (player_df["frame"] <= frame + 3)]
    if len(nearby) == 0:
        return ("unknown", np.inf) if return_dist else "unknown"

    nearby = nearby.copy()

    def bbox_distance(row):
        if pd.notna(row.get("x1")) and pd.notna(row.get("x2")):
            if row["x1"] <= ball_px <= row["x2"]:
                return 0.0
            return min(abs(ball_px - row["x1"]), abs(ball_px - row["x2"]))
        return abs(row["pixel_x"] - ball_px)

    nearby["dist"] = nearby.apply(bbox_distance, axis=1)
    best = nearby.loc[nearby["dist"].idxmin()]

    if best["dist"] > margin:
        return ("unknown", best["dist"]) if return_dist else "unknown"

    side = f"track_{int(best['track_id'])}"
    return (side, best["dist"]) if return_dist else side


def _attribute_player_side_windowed(player_df, rally_frames, px_raw, py_raw, idx,
                                     search_window=HIT_ATTRIBUTION_SEARCH_FRAMES):
    n = len(rally_frames)
    best = None
    for offset in range(-search_window, search_window + 1):
        i = idx + offset
        if i < 0 or i >= n:
            continue
        bx, by = px_raw[i], py_raw[i]
        if pd.isna(bx) or pd.isna(by):
            continue
        side, dist = _attribute_player_side(player_df, int(rally_frames[i]), bx, by, return_dist=True)
        if side == "unknown":
            continue
        key = (dist, abs(offset))
        if best is None or key < best[0]:
            best = (key, side)
    return best[1] if best else "unknown"


def _slope(t, v):
    t = t - t.mean()
    return float((t * (v - v.mean())).sum() / (t * t).sum())


def _nearest_player(player_df, frame, bx, by, search=3):
    """Track id of the player box closest to the ball (0 if inside it),
    within +/-search frames. The hit/bounce decision itself is made from
    ball motion (see HIT_DIRECTION_FRAMES), this only attributes it."""
    near = player_df[(player_df["frame"] >= frame - search) & (player_df["frame"] <= frame + search)]
    if "table_x" in near.columns and near["table_x"].notna().any():
        # People with a court position only -- spectators, a coach on the
        # bench or players on the next court project off-court (NaN).
        near = near[near["table_x"].notna()]
    best = None
    for r in near.itertuples():
        if pd.isna(r.track_id):
            continue
        dx = max(r.x1 - bx, 0, bx - r.x2)
        dy = max(r.y1 - by, 0, by - r.y2)
        key = (np.hypot(dx, dy), abs(r.frame - frame))
        if best is None or key < best[0]:
            best = (key, r.track_id)
    return "unknown" if best is None else f"track_{int(best[1])}"


def _kink_frame(F, X, Y, frame):
    """Bounce frame = where the image velocity changes most, measured over a
    short baseline (nearest detections >= KINK_BASELINE_FRAMES either side)
    within +/-KINK_SEARCH_FRAMES. The impulse peak is smeared over its fit
    window, and "lowest image point" fails when the ball bounces TOWARD
    this camera: it keeps moving down the image after the bounce, only much
    slower (2026-09-29: a serve bouncing at 10565 was placed at 10562, 4 m
    up the court -- in the box instead of long). Long straight-line fits
    don't work either: gravity + perspective curve every flight segment."""
    best, best_dv = frame, -1.0
    for c in np.where((F >= frame - KINK_SEARCH_FRAMES) & (F <= frame + KINK_SEARCH_FRAMES))[0]:
        b = np.where(F <= F[c] - KINK_BASELINE_FRAMES)[0]
        a = np.where(F >= F[c] + KINK_BASELINE_FRAMES)[0]
        if len(b) == 0 or len(a) == 0:
            continue
        b, a = b[-1], a[0]
        if F[c] - F[b] > 2 * KINK_BASELINE_FRAMES or F[a] - F[c] > 2 * KINK_BASELINE_FRAMES:
            continue
        vb = np.array([X[c] - X[b], Y[c] - Y[b]]) / (F[c] - F[b])
        va = np.array([X[a] - X[c], Y[a] - Y[c]]) / (F[a] - F[c])
        dv = float(np.hypot(*(va - vb)))
        if dv > best_dv:
            best, best_dv = int(F[c]), dv
    return best


def detect_events_impulse(ball_df, player_df, start_frame, end_frame):
    """Hits and bounces as sudden velocity changes -- see the
    USE_IMPULSE_EVENTS note at the top of this file. Returns (hits, bounces)
    in the same dict shapes detect_hits()/detect_bounces() produce."""
    w = ball_df[(ball_df["frame"] >= start_frame) & (ball_df["frame"] <= end_frame)
                & ball_df["pixel_x"].notna()]
    # Real detections only: transform.py's gap interpolation is a straight
    # line, which would hide the very kink we're looking for.
    if "confidence" in w.columns and w["confidence"].notna().any():
        w = w[w["confidence"].notna()]
    w = w.sort_values("frame")
    if len(w) < 2 * IMPULSE_MIN_POINTS_PER_SIDE + 1:
        return [], []
    step = np.hypot(w["pixel_x"].diff(), w["pixel_y"].diff())
    w = w[~((w["frame"].diff() == 1) & (step < DUPLICATE_FRAME_PX))]

    F = w["frame"].to_numpy()
    X = w["pixel_x"].to_numpy(dtype=float)
    Y = w["pixel_y"].to_numpy(dtype=float)
    if {"x1", "x2", "y1", "y2"}.issubset(w.columns):
        S = np.minimum(w["x2"] - w["x1"], w["y2"] - w["y1"]).to_numpy(dtype=float)
    else:
        S = np.full(len(F), np.nan)
    if np.all(np.isnan(S)):
        S = np.full(len(F), 16.0)
    S = np.where(np.isnan(S), np.nanmedian(S), S)

    def side_ok(m):
        f = F[m]
        return (len(f) >= IMPULSE_MIN_POINTS_PER_SIDE + 1
                and np.diff(f).max(initial=0) <= IMPULSE_MAX_FIT_GAP_FRAMES)

    K = IMPULSE_FIT_FRAMES
    impulse = np.zeros(len(F))
    for i, f in enumerate(F):
        mb = (F >= f - K) & (F <= f)
        ma = (F >= f) & (F <= f + K)
        if not (side_ok(mb) and side_ok(ma)):
            continue
        dvx = _slope(F[ma], X[ma]) - _slope(F[mb], X[mb])
        dvy = _slope(F[ma], Y[ma]) - _slope(F[mb], Y[mb])
        size = np.median(S[(F >= f - 5) & (F <= f + 5)])
        impulse[i] = np.hypot(dvx, dvy) / max(size, 1.0)

    accepted = []
    for i in np.argsort(-impulse):
        if impulse[i] < IMPULSE_THRESHOLD:
            break
        if all(abs(F[i] - F[j]) >= IMPULSE_MIN_SEPARATION_FRAMES for j in accepted):
            accepted.append(i)

    def vy(m, size):
        if m.sum() < 2:
            return None
        return _slope(F[m], Y[m]) / size

    def overhead_player(frame, bx, by, size):
        """Track id of a player the ball is above (serve/smash contact), else None."""
        near = player_df[(player_df["frame"] >= frame - 2) & (player_df["frame"] <= frame + 2)]
        if "table_x" in near.columns:
            near = near[near["table_x"].notna()]
        for r in near.itertuples():
            if pd.isna(r.track_id):
                continue
            w, h = r.x2 - r.x1, r.y2 - r.y1
            if (r.x1 - OVERHEAD_SIDE_FRAC * w <= bx <= r.x2 + OVERHEAD_SIDE_FRAC * w
                    and r.y1 - OVERHEAD_ABOVE_FRAC * h <= by <= r.y1 + OVERHEAD_BELOW_FRAC * h
                    and size >= OVERHEAD_MIN_BALL_TO_BOX * h):
                return f"track_{int(r.track_id)}"
        return None

    def speed(m, size):
        if m.sum() < 2:
            return None
        return np.hypot(_slope(F[m], X[m]), _slope(F[m], Y[m])) / size

    H = HIT_DIRECTION_FRAMES
    hits, bounces = [], []
    for i in sorted(accepted):
        frame = int(F[i])
        # Which half the ball is over (unclipped ground projection; a ball
        # in the air projects slightly long, never across the whole court).
        # None = unknown -> either rule may apply.
        # Uses the ball's CLOSEST projected point within a few frames: with a
        # missed detection at contact the impulse peak can land 3-4 frames
        # late, when a near-player shot is already high in the air and
        # projects past the net.
        side = None
        if "proj_x" in ball_df.columns:
            px = ball_df.loc[(ball_df["frame"] >= frame - 4) & (ball_df["frame"] <= frame + 4),
                             "proj_x"].dropna()
            if len(px):
                side = "near" if px.min() < config.NET_POSITION_OFFSET else "far"
        if side == "near":
            # Near-half bounce or hit: contact is the ball's lowest point in
            # the image (closest to the camera) -- snap to it, which also
            # undoes the late impulse peak described above.
            m = np.where((F >= frame - EVENT_SNAP_FRAMES) & (F <= frame + EVENT_SNAP_FRAMES))[0]
            frame = int(F[m[np.argmax(Y[m])]])
        size = max(np.median(S[(F >= frame - 5) & (F <= frame + 5)]), 1.0)
        vy_before = vy((F >= frame - H) & (F < frame), size)
        vy_after = vy((F > frame) & (F <= frame + H), size)
        is_hit = False
        overhead = None
        if USE_OVERHEAD_HITS:
            # contact is at or just before the impulse peak; speeds are
            # measured either side of the candidate contact frame itself
            for j in np.where((F >= frame - 3) & (F <= frame))[0][::-1]:
                fj = F[j]
                sp_b = speed((F >= fj - H) & (F <= fj), size)
                sp_a = speed((F > fj) & (F <= fj + H), size)
                if sp_a is None or sp_b is None:
                    continue
                vy_b = vy((F >= fj - H) & (F <= fj), size)
                vy_a = vy((F > fj) & (F <= fj + H), size)
                reversal = (OVERHEAD_REVERSAL and vy_b >= OVERHEAD_REVERSAL_MIN_VY
                            and vy_a <= -OVERHEAD_REVERSAL_MIN_VY)
                if not reversal and (sp_a < OVERHEAD_MIN_SPEED_AFTER
                                     or sp_a < OVERHEAD_MIN_SPEEDUP * max(sp_b, 0.1)):
                    continue
                overhead = overhead_player(int(fj), X[j], Y[j], S[j])
                if overhead is not None:
                    break
        if overhead is not None:
            is_hit = True                                       # serve / smash contact
        elif vy_after is not None:
            if vy_after <= NEAR_HIT_MAX_VY_AFTER and side != "far":
                is_hit = True                                   # sent away from the camera
            elif (vy_after >= FAR_HIT_MIN_VY_AFTER and side != "near"
                  and vy_before is not None and vy_before <= FAR_HIT_MAX_VY_BEFORE):
                is_hit = True                                   # sent back toward the camera
        if not is_hit and REFINE_BOUNCE_KINK:
            frame = _kink_frame(F, X, Y, frame)
        tx, ty, source, offset = get_table_position(ball_df, frame)
        base = {"frame": frame, "table_x": tx, "table_y": ty,
                "pos_source": source, "pos_offset_frames": offset,
                "impulse": round(float(impulse[i]), 2)}
        if is_hit:
            hits.append({**base, "player_side": overhead or _nearest_player(player_df, frame, X[i], Y[i])})
        else:
            bounces.append({**base, "in_bounds": is_on_table(tx, ty)})

    # Snapping can pull two peaks of the same physical event (e.g. either
    # side of a missed or duplicated frame) close together again -- keep
    # the stronger one.
    events = sorted([("hit", e) for e in hits] + [("bounce", e) for e in bounces],
                    key=lambda ke: -ke[1]["impulse"])
    kept = []
    for kind, e in events:
        if all(abs(e["frame"] - k["frame"]) >= IMPULSE_MIN_SEPARATION_FRAMES for _, k in kept):
            kept.append((kind, e))
    hits = sorted((e for k, e in kept if k == "hit"), key=lambda e: e["frame"])
    bounces = sorted((e for k, e in kept if k == "bounce"), key=lambda e: e["frame"])
    return hits, bounces


def detect_gap_hits(ball_df, player_df, existing_hits):
    """Far-player hits inferred from detection gaps -- see USE_GAP_HITS.
    Returns hit dicts (estimated=True, pos_source='estimated_gap_hit')."""
    if "proj_x" not in ball_df.columns:
        return []
    b = ball_df[ball_df["pixel_x"].notna()]
    if "confidence" in b.columns and b["confidence"].notna().any():
        b = b[b["confidence"].notna()]                 # real detections only
    b = b.sort_values("frame")
    F = b["frame"].to_numpy()
    Y = b["pixel_y"].to_numpy(dtype=float)
    X = b["pixel_x"].to_numpy(dtype=float)
    PX = b["proj_x"].to_numpy(dtype=float)
    hit_frames = [h["frame"] for h in existing_hits]

    def vy(idx):
        idx = [i for i in idx if 0 <= i < len(F)]
        if len(idx) < 3:
            return None
        return _slope(F[idx].astype(float), Y[idx])

    out = []
    for i in np.where(np.diff(F) > GAP_HIT_MIN_GAP)[0]:
        last, first = i, i + 1
        gap = F[first] - F[last]
        if gap > GAP_HIT_MAX_GAP:
            continue
        after = vy(range(first, first + 5))
        if after is None or after < GAP_HIT_MIN_VY_AFTER or not PX[first] > GAP_HIT_FAR_PROJ_X:
            continue
        if gap < GAP_HIT_NEW_POINT_GAP:               # mid-rally: ball was going away over the far half
            before = vy(range(last - 4, last + 1))
            if before is None or before > 5.0 or not PX[last] > config.NET_POSITION_OFFSET:
                continue
        # Must actually come back over the net. A ball falling toward a far
        # bounce also moves DOWN the image (vy > 0), but never reaches the
        # near half; the in-air projection runs long, so proj_x < net means
        # the ball really is on the near side.
        window = np.where((F >= F[first]) & (F <= F[first] + GAP_HIT_CROSS_WITHIN))[0]
        crossed = window[PX[window] < config.NET_POSITION_OFFSET]
        if len(crossed) == 0 and USE_NET_EVENTS:
            # ...or be stopped by it (a far-player shot into the net)
            netted = [k for k in window if _net_stall_at(F, X, Y, PX, F[k])]
            crossed = np.array(netted[:1], dtype=int)
        if len(crossed) == 0:
            continue
        # ...and travel toward the camera without a bounce first: a far-side
        # bounce shows as the ball rising (image y falling back) before it
        # crosses -- that return trip belongs to a LATER far hit, not this gap.
        path_y = Y[first:crossed[0] + 1]
        if len(path_y) and np.max(np.maximum.accumulate(path_y) - path_y) > GAP_HIT_MAX_RISE_PX:
            continue
        frame = int(max(F[last] + 1, F[first] - GAP_HIT_REAPPEAR_OFFSET))
        if any(abs(frame - h) <= GAP_HIT_DEDUPE_FRAMES for h in hit_frames):
            continue
        side = _nearest_player(player_df, F[first], X[first], Y[first], search=GAP_HIT_REAPPEAR_OFFSET)
        tx, ty, source, offset = get_table_position(ball_df, int(F[first]))
        out.append({"frame": frame, "player_side": side, "table_x": tx, "table_y": ty,
                    "pos_source": "estimated_gap_hit", "pos_offset_frames": int(F[first] - frame),
                    "estimated": True, "impulse": np.nan})
        hit_frames.append(frame)
    return out


def _real_ball_detections(ball_df):
    """Real (non-interpolated), de-duplicated ball detections."""
    b = ball_df[ball_df["pixel_x"].notna()]
    if "confidence" in b.columns and b["confidence"].notna().any():
        b = b[b["confidence"].notna()]
    b = b.sort_values("frame")
    step = np.hypot(b["pixel_x"].diff(), b["pixel_y"].diff())
    return b[~((b["frame"].diff() == 1) & (step < DUPLICATE_FRAME_PX))]


def _overhead_tracks(b, player_df):
    """[(frame, 'track_N')] for detections in b inside an on-court player's
    overhead zone (see USE_OVERHEAD_HITS)."""
    if player_df is None or len(player_df) == 0 or len(b) == 0:
        return []
    p = player_df
    if "table_x" in p.columns:
        p = p[p["table_x"].notna()]
    bb = b[["frame", "pixel_x", "pixel_y", "x1", "x2", "y1", "y2"]].rename(
        columns={"x1": "bx1", "x2": "bx2", "y1": "by1", "y2": "by2"})
    m = bb.merge(p[["frame", "track_id", "x1", "x2", "y1", "y2"]].dropna(subset=["track_id"]), on="frame")
    w, h = m["x2"] - m["x1"], m["y2"] - m["y1"]
    size = np.minimum(m["bx2"] - m["bx1"], m["by2"] - m["by1"])
    ok = ((m["pixel_x"] >= m["x1"] - OVERHEAD_SIDE_FRAC * w) & (m["pixel_x"] <= m["x2"] + OVERHEAD_SIDE_FRAC * w)
          & (m["pixel_y"] >= m["y1"] - OVERHEAD_ABOVE_FRAC * h) & (m["pixel_y"] <= m["y1"] + OVERHEAD_BELOW_FRAC * h)
          & (size >= OVERHEAD_MIN_BALL_TO_BOX * h))
    m = m[ok].drop_duplicates("frame").sort_values("frame")
    return [(int(f), f"track_{int(t)}") for f, t in zip(m["frame"], m["track_id"])]


def find_toss_ends(ball_df, player_df):
    """(frame, 'track_N') of the LAST detection of each run of detections in
    an on-court player's overhead zone: the top/fall of a serve toss (or an
    overhead) just before contact."""
    out, prev = [], None
    for f, trk in _overhead_tracks(_real_ball_detections(ball_df), player_df):
        if prev is not None and (f - prev[0] > 3 or trk != prev[1]):
            out.append(prev)
        prev = (f, trk)
    if prev is not None:
        out.append(prev)
    return out


def detect_toss_gap_hits(ball_df, tosses, existing_hits):
    """Serve contact hidden in a short detection gap right after the toss
    (the impulse fit needs points on both sides, so it can't see it): the
    ball reappears within OVERHEAD_KEEP_FRAMES moving much faster than the
    toss fell. Same speed rule as the impulse overhead check."""
    b = _real_ball_detections(ball_df)
    F = b["frame"].to_numpy()
    X = b["pixel_x"].to_numpy(dtype=float)
    Y = b["pixel_y"].to_numpy(dtype=float)
    S = np.minimum(b["x2"] - b["x1"], b["y2"] - b["y1"]).to_numpy(dtype=float)
    hit_frames = [h["frame"] for h in existing_hits]
    out = []
    for f, trk in tosses:
        if any(abs(f - h) <= IMPULSE_MIN_SEPARATION_FRAMES for h in hit_frames):
            continue
        nxt = np.where((F > f) & (F <= f + OVERHEAD_KEEP_FRAMES))[0]
        if len(nxt) == 0:
            continue
        k = nxt[0]
        mb = (F >= f - HIT_DIRECTION_FRAMES) & (F <= f)
        ma = (F >= F[k]) & (F <= F[k] + HIT_DIRECTION_FRAMES)
        if mb.sum() < 2 or ma.sum() < 2:
            continue
        size = max(np.nanmedian(S[mb | ma]), 1.0)
        sp_b = np.hypot(_slope(F[mb], X[mb]), _slope(F[mb], Y[mb])) / size
        sp_a = np.hypot(_slope(F[ma], X[ma]), _slope(F[ma], Y[ma])) / size
        if sp_a < OVERHEAD_MIN_SPEED_AFTER or sp_a < OVERHEAD_MIN_SPEEDUP * max(sp_b, 0.1):
            continue
        tx, ty, source, offset = get_table_position(ball_df, int(f))
        out.append({"frame": int(f) + 1, "player_side": trk, "table_x": tx, "table_y": ty,
                    "pos_source": "estimated_toss_gap_hit", "pos_offset_frames": -1,
                    "estimated": True, "impulse": np.nan})
        hit_frames.append(int(f) + 1)
    return out


def _net_stall_at(F, X, Y, PX, f):
    """True if the ball (real detections F/X/Y/PX) runs into the net band
    and stalls starting at frame f -- see USE_NET_EVENTS."""
    pre = np.where((F >= f - 6) & (F < f))[0]
    if len(pre) < 2:
        return False
    pre_speed = np.hypot(X[pre[-1]] - X[pre[0]], Y[pre[-1]] - Y[pre[0]]) / max(F[pre[-1]] - F[pre[0]], 1)
    if pre_speed < NET_STALL_MIN_SPEED_BEFORE:
        return False
    # Arrival: across the image (near hitter's ball) or down it (far
    # hitter's ball, coming toward the camera). A dead ball bouncing in
    # place arrives UP the image, rising off its bounce.
    approach = np.where((F >= f - 10) & (F <= f))[0]
    dx = abs(X[approach[-1]] - X[approach[0]])
    dy = Y[approach[-1]] - Y[approach[0]]
    if dx < NET_STALL_MIN_APPROACH_PX and dy < NET_STALL_MIN_APPROACH_PX:
        return False
    post = np.where((F >= f) & (F <= f + NET_STALL_WINDOW))[0]
    if len(post) < NET_STALL_MIN_POINTS:
        return False
    if np.ptp(X[post]) > NET_STALL_MAX_X_RANGE_PX or np.ptp(Y[post]) > NET_STALL_MAX_Y_RANGE_PX:
        return False
    if Y[post[-1]] - Y[post[0]] < -NET_STALL_MAX_RISE_PX:
        return False                                   # rising: a dead ball bouncing up, not netted
    pxs = PX[post][~np.isnan(PX[post])]
    net = config.NET_POSITION_OFFSET
    return len(pxs) > 0 and net + NET_STALL_PROJ_MIN <= np.median(pxs) <= net + NET_STALL_PROJ_MAX


def detect_net_events(ball_df, hits, bounces=(), tosses=()):
    """Ball stopped by the net -- see USE_NET_EVENTS. Returns (net events,
    inferred serve hits). A stall counts only within NET_STALL_MAX_AFTER_HIT
    frames of a hit -- or of a serve toss when the serve itself went unseen
    (a serve away from the camera looks slow in the image); the serve hit is
    then inferred at the end of the toss -- and with no bounce in between:
    a ball already bounced is dead or in play, not netted (it's the
    post-point dribble)."""
    if "proj_x" not in ball_df.columns or not (hits or tosses):
        return [], []
    b = ball_df[ball_df["pixel_x"].notna()]
    if "confidence" in b.columns and b["confidence"].notna().any():
        b = b[b["confidence"].notna()]                 # real detections only
    b = b.sort_values("frame")
    step = np.hypot(b["pixel_x"].diff(), b["pixel_y"].diff())
    b = b[~((b["frame"].diff() == 1) & (step < DUPLICATE_FRAME_PX))]
    F = b["frame"].to_numpy()
    X = b["pixel_x"].to_numpy(dtype=float)
    Y = b["pixel_y"].to_numpy(dtype=float)
    PX = b["proj_x"].to_numpy(dtype=float)
    hit_frames = np.array(sorted(h["frame"] for h in hits))
    hit_set = set(hit_frames.tolist())
    toss_frames = dict(tosses)
    anchors = np.array(sorted(hit_set | set(toss_frames)))
    bounce_frames = [b["frame"] for b in bounces if b.get("in_bounds") == True]  # noqa: E712 (numpy bools)
    net = config.NET_POSITION_OFFSET

    out, inferred, last_net = [], [], -10**9
    for k in range(1, len(F)):
        f = F[k]
        if f - last_net < 2 * NET_STALL_WINDOW:
            continue
        prior = anchors[anchors < f]
        if len(prior) == 0 or f - prior[-1] > NET_STALL_MAX_AFTER_HIT:
            continue
        if any(prior[-1] < bf < f - NET_IMPACT_FRAMES for bf in bounce_frames):
            continue
        if not _net_stall_at(F, X, Y, PX, f):
            continue
        out.append({"frame": int(f), "table_x": net, "table_y": np.nan,
                    "pos_source": "net_stall", "pos_offset_frames": 0,
                    "player_side": None, "in_bounds": False, "impulse": np.nan})
        a = int(prior[-1])
        # the serve may already be a hit a few frames after the toss end
        # (detect_toss_gap_hits); don't add it twice
        if a in toss_frames and not any(abs(a - h) <= IMPULSE_MIN_SEPARATION_FRAMES for h in hit_set):
            inferred.append({"frame": a + 1, "player_side": toss_frames[a], "table_x": np.nan,
                             "table_y": np.nan, "pos_source": "estimated_toss_net_hit",
                             "pos_offset_frames": -1, "estimated": True, "impulse": np.nan})
        last_net = f
    return out, inferred


def drop_pre_serve_events(ball_df, player_df, hits, bounces):
    """Between points the server bounces the ball at their feet; with the
    retrained model (which sees the ball near the far player) each bounce
    became a bounce/hit event. Drop a measured event when the ball is at an
    on-court player's feet, hasn't travelled from elsewhere in the last 30
    frames, and no hit happened in the last PRE_SERVE_NO_HIT_FRAMES (the
    ball is dead). Estimated hits are kept."""
    b = _real_ball_detections(ball_df)
    F = b["frame"].to_numpy()
    X = b["pixel_x"].to_numpy(dtype=float)
    Y = b["pixel_y"].to_numpy(dtype=float)
    p = player_df[player_df["table_x"].notna()] if "table_x" in player_df.columns else player_df
    hit_frames = np.array(sorted(h["frame"] for h in hits))

    def dead_ball_at_feet(e):
        if e.get("estimated") or len(F) == 0:
            return False
        f = e["frame"]
        earlier = hit_frames[(hit_frames < f) & (hit_frames >= f - PRE_SERVE_NO_HIT_FRAMES)]
        if len(earlier):
            return False
        j = int(np.argmin(np.abs(F - f)))
        if abs(F[j] - f) > 2:
            return False
        for r in p[p["frame"] == F[j]].itertuples():
            w, h = r.x2 - r.x1, r.y2 - r.y1
            if r.x1 - 0.5 * w <= X[j] <= r.x2 + 0.5 * w and r.y1 + 0.5 * h <= Y[j] <= r.y2 + 0.3 * h:
                pre = np.where((F >= f - 30) & (F < f))[0]
                travel = np.hypot(X[pre] - X[j], Y[pre] - Y[j]).max() / h if len(pre) else 0.0
                return travel < PRE_SERVE_MAX_TRAVEL
        return False

    kept_hits = [h for h in hits if not dead_ball_at_feet(h)]
    kept_bounces = [x for x in bounces if x.get("event_type") == "net" or not dead_ball_at_feet(x)]
    return kept_hits, kept_bounces, (len(hits) - len(kept_hits)) + (len(bounces) - len(kept_bounces))


def split_on_event_gap(hits, bounces, gap_threshold=EVENT_GAP_SPLIT_FRAMES):
    events = (
        [{"frame": h["frame"], "kind": "hit", "data": h} for h in hits]
        + [{"frame": b["frame"], "kind": "bounce", "data": b} for b in bounces]
    )
    events.sort(key=lambda e: e["frame"])

    sub_rallies = []
    current_hits, current_bounces = [], []
    prev_frame = None

    def flush_current():
        if current_hits or current_bounces:
            sub_rallies.append({"hits": list(current_hits), "bounces": list(current_bounces)})

    for event in events:
        if prev_frame is not None and (event["frame"] - prev_frame) > gap_threshold:
            flush_current()
            current_hits, current_bounces = [], []
        if event["kind"] == "hit":
            current_hits.append(event["data"])
        else:
            current_bounces.append(event["data"])
        prev_frame = event["frame"]

    flush_current()
    return sub_rallies


def run_analysis(csv_path, output_path="rally_events.csv",
                  min_sub_rally_length=MIN_RALLY_LENGTH_FRAMES):
    ball_df, player_df = load_data(csv_path)
    ball_df = smooth_trajectory(ball_df, player_df)

    coarse_rallies = segment_rallies(ball_df)
    n_before_merge = len(coarse_rallies)
    coarse_rallies = merge_nearby_coarse_rallies(coarse_rallies)
    print(f"Found {n_before_merge} coarse rally candidates (gap-based), "
          f"merged to {len(coarse_rallies)} after bridging <= {EVENT_GAP_SPLIT_FRAMES}-frame "
          f"gaps between them (see merge_nearby_coarse_rallies).")

    all_events = []
    rally_id = 0
    n_dead_ball_splits = 0
    n_estimated_bounces = 0
    n_unresolved_unclassified = 0
    n_hitless_rallies_kept = 0

    if USE_IMPULSE_EVENTS:
        # Detected once over the whole clip, then assigned to rallies:
        # running per rally window cuts off the "before" velocity fit for
        # any event near a window's start (e.g. a serve bounce right after
        # the ball reappears).
        all_hits, all_bounces = detect_events_impulse(
            ball_df, player_df, int(ball_df["frame"].min()), int(ball_df["frame"].max()))
        n_gap_hits = 0
        if USE_GAP_HITS:
            gap_hits = detect_gap_hits(ball_df, player_df, all_hits)
            n_gap_hits = len(gap_hits)
            all_hits = sorted(all_hits + gap_hits, key=lambda h: h["frame"])
        print(f"Impulse events: {len(all_hits) - n_gap_hits} hits, {len(all_bounces)} bounces; "
              f"+{n_gap_hits} far-player hits inferred from detection gaps")
        if PRE_SERVE_FILTER:
            all_hits, all_bounces, n_pre = drop_pre_serve_events(ball_df, player_df, all_hits, all_bounces)
            print(f"Pre-serve ball bouncing: {n_pre} event(s) dropped")
        tosses = find_toss_ends(ball_df, player_df) if USE_OVERHEAD_HITS else []
        if tosses:
            toss_hits = detect_toss_gap_hits(ball_df, tosses, all_hits)
            all_hits = sorted(all_hits + toss_hits, key=lambda h: h["frame"])
            # the contact itself may have been read as a bounce
            all_bounces = [b for b in all_bounces
                           if not any(abs(b["frame"] - h["frame"]) <= IMPULSE_MIN_SEPARATION_FRAMES
                                      for h in toss_hits)]
            print(f"Serve tosses: {len(tosses)}; +{len(toss_hits)} serve hits hidden in a detection gap")
        if USE_NET_EVENTS:
            net_events, toss_net_hits = detect_net_events(ball_df, all_hits, all_bounces, tosses)
            all_hits = sorted(all_hits + toss_net_hits, key=lambda h: h["frame"])
            # The impact into the net and the dribble after it read as
            # bounces; the net event replaces them.
            n_before = len(all_bounces)
            all_bounces = [b for b in all_bounces
                           if not any(n["frame"] - NET_IMPACT_FRAMES <= b["frame"] <= n["frame"] + 2 * NET_STALL_WINDOW
                                      for n in net_events)]
            all_bounces = sorted(all_bounces + [{**n, "event_type": "net"} for n in net_events],
                                 key=lambda b: b["frame"])
            # The same impact can read as a hit (the ball drops off the tape
            # and kicks up off the court): that "hit" then took the netted
            # shot (2026-10-21, frame 15439 on the unlabeled part of the
            # clip). Nobody strikes a ball that is already at the net.
            all_hits = [h for h in all_hits
                        if h.get("estimated") or not any(
                            n["frame"] - NET_IMPACT_FRAMES <= h["frame"] < n["frame"]
                            and abs(h["table_x"] - config.NET_POSITION_OFFSET) <= NET_IMPACT_MAX_DIST_CM
                            for n in net_events)]
            print(f"Net events: {len(net_events)} (ball stopped by the net; {len(toss_net_hits)} "
                  f"with the serve inferred from the toss); "
                  f"{n_before - (len(all_bounces) - len(net_events))} bounce(s) inside them dropped")

    for start, end in coarse_rallies:
        if USE_IMPULSE_EVENTS:
            # a far serve is inferred ~13 frames BEFORE the ball first reappears
            hits = [h for h in all_hits if start - GAP_HIT_REAPPEAR_OFFSET <= h["frame"] <= end]
            bounces = [b for b in all_bounces if start <= b["frame"] <= end]
        else:
            bounces = detect_bounces(ball_df, start, end)
            hits = detect_hits(ball_df, player_df, start, end)

        for pre_f, post_f in find_unresolved_gaps(ball_df, start, end):
            already_covered = (
                any(pre_f <= b["frame"] <= post_f for b in bounces)
                or any(pre_f <= h["frame"] <= post_f for h in hits)
            )
            if already_covered:
                continue
            gap_event = estimate_gap_bounce(ball_df, pre_f, post_f)
            if gap_event["likely_bounce"]:
                bounces.append(gap_event)
                n_estimated_bounces += 1
            else:
                n_unresolved_unclassified += 1

        sub_rallies = split_on_event_gap(hits, bounces)
        if len(sub_rallies) > 1:
            n_dead_ball_splits += len(sub_rallies) - 1
        # A net event ends the point: anything after it (dribble, pick-up,
        # ball fed back) starts a new sub-rally.
        split_subs = []
        for sub in sub_rallies:
            nets = sorted(b["frame"] for b in sub["bounces"] if b.get("event_type") == "net")
            for cut in nets:
                split_subs.append({"hits": [h for h in sub["hits"] if h["frame"] < cut],
                                   "bounces": [b for b in sub["bounces"] if b["frame"] <= cut]})
                sub = {"hits": [h for h in sub["hits"] if h["frame"] >= cut],
                       "bounces": [b for b in sub["bounces"] if b["frame"] > cut]}
            if sub["hits"] or sub["bounces"]:
                split_subs.append(sub)
        sub_rallies = split_subs

        for sub in sub_rallies:
            sub_events = (
                [{"frame": h["frame"], "event_type": "hit", **h} for h in sub["hits"]]
                + [{"frame": b["frame"], "event_type": "bounce", "player_side": None, **b}
                   for b in sub["bounces"]]
            )
            if not sub_events:
                continue
            sub_events.sort(key=lambda e: e["frame"])

            frames_seen = set()
            deduped_events = []
            for e in sub_events:
                if e["frame"] in frames_seen:
                    prior = next(x for x in deduped_events if x["frame"] == e["frame"])
                    if prior["event_type"] == "bounce" and e["event_type"] == "hit":
                        deduped_events.remove(prior)
                        deduped_events.append(e)
                    continue
                frames_seen.add(e["frame"])
                deduped_events.append(e)
            sub_events = sorted(deduped_events, key=lambda e: e["frame"])

            has_hit = any(e["event_type"] == "hit" for e in sub_events)
            if not has_hit:
                n_hitless_rallies_kept += 1

            sub_start = sub_events[0]["frame"]
            sub_end = sub_events[-1]["frame"]
            # A serve straight into the net is a whole point in < 0.5 s.
            ends_in_net = has_hit and sub_events[-1]["event_type"] == "net"
            if sub_end - sub_start + 1 < min_sub_rally_length and not ends_in_net:
                continue

            rally_id += 1
            for e in sub_events:
                all_events.append({
                    "rally_id": rally_id,
                    "rally_start_frame": sub_start,
                    "rally_end_frame": sub_end,
                    "has_hit": has_hit,
                    "event_type": e["event_type"],
                    "frame": e["frame"],
                    "player_side": e["player_side"],
                    "table_x": e["table_x"],
                    "table_y": e["table_y"],
                    "pos_source": e["pos_source"],
                    "pos_offset_frames": e["pos_offset_frames"],
                    "in_bounds": e.get("in_bounds"),
                    "estimated": e.get("estimated", False),
                })

    events_df = pd.DataFrame(all_events)
    if len(events_df) > 0:
        events_df = events_df.sort_values(["rally_id", "frame"]).reset_index(drop=True)

    events_df.to_csv(output_path, index=False)
    print(f"Event-gap splitting (>{EVENT_GAP_SPLIT_FRAMES} frames between consecutive "
          f"hit/bounce events) added {n_dead_ball_splits} extra rally boundaries.")
    print(f"Unresolved flight gaps: {n_estimated_bounces} estimated bounce(s) added, "
          f"{n_unresolved_unclassified} gap(s) flagged but not classified as a bounce.")
    print(f"Sub-rallies kept with zero detected hits (bounce-only): {n_hitless_rallies_kept} "
          f"-- previously these were silently discarded entirely.")
    print(f"Wrote {len(events_df)} events across {rally_id} final rallies to {output_path}")

    rallies = [
        (g["rally_start_frame"].iloc[0], g["rally_end_frame"].iloc[0])
        for _, g in events_df.groupby("rally_id")
    ] if len(events_df) > 0 else []

    return events_df, rallies


def validation_summary(events_df, rallies):
    print(f"\n--- Validation summary ---")
    print(f"Total rallies: {len(rallies)}")
    if len(events_df) == 0:
        print("No events detected.")
        return

    for rally_id, group in events_df.groupby("rally_id"):
        n_hits = (group["event_type"] == "hit").sum()
        n_bounces = (group["event_type"] == "bounce").sum()
        n_estimated = group["estimated"].sum() if "estimated" in group.columns else 0
        est_note = f", {n_estimated} estimated" if n_estimated else ""
        hit_note = "" if n_hits else " [BOUNCE-ONLY, no hit detected]"
        print(f"  Rally {rally_id}: frames {group['rally_start_frame'].iloc[0]}"
              f"-{group['rally_end_frame'].iloc[0]}, {n_hits} hits, {n_bounces} bounces{est_note}{hit_note}")

    source_counts = events_df["pos_source"].value_counts()
    print(f"\nPosition source breakdown across all events:\n{source_counts}")


if __name__ == "__main__":
    events_df, rallies = run_analysis(config.MATCH_CSV, config.EVENTS_CSV)
    validation_summary(events_df, rallies)
