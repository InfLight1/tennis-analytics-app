"""
Runs ball detection (custom YOLOv8 model) and player detection + tracking
(pretrained YOLOv8n + ByteTrack) over a full video, writing raw per-frame
detections to CSV.

DAY 4 UPDATE (no footage yet, interface-only fix): the ball side previously
collapsed multiple ball candidates per frame down to a single
highest-confidence detection immediately at detection time, with no track
continuity. That contradicted the multi-ball design decision already
recorded in PROJECT.md ("label all balls as one class at detection stage;
reject near-zero-displacement tracks at the trajectory stage") -- with no
track for anything downstream to disambiguate, a stationary/stray ball
could win on confidence just as easily as the real in-play ball, especially
on partially-occluded or motion-blurred in-play frames.

Fixed by giving the ball its own ByteTrack instance (same approach already
used for players -- separate instance since ball motion characteristics
differ from player motion), keeping every candidate + its track_id, then
filtering out tracks whose centroid barely moves before collapsing to one
ball row per frame. This preserves the CSV's existing schema/shape exactly,
so nothing downstream (transform.py, analysis.py) needs to change.
Untested against a real multi-ball scene (no footage yet) -- validate once
the confirmed-angle footage includes stray balls, same as everything else
in this project currently marked ESTIMATED.

Also drops the old manual per-box class==0 filtering loop for the ball --
that was written for a possible multi-class ball model; the ball model is
now trained single_cls (see train_ball_detector.py), so sv.Detections can
be built directly from the YOLO result, same as the player side already does.

Run this standalone once calibration is done:
    python detection.py

--------------------------------------------------------------------------
DEPTH-ADAPTIVE BALL-TRACK FILTER (added this session)
--------------------------------------------------------------------------
Real-data check on job 76a383379d90 (14-min real point-play clip) found
accepted ball detections split 71% near-half / 29% far-half of on-table
frames (by table_x relative to the net) -- should be close to symmetric in
real singles play -- and that far-half survivors moved ~40% fewer
pixels/frame than near-half survivors (median 1.4px/frame vs 2.8px/frame,
consecutive-frame steps). This is the same perspective-compression failure
class already found and fixed for BOUNCE_PROMINENCE/HIT_PROMINENCE/
PLAYER_PROXIMITY_MARGIN in analysis.py and for player table_x via
transform.py's _foot_point() -- under this elevated, oblique,
behind-baseline camera, the same real-world motion produces much less
pixel-space displacement far from the camera than near it. A flat
BALL_TRACK_MIN_DISPLACEMENT_PX (and the stitching fragment-movement floor)
was very likely rejecting genuine far-court ball motion as "near-static,"
contributing to the ~3.4x-worse-than-benchmark ball-detection coverage
regression found via ground-truth comparison this session.

Fixed by porting analysis.py's exact _interp_by_depth pattern (continuous
linear interpolation on pixel_y/frame_height, not a binary near/far
branch) into this file, duplicated rather than imported so detection.py's
dependency surface doesn't change. BOTH BALL_TRACK_MIN_DISPLACEMENT_FAR_PX
and BALL_TRACK_STITCH_MIN_FRAGMENT_MOVEMENT_FAR_PX are marked ESTIMATED in
config.py -- re-derive them from a real post-stitch candidate dump (see
debug_dump_path below) before trusting far-court recall numbers, same as
every other ESTIMATED constant in this project.

Also added: run_detection() now reads the real frame height directly via
cv2 (frame_height, used for the depth-adaptive filter above) instead of
trusting config.FRAME_HEIGHT, which is a per-video value elsewhere in this
project (see the 2026-09-19 FRAME_HEIGHT incident) and was NOT previously
read at all anywhere in this file.

--------------------------------------------------------------------------
BALL-SPECIFIC TRACKER BOX PADDING (added this session; threshold-direction
mistake caught and corrected before shipping -- see below)
--------------------------------------------------------------------------
Root-caused job 76a383379d90's frame-298-386 dead zone (24 real
above-confidence-threshold candidates across 21 frames, only 2 surviving
into the tracked pool -- see TennisPerfApp.md's 2026-09-26 entry) one
level deeper: this is a ByteTrack matching failure, not a filter/threshold
issue in this file's own displacement logic. Measured IOU directly
between literally-CONSECUTIVE-frame real ball detections (confirmed same
physical ball, 1 frame apart) and found most pairs at 0.000-0.06 IOU,
several at EXACTLY 0.000 -- a ~15-18px ball box moving 15-25px/frame is
larger than its own box width, so it frequently has zero pixel overlap
with its own position one frame earlier.

FIRST ATTEMPT (wrong, caught before shipping): assumed
minimum_matching_threshold was a minimum-IOU floor and tried lowering it
from 0.8 to 0.2 for the ball tracker. Checked supervision's actual source
(tracker/byte_tracker/core.py) before trusting this: the threshold is
passed to `linear_assignment` against an IOU-DISTANCE cost (1 - IOU), so
a match is accepted when cost <= threshold, i.e. IOU >= (1 - threshold) --
a HIGHER value is MORE permissive, the opposite of what was assumed.
Confirmed empirically via a full frame-by-frame ByteTrack replay against
real diagnostic data: survival was flat across threshold=0.05-0.5 (all
functionally "require near-total overlap") and best at the ORIGINAL,
untouched 0.8. The threshold change was reverted entirely -- see
config.py's PLAYER_TRACKER_MATCHING_THRESHOLD/BALL_TRACKER_MATCHING_THRESHOLD,
both correctly left at 0.8.

THE ACTUAL FIX: ball boxes are padded by config.BALL_TRACK_BOX_PAD_PX
(each side) BEFORE being handed to ball_tracker for IOU association --
creates real overlap between real consecutive-frame ball positions that
otherwise have none, at the unchanged 0.8 threshold. The padded box is
used ONLY for tracker association; the true (unpadded) box is stashed via
sv.Detections' `data` field (confirmed to propagate through ByteTrack via
a direct test before relying on it) and recovered after tracking, so
raw_detection.csv's stored coordinates are exactly the same as before
this change.

Validated via the same full frame-by-frame replay (not just pairwise IOU,
which turned out to miss real tracker behavior like Kalman-predicted
position over gaps): survival into the tracked pool for the 298-386
window, threshold held at 0.8 throughout --
    pad=0 (baseline): 3/21 (14%) survive
    pad=20 (chosen):  11/21 (52%)
    pad=50:           15/21 (71%)
20px chosen over higher-recall options as the more conservative start --
see config.py's BALL_TRACK_BOX_PAD_PX docstring for the false-merge-risk
tradeoff and the still-open 36-frame true-absence gap (313-349) this fix
cannot address. Re-check ball_candidates_debug.csv from a fresh detection
run before trusting broadly -- specifically look for chains that jump
between spatially distant clusters (a signature already seen once before
in this project, the 2026-09-09 hit@225 false-merge investigation, though
that one was ruled out as a different mechanism).
--------------------------------------------------------------------------
BALL LINKER (2026-09-27) -- supersedes the ball ByteTrack/padding/stitch/
displacement-filter path above when config.USE_BALL_LINKER is True
--------------------------------------------------------------------------
Ground-truth diffing on job 76a383379d90 showed the ball model finds the
real ball at conf 0.7-0.85 in nearly every frame of a rally, but ByteTrack
still emitted it only as scattered single-point tracks (IOU can't follow a
ball moving several box-widths per frame; this footage also repeats every
5th frame). The ball now skips ByteTrack entirely: raw per-frame model
detections go to ball_linker.link_ball_detections(), which links on
distance-to-velocity-prediction. See ball_linker.py. The old path is kept,
unchanged, for USE_BALL_LINKER = False.

Ball inference size also now follows the video width (see
config.ball_inference_imgsz): the model was trained on 1920px frames at
imgsz 1280, so 4K footage at 1280 shows it a ball half the size it learned.
"""

import csv

import cv2
import numpy as np
import pandas as pd
import supervision as sv
from ultralytics import YOLO

import ball_linker
import config

import warnings
# supervision 0.29 flags sv.ByteTrack as deprecated (removal in 0.30/0.31); the
# Modal image pins supervision==0.29.1, so this is noise -- see TennisPerfApp.md §6.
warnings.filterwarnings("ignore", message=".*ByteTrack.*deprecated.*", category=FutureWarning)


def _interp_by_depth(pixel_y, frame_height, near_value, far_value):
    """Same formula as analysis.py's _interp_by_depth, duplicated here
    rather than imported so detection.py's dependency surface doesn't
    change. Works on a scalar or a numpy array of pixel_y. NaN pixel_y
    (shouldn't normally reach here, but kept for safety/symmetry with
    analysis.py's version) falls back to the midpoint of near/far."""
    arr = np.asarray(pixel_y, dtype=float)
    t = np.clip(arr / frame_height, 0.0, 1.0)
    result = far_value + t * (near_value - far_value)
    result = np.where(np.isnan(arr), (near_value + far_value) / 2, result)
    return float(result) if result.ndim == 0 else result


def get_ball_min_displacement(pixel_y, frame_height):
    return _interp_by_depth(
        pixel_y, frame_height,
        config.BALL_TRACK_MIN_DISPLACEMENT_NEAR_PX,
        config.BALL_TRACK_MIN_DISPLACEMENT_FAR_PX,
    )


def get_stitch_min_fragment_movement(pixel_y, frame_height):
    return _interp_by_depth(
        pixel_y, frame_height,
        config.BALL_TRACK_STITCH_MIN_FRAGMENT_MOVEMENT_NEAR_PX,
        config.BALL_TRACK_STITCH_MIN_FRAGMENT_MOVEMENT_FAR_PX,
    )


def fp16_kwargs(enabled):
    """FP16 inference kwargs for whichever ultralytics is installed: newer
    versions replaced `half=True` with `quantize=16` and log a deprecation
    WARNING on every single predict call otherwise (flooding job logs)."""
    if not enabled:
        return {}
    try:
        from ultralytics.cfg import DEFAULT_CFG_DICT
        if "quantize" in DEFAULT_CFG_DICT:
            return {"quantize": 16}
    except Exception:
        pass
    return {"half": True}


def _open_at_frame(video_path, cap, start_frame):
    """Position cap at start_frame. Seeks (<1 s) when the decoder confirms it
    landed exactly on start_frame; otherwise reopens and grab()s sequentially.

    Measured 2026-09-28 on job 76a383379d90: grab()-skipping cost the last
    chunk ~190 s of its 339 s on Modal (~100 fps over ~19.6k frames). A single
    seek per chunk was verified pixel-identical to sequential reading at all
    9 chunk starts (+0/+1/+2/+7/+30 frames, 45/45 frames). The 2026-09-09
    "don't trust seeking" finding came from per-frame seeks during fast
    motion in a diagnostic, a different access pattern.
    """
    if start_frame <= 0:
        return cap
    if config.DETECTION_CHUNK_SEEK:
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        if int(round(cap.get(cv2.CAP_PROP_POS_FRAMES))) == start_frame:
            return cap
        print(f"  seek to {start_frame} not confirmed by decoder -- falling back to sequential skip")
        cap.release()
        cap = cv2.VideoCapture(str(video_path))
    for _ in range(start_frame):
        if not cap.grab():
            break
    return cap


def detect_chunk(
    video_path,
    ball_model_path,
    player_model_path,
    start_frame,
    end_frame,
    player_track_id_offset=0,
    half=None,
):
    """
    Raw detection for frames [start_frame, end_frame) only -- one unit of
    chunked, parallel detection (modal_app.detect_chunk_remote). Returns
    (ball_candidates, player_rows) as lists of dicts; nothing is filtered.
    The ball linker runs ONCE over all chunks' candidates afterwards
    (detection_merge.merge_and_link), so chunk boundaries never cut a ball
    trajectory.

    Frames before start_frame are skipped with cap.grab() (sequential, no
    decode to BGR -- ~250 fps on 4K locally, and matches sequential reading
    exactly, unlike the per-frame cap.set() seeking this project stopped
    trusting on 2026-09-09).

    Player ByteTrack restarts at each chunk, so ids are offset by
    player_track_id_offset to stay unique across chunks. A rally that spans
    a boundary sees two ids per player; player_identity.py resolves players
    per rally by position, not id continuity, so this is tolerated.

    half: FP16 ball inference. Default = on when CUDA is available (measured
    2026-09-27: 1.4x faster at imgsz 2560, typed F1 within one event).
    """
    import torch
    if half is None:
        half = torch.cuda.is_available()

    ball_model = YOLO(str(ball_model_path))
    player_model = YOLO(str(player_model_path))
    player_tracker = sv.ByteTrack(
        track_activation_threshold=config.TRACKER_ACTIVATION_THRESHOLD,
        lost_track_buffer=config.PLAYER_TRACKER_LOST_BUFFER,
        minimum_matching_threshold=config.PLAYER_TRACKER_MATCHING_THRESHOLD,
        frame_rate=config.TRACKER_FRAME_RATE,
    )

    cap = cv2.VideoCapture(str(video_path))
    ball_imgsz = config.ball_inference_imgsz(int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)))
    precision = fp16_kwargs(half)
    cap = _open_at_frame(video_path, cap, start_frame)

    ball_candidates, player_rows = [], []
    frame_num = start_frame
    while frame_num < end_frame:
        ok, frame = cap.read()
        if not ok:
            break
        r = ball_model(frame, conf=config.BALL_LINK_CONF_MIN, imgsz=ball_imgsz,
                       verbose=False, **precision)[0]
        for (x1, y1, x2, y2), conf in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist()):
            ball_candidates.append({
                "frame": frame_num, "track_id": -1,
                "pixel_x": (x1 + x2) / 2, "pixel_y": (y1 + y2) / 2,
                "x1": x1, "y1": y1, "x2": x2, "y2": y2, "confidence": float(conf),
            })

        pr = player_model(frame, classes=[0], conf=config.PLAYER_CONF_THRESHOLD,
                          imgsz=config.INFERENCE_IMGSZ, verbose=False)[0]
        det = player_tracker.update_with_detections(sv.Detections.from_ultralytics(pr))
        for i, (x1, y1, x2, y2) in enumerate(det.xyxy.tolist()):
            tid = int(det.tracker_id[i]) + player_track_id_offset if det.tracker_id is not None else -1
            player_rows.append({
                "frame": frame_num, "type": "player", "track_id": tid,
                "pixel_x": (x1 + x2) / 2, "pixel_y": (y1 + y2) / 2,
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "confidence": float(det.confidence[i]),
            })
        frame_num += 1

    cap.release()
    print(f"Chunk {start_frame}-{end_frame}: {frame_num - start_frame} frames, "
          f"{len(ball_candidates)} ball candidates, {len(player_rows)} player rows "
          f"(imgsz {ball_imgsz}, half={half})")
    return ball_candidates, player_rows


def run_detection(
    video_path,
    ball_model_path,
    player_model_path,
    raw_csv_path,
    ball_conf=config.BALL_CONF_THRESHOLD,
    player_conf=config.PLAYER_CONF_THRESHOLD,
    imgsz=config.INFERENCE_IMGSZ,
    debug_dump_path=None,
):
    """
    Processes every frame of video_path, detecting the ball with
    ball_model_path (tracked with its own ByteTrack instance, then filtered
    down to one active-ball row per frame -- see module docstring) and
    tracking players with player_model_path + ByteTrack. Writes one row per
    frame per resolved object to raw_csv_path.

    Parameters
    ----------
    debug_dump_path : str, optional
        If given, every post-stitch ball candidate point (with pixel_y,
        chain_id, and -- as of 2026-09-27 -- its raw windowed_displacement_px,
        not just the threshold and pass/fail) is also written to this path
        BEFORE the displacement filter runs. Lets you replay/tune
        _select_active_ball_per_frame's filter entirely offline against
        real candidate data, without a full GPU rerun for every threshold
        you want to try -- same idea as diagnose_ball_candidates.py from
        the 2026-09-09 session.

    Returns
    -------
    int
        Total number of frames processed.
    """
    ball_model = YOLO(str(ball_model_path))
    player_model = YOLO(str(player_model_path))

    player_tracker = sv.ByteTrack(
        track_activation_threshold=config.TRACKER_ACTIVATION_THRESHOLD,
        lost_track_buffer=config.PLAYER_TRACKER_LOST_BUFFER,
        minimum_matching_threshold=config.PLAYER_TRACKER_MATCHING_THRESHOLD,
        frame_rate=config.TRACKER_FRAME_RATE,
    )
    # Separate instance from player_tracker -- same class (ByteTrack doesn't
    # care what it's tracking) but sharing state across ball and player
    # detections would be wrong regardless. Ball keeps its own, much
    # shorter, lost-buffer (see config.py). Its matching threshold is
    # currently the same 0.8 as the player tracker's -- kept as a separate
    # constant only for future independent tuning. NOTE the direction: in
    # supervision, minimum_matching_threshold is a max COST (1 - IOU), so
    # LOWER = STRICTER; do not lower it hoping to loosen matching (see
    # config.py). The ball's real association fix is the box padding
    # applied in the detection loop below (BALL_TRACK_BOX_PAD_PX).
    ball_tracker = sv.ByteTrack(
        track_activation_threshold=config.TRACKER_ACTIVATION_THRESHOLD,
        lost_track_buffer=config.BALL_TRACKER_LOST_BUFFER,
        minimum_matching_threshold=config.BALL_TRACKER_MATCHING_THRESHOLD,
        frame_rate=config.TRACKER_FRAME_RATE,
    )

    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    # NEW: read this job's real frame height directly, same as
    # modal_app.py already does for analysis.py's depth-adaptive
    # thresholds -- don't trust config.FRAME_HEIGHT here, it's a per-video
    # value elsewhere in this project (see the 2026-09-19 FRAME_HEIGHT
    # incident) and nothing in this file previously read it at all.
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if not frame_height:
        raise RuntimeError(f"Could not read frame height from {video_path}")
    frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_num = 0

    use_linker = config.USE_BALL_LINKER
    if use_linker:
        # The linker does its own static-clutter rejection, so it wants
        # everything down to its own floor, not the old 0.3 cut.
        ball_conf = min(ball_conf, config.BALL_LINK_CONF_MIN)
        ball_imgsz = config.ball_inference_imgsz(frame_width)
    else:
        ball_imgsz = imgsz
    import torch
    use_half = use_linker and torch.cuda.is_available()   # FP16: see detect_chunk()

    print(f"Processing {total} frames (~{total / fps / 60:.1f} min of footage)")
    print(f"Detected frame_height={frame_height}px (used for depth-adaptive ball filter)")
    print(f"Ball: {'linker' if use_linker else 'ByteTrack'}, conf>={ball_conf}, imgsz={ball_imgsz}")
    print(f"Saving to: {raw_csv_path}\n")

    # Ball candidates are buffered (not written directly) because
    # track-based filtering needs to see each track's whole lifespan before
    # deciding whether it's static -- can't decide that from a single
    # frame. Player rows have no such dependency and are still streamed
    # straight through.
    ball_candidates = []
    player_rows = []

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # ── Ball detection + tracking ───────────────────────────────────
        ball_results = ball_model(frame, conf=ball_conf, imgsz=ball_imgsz, verbose=False, **fp16_kwargs(use_half))[0]
        ball_detections = sv.Detections.from_ultralytics(ball_results)

        if use_linker:
            for (x1, y1, x2, y2), conf in zip(ball_detections.xyxy.tolist(),
                                              ball_detections.confidence.tolist()):
                ball_candidates.append({
                    "frame": frame_num, "track_id": -1,
                    "pixel_x": (x1 + x2) / 2, "pixel_y": (y1 + y2) / 2,
                    "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                    "confidence": float(conf),
                })
            ball_detections = ball_detections[:0]   # skip the ByteTrack path below

        # Stash the true (unpadded) box before padding for tracking -- see
        # config.BALL_TRACK_BOX_PAD_PX's docstring for why padding is
        # needed at all. Stored via .data, which supervision propagates
        # through ByteTrack alongside xyxy/confidence/tracker_id, so each
        # surviving detection keeps its real box regardless of anything
        # ByteTrack's Kalman filter does to the padded copy internally.
        orig_xyxy = ball_detections.xyxy.copy()
        ball_detections.data["orig_xyxy"] = orig_xyxy
        pad = config.BALL_TRACK_BOX_PAD_PX
        padded_xyxy = orig_xyxy.copy()
        if len(padded_xyxy):
            padded_xyxy[:, [0, 1]] -= pad
            padded_xyxy[:, [2, 3]] += pad
        ball_detections.xyxy = padded_xyxy

        if not use_linker:
            ball_detections = ball_tracker.update_with_detections(ball_detections)

        # Recover the true box for surviving detections. Prefer the
        # propagated orig_xyxy; fall back to un-padding the tracked box
        # (exact inverse of the padding above) if data didn't survive for
        # some reason -- logged once so a silent fallback is never silent.
        if "orig_xyxy" in ball_detections.data:
            true_xyxy = ball_detections.data["orig_xyxy"]
        else:
            if frame_num == 0:
                print("  WARNING: orig_xyxy did not propagate through "
                      "ball_tracker -- falling back to un-padding tracked "
                      "boxes directly. Verify this doesn't silently "
                      "distort stored ball coordinates (see BALL_TRACK_BOX_PAD_PX).")
            true_xyxy = ball_detections.xyxy.copy()
            if len(true_xyxy):
                true_xyxy[:, [0, 1]] += pad
                true_xyxy[:, [2, 3]] -= pad

        for i, box in enumerate(true_xyxy):
            x1, y1, x2, y2 = box.tolist()
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            tid = int(ball_detections.tracker_id[i]) if ball_detections.tracker_id is not None else -1
            conf = float(ball_detections.confidence[i])
            ball_candidates.append({
                "frame": frame_num, "track_id": tid,
                "pixel_x": cx, "pixel_y": cy,
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "confidence": conf,
            })

        # ── Player detection + tracking (unchanged) ─────────────────────
        player_results = player_model(frame, classes=[0], conf=player_conf, imgsz=imgsz, verbose=False)[0]
        player_detections = sv.Detections.from_ultralytics(player_results)
        player_detections = player_tracker.update_with_detections(player_detections)

        for i, box in enumerate(player_detections.xyxy):
            x1, y1, x2, y2 = box.tolist()
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            tid = int(player_detections.tracker_id[i]) if player_detections.tracker_id is not None else -1
            conf = float(player_detections.confidence[i])
            player_rows.append({
                "frame": frame_num, "type": "player", "track_id": tid,
                "pixel_x": cx, "pixel_y": cy,
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "confidence": conf,
            })

        frame_num += 1
        if frame_num % 500 == 0:
            pct = 100 * frame_num / total
            print(f"  [{frame_num}/{total}] {pct:.1f}% complete")

    cap.release()

    print(f"\nDone reading -- {frame_num} frames processed. Resolving ball tracks...")
    if use_linker:
        resolved_ball_rows = ball_linker.link_ball_detections(
            ball_candidates, frame_num, debug_dump_path=debug_dump_path
        )
    else:
        resolved_ball_rows = _select_active_ball_per_frame(
            ball_candidates, frame_num, frame_height, debug_dump_path=debug_dump_path
        )

    all_rows = resolved_ball_rows + player_rows
    all_rows.sort(key=lambda r: (r["frame"], r["type"]))

    with open(raw_csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "frame", "type", "track_id",
            "pixel_x", "pixel_y",
            "x1", "y1", "x2", "y2",
            "confidence",
        ])
        for r in all_rows:
            writer.writerow([
                r["frame"], r["type"], r["track_id"],
                r["pixel_x"], r["pixel_y"],
                r["x1"], r["y1"], r["x2"], r["y2"],
                r["confidence"],
            ])

    print(f"Saved to {raw_csv_path}")
    return frame_num


def _track_internal_displacement(g):
    """
    Net displacement across a single track's OWN lifespan (first row to
    last row). None for single-row tracks -- can't assess static-ness from
    one point, so those are left for the cross-track distance/gap check to
    handle on their own merits.

    Added 2026-09 after real-footage validation surfaced a genuine
    false-merge risk in stitch_track_fragments' greedy nearest-distance
    matching: a persistent near-static clutter track (e.g. a court-line
    artifact, present across many frames but jittering <2px) can sit
    CLOSER to a real ball fragment's endpoint than the real next fragment
    does, and the old distance-only matching would prefer the closer (but
    wrong) static track every time -- confirmed on real data (a genuine
    bounce-to-hit ball trajectory had its correct next fragment 103.8px
    away, while an unrelated static track sat only 32.8px away and would
    have won the match once gap/distance limits were loosened to bridge
    real high-speed post-bounce motion). A track's own internal
    displacement is a much stronger and correctly-separated static/real
    signal than distance-to-a-neighbor: real footage showed all clutter
    tracks under ~1.5px internal movement even over 25-40 frames, while
    already-confirmed-real fragments showed 9px+ even over just 2-4 frames.
    """
    if len(g) < 2:
        return None
    x0, y0 = g["pixel_x"].iloc[0], g["pixel_y"].iloc[0]
    x1, y1 = g["pixel_x"].iloc[-1], g["pixel_y"].iloc[-1]
    return float(np.hypot(x1 - x0, y1 - y0))


def stitch_track_fragments(
    df,
    frame_height,
    max_gap_frames=config.BALL_TRACK_STITCH_MAX_GAP_FRAMES,
    max_gap_dist=config.BALL_TRACK_STITCH_MAX_GAP_DIST_PX,
):
    """
    Bridges ByteTrack's short track_id fragmentation (confirmed via real
    footage: the ball visibly flickers -- briefly cut mid-air, re-detected
    a moment later, already lower) before the displacement filter runs.

    Compares each track's END point only to OTHER tracks' START points
    (union-find over track-level summaries) -- NOT individual candidate
    rows. This matters: real footage has 40-80+ concurrent stray-ball
    candidates in nearly every frame (see PROJECT.md on stray balls during
    practice), so a naive row-by-row walk sorted by frame gets hijacked by
    whichever unrelated static candidate happens to sort next, long before
    it reaches the real continuation -- validated and confirmed on real
    data during development. Matching at the track level means the
    long-lived static tracks (present almost every frame, so they never
    "end" mid-window) simply never compete for a bridge.

    Tracks whose OWN internal displacement (see _track_internal_displacement)
    is below that track's own depth-adjusted min_fragment_movement (see
    get_stitch_min_fragment_movement -- DEPTH-ADAPTIVE as of this session,
    was a single flat config value before) are excluded from both the
    source and target candidate pools entirely, regardless of how close
    they sit to a real fragment -- see that function's docstring for why
    distance alone isn't sufficient once gap/distance limits are loosened
    enough to bridge real high-speed post-bounce motion. Single-row tracks
    can't be assessed this way and are always eligible, same as before.

    For each track's end point, picks the nearest not-yet-claimed eligible
    track start within max_gap_frames/max_gap_dist (0 < gap required -- two
    candidates in the same frame are never the same object). Chosen greedy
    by processing tracks in end_frame order; each start can only be
    claimed once. Validated against real footage: correctly bridges a
    genuine 2-frame ball dropout without merging distinct concurrent stray
    balls (zero false merges across ~140 real tracks tested), and (2026-09,
    post-fragment-movement-filter) correctly bridges real post-bounce gaps
    up to 6 frames / ~210px without being hijacked by nearby static clutter.
    """
    summaries = []
    for tid, g in df.groupby("track_id"):
        g = g.sort_values("frame")
        internal_disp = _track_internal_displacement(g)
        # DEPTH-ADAPTIVE as of this session: each track's own mean pixel_y
        # picks its eligibility floor, instead of one flat value for every
        # track regardless of how far from the camera it sits.
        min_fragment_movement = get_stitch_min_fragment_movement(
            g["pixel_y"].mean(), frame_height
        )
        summaries.append({
            "track_id": tid,
            "start_frame": int(g["frame"].iloc[0]), "end_frame": int(g["frame"].iloc[-1]),
            "start_x": g["pixel_x"].iloc[0], "start_y": g["pixel_y"].iloc[0],
            "end_x": g["pixel_x"].iloc[-1], "end_y": g["pixel_y"].iloc[-1],
            # None (single-row) or >= min_fragment_movement -> eligible;
            # a confirmed-static multi-row track is not.
            "eligible": internal_disp is None or internal_disp >= min_fragment_movement,
        })

    parent = {s["track_id"]: s["track_id"] for s in summaries}

    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x

    by_start = sorted((s for s in summaries if s["eligible"]), key=lambda s: s["start_frame"])
    used_as_target = set()

    for src in sorted((s for s in summaries if s["eligible"]), key=lambda s: s["end_frame"]):
        best, best_dist = None, None
        for cand in by_start:
            if cand["track_id"] == src["track_id"] or cand["track_id"] in used_as_target:
                continue
            gap = cand["start_frame"] - src["end_frame"]
            if 0 < gap <= max_gap_frames:
                dist = np.hypot(cand["start_x"] - src["end_x"], cand["start_y"] - src["end_y"])
                if dist <= max_gap_dist and (best is None or dist < best_dist):
                    best, best_dist = cand, dist
        if best is not None:
            parent[find(best["track_id"])] = find(src["track_id"])
            used_as_target.add(best["track_id"])

    chain_map = {tid: find(tid) for tid in parent}
    df = df.copy()
    df["chain_id"] = df["track_id"].map(chain_map)
    return df


def _max_windowed_net_displacement(frames, xs, ys, window):
    """
    Two-pointer sliding window: for each point, finds the furthest-back
    point still within `window` frames and returns the largest net
    (straight-line, start-to-end) displacement seen across any such span.

    This is deliberately NOT the sum of consecutive frame-to-frame steps --
    that sum accumulates from pure detection jitter on a stationary object
    the longer a track survives, which is exactly what let static false
    positives (a track present for 100+ frames, moving by fractions of a
    pixel each frame) outscore real short-lived ball tracks in real
    footage. Net displacement within a bounded window can't accumulate that
    way -- a genuinely stationary object stays near 0 no matter how long
    the track lives.

    SUPERSEDED 2026-09-14 -- see _windowed_net_displacement_per_point below.
    Kept only for reference; no longer called. This function collapses an
    entire chain to ONE scalar (the max window seen anywhere in its whole
    life), which _select_active_ball_per_frame then used to accept/reject
    every frame of the chain as a single unit. Real-footage validation
    found a long-lived, genuinely near-static stray ball (track 928, ~3.5
    minutes) that was mostly motionless but had a handful of frames where
    its local windowed displacement briefly spiked (up to 187px, likely a
    small nudge/faster phase of a slow roll) -- enough to clear
    min_displacement ONCE, which under the old whole-chain logic
    whitelisted all 6342 of its frames as "the ball," masking real rally
    boundaries for the entire span it spanned. The fix scopes the
    accept/reject decision to each individual point instead of the chain
    as a whole.
    """
    max_disp = 0.0
    left = 0
    n = len(frames)
    for right in range(n):
        while frames[right] - frames[left] > window:
            left += 1
        dx = xs[right] - xs[left]
        dy = ys[right] - ys[left]
        disp = (dx ** 2 + dy ** 2) ** 0.5
        if disp > max_disp:
            max_disp = disp
    return max_disp


def _windowed_net_displacement_per_point(frames, xs, ys, window):
    """
    Local analogue of _max_windowed_net_displacement, scoped to each
    individual point instead of the whole chain. For each point i, returns
    the largest net (straight-line) displacement from point i to any OTHER
    point within `window` frames of it, looking both forward and backward
    (symmetric) -- i.e. "is THIS specific frame part of a real local
    motion burst," not "did this chain ever move at some point in its
    life."

    FIX (2026-09-14, real-footage finding): the old whole-chain version
    let a single brief motion burst anywhere in a long-lived chain
    whitelist every frame of that chain as active. Confirmed on real data:
    track 928, a genuine but out-of-play stray ball, was motionless for
    ~97.6% of its 6342-frame, ~3.5-minute life, with a handful of frames
    where local displacement briefly spiked past the 15px threshold
    (likely a small nudge or a faster phase of a slow roll) -- enough to
    mark the ENTIRE chain active under the old logic, which silently
    swallowed real between-rally gaps for the whole span and prevented
    analysis.py's segment_rallies() from ever splitting there.

    Scoping the decision to each point means only frames actually near a
    real motion burst get accepted; long static stretches elsewhere in the
    same track_id/chain are correctly rejected even though ByteTrack kept
    them under one continuous ID. Real, genuinely-moving ball fragments
    (short-lived, consistently fast for their whole life -- see
    _track_internal_displacement's own real-data numbers) are unaffected:
    essentially every point in a real fragment already has fast neighbors
    on both sides within any reasonable window, so this only removes
    frames that were never near real motion to begin with.

    O(n): frames is sorted (guaranteed by caller), so both the trailing
    and leading window edges advance monotonically as i increases.
    """
    n = len(frames)
    result = np.zeros(n, dtype=float)
    left = 0
    right = 0
    for i in range(n):
        while frames[i] - frames[left] > window:
            left += 1
        if right < i:
            right = i
        while right + 1 < n and frames[right + 1] - frames[i] <= window:
            right += 1
        dx = xs[left:right + 1] - xs[i]
        dy = ys[left:right + 1] - ys[i]
        d = np.hypot(dx, dy)
        result[i] = d.max() if len(d) else 0.0
    return result


def _select_active_ball_per_frame(
    ball_candidates,
    total_frames,
    frame_height,
    window=config.BALL_TRACK_DISPLACEMENT_WINDOW,
    debug_dump_path=None,
):
    """
    Implements the multi-ball disambiguation design from PROJECT.md: reject
    tracks that never move like a real ball, then collapse to one ball row
    per frame -- matching the original single-row-per-frame CSV shape so
    downstream code (transform.py, analysis.py) doesn't need to change.

    A frame with no accepted candidate gets an empty ball row (all-None),
    exactly like the original "no candidates found" branch -- analysis.py's
    load_data() already treats this as a normal tracking gap.

    UPDATED 2026-09-14: the accept/reject decision is now made PER POINT
    (see _windowed_net_displacement_per_point), not per whole chain.

    UPDATED this session -- DEPTH-ADAPTIVE displacement floor: real-data
    check (job 76a383379d90) showed far-court ball motion is compressed in
    pixel-space relative to near-court motion under this camera's
    perspective (same mechanism already fixed for prominence/margin
    thresholds in analysis.py and for player table_x via transform.py's
    _foot_point()) -- a flat min_displacement was very likely rejecting
    real far-court ball points as "near-static." Each point's own pixel_y
    now picks its own threshold via get_ball_min_displacement(), instead of
    one value for the whole video. See config.py for the
    BALL_TRACK_MIN_DISPLACEMENT_FAR_PX caveat (ESTIMATED, needs
    re-derivation from real candidate data -- see debug_dump_path).

    Fragments are still stitched (see stitch_track_fragments) into chains
    BEFORE this check -- ByteTrack briefly loses and re-acquires the real
    ball often enough (confirmed via real-footage flicker) that many
    genuine ball appearances are individually too short-lived to clear
    min_displacement's window on their own without being joined to their
    neighboring fragments first.

    Parameters
    ----------
    debug_dump_path : str, optional
        If given, writes every post-stitch candidate point (frame,
        chain_id, pixel_x, pixel_y, windowed_displacement_px, per-point
        threshold, accepted/rejected) to this CSV before collapsing to one
        row per frame. windowed_displacement_px (added 2026-09-27) is the
        raw measured value the accept/reject decision was based on --
        previously only the threshold and the boolean outcome were kept,
        which couldn't distinguish "rejected because genuinely static" from
        "rejected but close to the (possibly still-too-strict) far-side
        threshold." Lets you replay and tune the depth-adaptive threshold
        entirely offline against real data, without a GPU rerun per
        attempt.
    """
    if not ball_candidates:
        return [_empty_ball_row(f) for f in range(total_frames)]

    df = pd.DataFrame(ball_candidates)
    df = stitch_track_fragments(df, frame_height=frame_height)

    active_parts = []
    threshold_parts = []
    displacement_parts = []
    n_chains = 0
    for cid, group in df.groupby("chain_id"):
        n_chains += 1
        group = group.sort_values("frame")
        frames = group["frame"].to_numpy()
        xs = group["pixel_x"].to_numpy()
        ys = group["pixel_y"].to_numpy()
        local_disp = _windowed_net_displacement_per_point(frames, xs, ys, window)
        # DEPTH-ADAPTIVE: each point's own pixel_y picks its own floor,
        # rather than one config.BALL_TRACK_MIN_DISPLACEMENT_PX for every
        # point regardless of depth.
        per_point_threshold = get_ball_min_displacement(ys, frame_height)
        active_parts.append(pd.Series(local_disp >= per_point_threshold, index=group.index))
        threshold_parts.append(pd.Series(per_point_threshold, index=group.index))
        # NEW (2026-09-27): keep the raw measured value alongside the
        # threshold it was compared against. Added specifically to answer
        # the 954-2207-class question the dump previously couldn't:
        # whether a rejected point was CLOSE to its threshold (suggests
        # the far-side floor is still too strict) or far below it
        # (suggests it's genuinely static/clutter, correctly rejected).
        # Before this, the dump only had the boolean outcome, not the
        # number the decision was based on.
        displacement_parts.append(pd.Series(local_disp, index=group.index))

    active_mask = pd.concat(active_parts).reindex(df.index, fill_value=False)

    if debug_dump_path:
        dump_df = df.copy()
        dump_df["windowed_displacement_px"] = pd.concat(displacement_parts).reindex(df.index)
        dump_df["depth_threshold_px"] = pd.concat(threshold_parts).reindex(df.index)
        dump_df["accepted"] = active_mask
        dump_df.to_csv(debug_dump_path, index=False)
        print(f"  Dumped {len(dump_df)} post-stitch candidate point(s) across {n_chains} "
              f"chain(s) to {debug_dump_path} for offline threshold tuning "
              f"(now includes windowed_displacement_px alongside the threshold).")

    # Fail-safe, not fail-open: if nothing passes, the correct answer is
    # "no real ball this frame" (empty rows), never "fall back to every
    # unfiltered candidate" -- the latter would silently hand back static
    # false positives exactly when the filter is needed most.
    filtered = df[active_mask]

    rows = []
    grouped = {f: g for f, g in filtered.groupby("frame")}
    for f in range(total_frames):
        candidates = grouped.get(f)
        if candidates is None or len(candidates) == 0:
            rows.append(_empty_ball_row(f))
            continue
        # Multiple surviving tracks/points in the same frame (e.g. two
        # moving balls) -- fall back to highest confidence, same tie-break
        # the original single-candidate version used.
        best = candidates.loc[candidates["confidence"].idxmax()]
        rows.append({
            "frame": f, "type": "ball", "track_id": int(best["track_id"]),
            "pixel_x": best["pixel_x"], "pixel_y": best["pixel_y"],
            "x1": best["x1"], "y1": best["y1"], "x2": best["x2"], "y2": best["y2"],
            "confidence": best["confidence"],
        })

    n_points_total = len(df)
    n_points_kept = int(active_mask.sum())
    n_rejected = n_points_total - n_points_kept
    if n_rejected:
        print(f"  Rejected {n_rejected} of {n_points_total} ball candidate point(s) across "
              f"{n_chains} chain(s) as near-static (no {window}-frame local span clearing "
              f"that point's depth-adjusted displacement floor)")

    return rows


def _empty_ball_row(frame_num):
    return {
        "frame": frame_num, "type": "ball", "track_id": None,
        "pixel_x": None, "pixel_y": None,
        "x1": None, "y1": None, "x2": None, "y2": None,
        "confidence": None,
    }


if __name__ == "__main__":
    run_detection(
        video_path=config.VIDEO_PATH,
        ball_model_path=config.BALL_MODEL_PATH,
        player_model_path=config.PLAYER_MODEL_PATH,
        raw_csv_path=config.RAW_CSV,
    )
