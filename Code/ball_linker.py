"""
ball_linker.py -- turns raw per-frame ball detections into one ball
position per frame, replacing ByteTrack + stitch_track_fragments + the
windowed-displacement filter for the BALL (players still use ByteTrack).

WHY (2026-09-27 ground-truth investigation, job 76a383379d90):
ByteTrack associates detections by box overlap (IOU) on a Kalman
prediction. That's built for pedestrians, not a ~16px tennis ball moving
50-120px per frame. On real footage the ball model found the ball at
conf 0.7-0.85 in nearly every frame of a rally (e.g. frames 1220-1253),
but ByteTrack output it only as isolated single-point "tracks" ~5 frames
apart, which the stitcher (220px cap) and displacement filter (a single
point has 0 displacement) then threw away. Two things break IOU matching:
  1. The ball moves several box-widths per frame -> IOU is exactly 0 even
     after BALL_TRACK_BOX_PAD_PX padding.
  2. This footage repeats every 5th frame (25->30fps conversion), so the
     ball "stops" for one frame and a constant-velocity prediction
     overshoots by a full frame of motion.

This linker matches on DISTANCE to a velocity prediction instead of box
overlap, treats an exact repeat of the last position as a duplicate frame,
and allows a sharp direction change (hit/bounce) when nothing sits near
the prediction. Static clutter (stray balls on the ground, court-line
artifacts) is removed before linking, and slow tracks (a stray ball
rolling at ~2px/frame) are rejected after linking.

Pure numpy/pandas -- no GPU/ultralytics dependency, so it can be tuned
offline against a dump of raw detections.
"""

import numpy as np
import pandas as pd

import config


def _remove_static_clutter(df, window, radius, min_hits):
    """Flags candidates that reappear at (nearly) the same pixel in many
    nearby frames. A real ball is only ever at the same spot on a duplicated
    frame (1 repeat) or near a lob apex (a few); a ball lying on the court,
    or a line artifact, is there almost every frame."""
    frames = df["frame"].to_numpy()
    xs = df["pixel_x"].to_numpy()
    ys = df["pixel_y"].to_numpy()
    order = np.argsort(frames, kind="stable")
    frames, xs, ys = frames[order], xs[order], ys[order]
    static = np.zeros(len(df), dtype=bool)
    lo = hi = 0
    for i in range(len(frames)):
        while frames[lo] < frames[i] - window:
            lo += 1
        while hi + 1 < len(frames) and frames[hi + 1] <= frames[i] + window:
            hi += 1
        sl = slice(lo, hi + 1)
        near = (np.hypot(xs[sl] - xs[i], ys[sl] - ys[i]) <= radius) & (frames[sl] != frames[i])
        if len(np.unique(frames[sl][near])) >= min_hits:
            static[i] = True
    out = np.zeros(len(df), dtype=bool)
    out[order] = static
    return out


def _link(df, max_gap, dup_px, base_gate, speed_gate_frac, max_step_px):
    """Greedy online linking, frame by frame. Returns a track id per row."""
    track_of = np.full(len(df), -1, dtype=int)
    tracks = []  # dicts: last_f, x, y, vx, vy, n
    by_frame = {f: g for f, g in df.groupby("frame")}
    for f in sorted(by_frame):
        g = by_frame[f]
        idxs = g.index.to_numpy()
        cx = g["pixel_x"].to_numpy()
        cy = g["pixel_y"].to_numpy()
        pairs = []
        for ti, t in enumerate(tracks):
            dt = f - t["last_f"]
            if dt < 1 or dt > max_gap:
                continue
            speed = np.hypot(t["vx"], t["vy"])
            px, py = t["x"] + t["vx"] * dt, t["y"] + t["vy"] * dt
            d_pred = np.hypot(cx - px, cy - py)
            d_last = np.hypot(cx - t["x"], cy - t["y"])
            gate = base_gate + speed_gate_frac * speed * dt
            for k in range(len(idxs)):
                if dt == 1 and d_last[k] <= dup_px:
                    pairs.append((0.0, ti, k, True))            # duplicated frame
                elif t["n"] >= 2 and d_pred[k] <= gate:
                    pairs.append((d_pred[k], ti, k, False))     # follows the prediction
                elif t["n"] < 3 and d_last[k] <= max_step_px * dt:
                    # Off-prediction jump: only for a track too young to
                    # have a trustworthy velocity. An established track
                    # that can't follow its prediction ENDS instead (after
                    # a hit, the new direction starts its own track) --
                    # otherwise it zig-zags between two nearby balls.
                    pairs.append((gate + d_last[k], ti, k, False))
        pairs.sort(key=lambda p: (p[0], p[1]))
        used_t, used_c = set(), set()
        for cost, ti, k, dup in pairs:
            if ti in used_t or k in used_c:
                continue
            used_t.add(ti)
            used_c.add(k)
            t = tracks[ti]
            dt = f - t["last_f"]
            if not dup:
                t["vx"] = (cx[k] - t["x"]) / dt
                t["vy"] = (cy[k] - t["y"]) / dt
            t["x"], t["y"], t["last_f"] = cx[k], cy[k], f
            t["n"] += 1
            track_of[df.index.get_loc(idxs[k])] = ti
        for k in range(len(idxs)):
            if k in used_c:
                continue
            tracks.append({"last_f": f, "x": cx[k], "y": cy[k], "vx": 0.0, "vy": 0.0, "n": 1})
            track_of[df.index.get_loc(idxs[k])] = len(tracks) - 1
    return track_of


def link_ball_detections(
    candidates,
    total_frames,
    conf_min=config.BALL_LINK_CONF_MIN,
    static_window=config.BALL_LINK_STATIC_WINDOW,
    static_radius_px=config.BALL_LINK_STATIC_RADIUS_PX,
    static_min_hits=config.BALL_LINK_STATIC_MIN_HITS,
    max_gap=config.BALL_LINK_MAX_GAP_FRAMES,
    dup_px=config.BALL_LINK_DUPLICATE_PX,
    base_gate=config.BALL_LINK_BASE_GATE_PX,
    speed_gate_frac=config.BALL_LINK_SPEED_GATE_FRAC,
    max_step_px=config.BALL_LINK_MAX_STEP_PX,
    min_track_points=config.BALL_LINK_MIN_TRACK_POINTS,
    min_median_speed=config.BALL_LINK_MIN_MEDIAN_SPEED_PX,
    debug_dump_path=None,
):
    """
    candidates: list of dicts or DataFrame with frame, pixel_x, pixel_y,
    x1, y1, x2, y2, confidence (raw, untracked model output).
    Returns one dict per frame in range(total_frames), same shape as
    detection._select_active_ball_per_frame's rows.
    """
    df = pd.DataFrame(candidates)
    empty = [_empty_row(f) for f in range(total_frames)]
    if df.empty:
        return empty
    df = df[df["confidence"] >= conf_min].reset_index(drop=True)
    if df.empty:
        return empty

    df["static"] = _remove_static_clutter(df, static_window, static_radius_px, static_min_hits)
    moving = df[~df["static"]].copy()
    moving["track_id"] = _link(moving, max_gap, dup_px, base_gate, speed_gate_frac, max_step_px)

    # Score tracks: enough points and a real ball's speed. Duplicated
    # frames (zero-length steps) are excluded from the speed median.
    stats = {}
    for tid, g in moving.sort_values("frame").groupby("track_id"):
        steps = np.hypot(np.diff(g["pixel_x"]), np.diff(g["pixel_y"])) / np.diff(g["frame"])
        steps = steps[steps > dup_px]
        med = float(np.median(steps)) if len(steps) else 0.0
        stats[tid] = {"n": len(g), "median_speed": med,
                      # fastest stretch: best median over 5 consecutive moving steps
                      "fast": float(pd.Series(steps).rolling(5, min_periods=3).median().max())
                              if len(steps) >= 3 else 0.0,
                      "path": float(steps.sum()) if len(steps) else 0.0}

    # A struck ball has a fast stretch even if it then stalls in the net or
    # dies after a bounce (its median speed can fall below the gate: 2026-10-07,
    # a serve into the net at frame 4641 was dropped this way while a ball
    # rolling slowly across the court for 10 s was kept).
    def accept(t):
        st = stats[t]
        if st["n"] < min_track_points:
            return False
        return bool(st["median_speed"] >= min_median_speed) or bool(
            config.BALL_LINK_FAST_SEGMENT_PX and st["fast"] >= config.BALL_LINK_FAST_SEGMENT_PX)
    moving["accepted"] = moving["track_id"].map(accept)
    moving["track_fast_px"] = moving["track_id"].map(lambda t: stats[t]["fast"])
    moving["track_path_px"] = moving["track_id"].map(lambda t: stats[t]["path"])

    if debug_dump_path:
        dump = df.merge(moving[["track_id", "accepted", "track_path_px"]],
                        left_index=True, right_index=True, how="left")
        dump.to_csv(debug_dump_path, index=False)

    acc = moving[moving["accepted"]]
    rows = list(empty)
    # When two accepted tracks overlap in a frame, keep the one with the
    # longer total path (the rally ball), then higher confidence.
    if config.BALL_LINK_LOCAL_SLOW_PX:
        # Moving slowly RIGHT NOW (median step over the nearby frames of its
        # own track) loses to an overlapping track that is moving: at frame
        # 4641 a serve into the net lost to a ball that had been rolling
        # along the court for 10 s, because the roller's track (which also
        # held its earlier flight) was longer.
        acc = acc.sort_values(["track_id", "frame"]).copy()
        local = []
        for _, g in acc.groupby("track_id", sort=False):
            st = np.hypot(g["pixel_x"].diff(), g["pixel_y"].diff()) / g["frame"].diff()
            st = st.where(st > dup_px)
            w = config.BALL_LINK_LOCAL_WINDOW
            local.append(st.rolling(2 * w + 1, center=True, min_periods=2).median())
        acc["_slow"] = (pd.concat(local).reindex(acc.index) < config.BALL_LINK_LOCAL_SLOW_PX).fillna(False)
        acc = acc.sort_values(["frame", "_slow", "track_path_px", "confidence"],
                              ascending=[True, True, False, False])
    elif config.BALL_LINK_ROLLER_MAX_PX:
        # A stray ball rolling along the court never moves fast, however long
        # it is tracked: it loses to any track that does at some point.
        acc = acc.assign(_roller=acc["track_fast_px"] < config.BALL_LINK_ROLLER_MAX_PX)
        acc = acc.sort_values(["frame", "_roller", "track_path_px", "confidence"],
                              ascending=[True, True, False, False])
    elif config.BALL_LINK_PREFER_FAST:
        acc = acc.sort_values(["frame", "track_fast_px", "track_path_px", "confidence"],
                              ascending=[True, False, False, False])
    else:
        acc = acc.sort_values(["frame", "track_path_px", "confidence"], ascending=[True, False, False])
    for r in acc.drop_duplicates("frame").itertuples():
        if 0 <= r.frame < total_frames:
            rows[int(r.frame)] = {
                "frame": int(r.frame), "type": "ball", "track_id": int(r.track_id),
                "pixel_x": r.pixel_x, "pixel_y": r.pixel_y,
                "x1": r.x1, "y1": r.y1, "x2": r.x2, "y2": r.y2,
                "confidence": r.confidence,
            }
    n_acc = int(acc["frame"].nunique())
    print(f"  Ball linker: {len(df)} candidates >= conf {conf_min}, "
          f"{int(df['static'].sum())} static clutter removed, "
          f"{moving['track_id'].nunique()} tracks, "
          f"{sum(1 for s in stats.values() if s['n'] >= min_track_points and s['median_speed'] >= min_median_speed)} accepted, "
          f"ball found in {n_acc}/{total_frames} frames")
    return rows


def _empty_row(frame_num):
    return {
        "frame": frame_num, "type": "ball", "track_id": None,
        "pixel_x": None, "pixel_y": None,
        "x1": None, "y1": None, "x2": None, "y2": None,
        "confidence": None,
    }
