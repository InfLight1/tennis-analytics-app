"""
Central configuration for the tennis pipeline. All paths resolve relative
to this file's location, so the pipeline runs on any machine unmodified.
"""

from pathlib import Path

# ── Base directories ─────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent.parent   # "Tennis Performance App/"
CODE_DIR   = BASE_DIR / "Code"
VIDEOS_DIR = BASE_DIR / "Videos"

# ── Input video ───────────────────────────────────────────────────────────
VIDEO_PATH = VIDEOS_DIR / "Tennis1.mp4"

# ── Models ────────────────────────────────────────────────────────────────
BALL_MODEL_PATH   = BASE_DIR / "Training" / "runs" / "detect" / "tennis_ball_v1-5" / "weights" / "best.pt"
PLAYER_MODEL_PATH = CODE_DIR / "yolov8n.pt"   # generic YOLOv8n person detector

# ── Pipeline artifacts (intermediate + final outputs) ────────────────────
RAW_CSV       = CODE_DIR / "raw_detection.csv"
MATCH_CSV     = CODE_DIR / "match_data.csv"
MATRIX_PATH   = CODE_DIR / "perspective_matrix.npy"
BIRDEYE_CHECK = CODE_DIR / "birdeye_check.jpg"
OUTPUT_VIDEO  = CODE_DIR / "output_annotated.mp4"
HEATMAP_PATH  = CODE_DIR / "final_heatmap.png"
EVENTS_CSV    = CODE_DIR / "rally_events.csv"
METRICS_CSV   = CODE_DIR / "rally_metrics.csv"

# ── Court geometry ────────────────────────────────────────────────────────
# Units: 1 unit = 1cm. Singles court: 23.77m x 8.23m.
TABLE_W = 2377   # baseline to baseline
TABLE_H = 823    # sideline to sideline

# Reference-point offsets, in court-space units from the near baseline (x=0).
# See calibration.py's get_reference_points_schema() for the full point set.
SERVICE_LINE_OFFSET_FROM_BASELINE = 549   # baseline -> service line (18ft)
NET_POSITION_OFFSET = TABLE_W / 2         # net at court's horizontal midpoint

# ── Detection / tracking parameters ──────────────────────────────────────
BALL_CONF_THRESHOLD   = 0.3
PLAYER_CONF_THRESHOLD = 0.5
INFERENCE_IMGSZ       = 1280

TRACKER_ACTIVATION_THRESHOLD = 0.25
# Split 2026-09: real 10-min point-play footage showed EVERY between-rally
# gap >= 90 frames (median 346 frames / ~11.5s, max 1909 / ~64s) -- the
# player tracker's lost-track buffer was expiring on almost every single
# point, forcing a fresh player_id nearly every rally (18 distinct IDs
# across ~20 rallies, 70% of hits unattributable to either player).
# CAVEAT: ByteTrack's default matching is motion/IOU-based, not
# appearance-based -- a longer buffer keeps a track "alive" longer, but if
# a player walks somewhere very different during the pause, the
# Kalman-predicted position won't track them there and a new ID can still
# get assigned regardless of buffer size. This raises the buffer to cover
# most real pauses, but is not guaranteed to fully eliminate ID churn --
# re-validate against real footage; a court-side-based post-hoc identity
# reconciliation may still be needed if churn persists.
PLAYER_TRACKER_LOST_BUFFER = 900   # frames (~30s @30fps) -- was shared at 90 with the ball tracker
BALL_TRACKER_LOST_BUFFER   = 90    # frames (~3s) -- unchanged; ball-specific gap-bridging is handled separately in detection.py's stitch_track_fragments

# SPLIT 2026-09-27 -- was one shared TRACKER_MATCHING_THRESHOLD (0.8) for
# both trackers. CORRECTED same session, after an initial wrong
# assumption caught by testing before shipping (see below) -- checked
# supervision's actual ByteTrack source (tracker/byte_tracker/core.py):
# minimum_matching_threshold is NOT a minimum IOU. It's passed as `thresh`
# to `linear_assignment` against `iou_distance` (1 - IOU, a COST), so a
# match is accepted when cost <= threshold, i.e. IOU >= (1 - threshold).
# A HIGHER value is therefore MORE permissive, not less -- the library's
# own docstring confirms this: "Decreasing minimum_matching_threshold
# improves accuracy but risks fragmentation." First attempt this session
# assumed the opposite (treated 0.8 as an IOU floor and tried lowering it
# to 0.2, i.e. accidentally requiring IOU >= 0.8 -- stricter, not looser)
# -- caught via a full frame-by-frame ByteTrack replay against real
# diagnostic data before deploying: survival was FLAT across
# threshold=0.05-0.5 (all effectively "require near-total overlap") and
# best at the untouched 0.8. Reverted the threshold change entirely;
# BOTH trackers correctly stay at 0.8 (already the most permissive
# reasonable value). The real, working fix is box padding below --
# lowering this threshold further is NOT part of the fix and would make
# things worse, not better.
PLAYER_TRACKER_MATCHING_THRESHOLD = 0.8
BALL_TRACKER_MATCHING_THRESHOLD = 0.8     # kept as a separate constant for future independent tuning; currently unchanged from the player value -- see corrected rationale above and BALL_TRACK_BOX_PAD_PX below for the actual fix
TRACKER_FRAME_RATE           = 30

# Pixels to pad each side of a ball detection's box by BEFORE feeding it
# to ball_tracker for IOU-based association (detection.py) -- NOT applied
# to the stored pixel_x/y/x1-y2 values written to raw_detection.csv, only
# to what the tracker uses to decide "is this the same object as last
# frame." Needed because real consecutive-frame ball motion (15-25px, up
# to ~200px+ post-bounce) regularly exceeds the ball's own ~15-18px box
# width, producing literal zero-overlap (IOU=0.000) between the SAME
# physical ball one frame apart -- no matching-threshold value can bridge
# a true zero-overlap pair (see BALL_TRACKER_MATCHING_THRESHOLD above),
# the boxes must be made to overlap first.
#
# VALIDATED empirically via a full frame-by-frame ByteTrack replay against
# real diagnostic data (frames 298-386, job 76a383379d90, 21 real
# above-confidence-threshold candidates in this window) -- NOT just
# pairwise IOU math, which turned out to be an incomplete picture (the
# tracker's Kalman-predicted position and gap-handling behavior matter
# too, not just raw box overlap). Measured survival into the tracked
# pool at threshold=0.8 (unchanged) across padding values:
#   pad=0 (baseline): 3/21 (14%) survive
#   pad=15:           8/21 (38%)
#   pad=20:          11/21 (52%)  <- chosen value
#   pad=30:          11/21 (52%)  (plateau)
#   pad=50:          15/21 (71%)
# 20px chosen over the higher-recall 40-60px options as the more
# conservative starting point -- larger padding recovers more real
# candidates but also has more room to false-merge with nearby stray-ball
# clutter (real frames can have 40-80+ concurrent candidates; a prior
# session's stitch validation found confirmed clutter as close as ~33px
# to a real fragment's endpoint). Re-check ball_candidates_debug.csv from
# a fresh run for false-merge signatures (a chain jumping between
# spatially distant clusters) before considering raising this further.
# This ALSO does not fully close the 298-386 dead zone -- a real ~36-frame
# span in that window (313-349) has ZERO candidates even at 0.02
# confidence, a genuine model-recall gap this fix cannot address at all.
BALL_TRACK_BOX_PAD_PX = 20

# ── Ball linker (ball_linker.py) ─────────────────────────────────────────
# ADDED 2026-09-27: replaces ByteTrack + stitching + the displacement
# filter for the BALL. See ball_linker.py's docstring for the root cause
# (IOU matching can't follow a small ball moving several box-widths per
# frame, and this footage repeats every 5th frame).
USE_BALL_LINKER = True
DETECTION_CHUNK_SEEK = True   # chunked detection seeks to its start frame (verified exact; falls back to sequential skip)

# The ball model was trained on 1920x1080 frames at imgsz 1280 (a 1.5x
# downscale; Training/runs/detect/tennis_ball_v1-5/args.yaml). Running 4K
# footage at 1280 is a 3x downscale -- the ball arrives at half the size the
# model learned. Keep the training scale: imgsz = frame width / 1.5.
BALL_TRAIN_FRAME_WIDTH = 1920
BALL_TRAIN_IMGSZ = 1280


def ball_inference_imgsz(frame_width):
    size = frame_width * BALL_TRAIN_IMGSZ / BALL_TRAIN_FRAME_WIDTH
    return max(INFERENCE_IMGSZ, int(round(size / 32)) * 32)
BALL_LINK_CONF_MIN = 0.15            # model detections below this are ignored; static clutter is removed separately
BALL_LINK_STATIC_WINDOW = 10         # frames either side to look for a repeat at the same spot
BALL_LINK_STATIC_RADIUS_PX = 6       # "same spot"
BALL_LINK_STATIC_MIN_HITS = 6        # repeats within the window -> static clutter (a real ball repeats at most ~1-3x)
BALL_LINK_MAX_GAP_FRAMES = 8         # frames a track may go undetected and still be continued
BALL_LINK_DUPLICATE_PX = 3           # a 1-frame "move" this small = duplicated video frame, not a stop
BALL_LINK_BASE_GATE_PX = 40          # match radius around the velocity prediction...
BALL_LINK_SPEED_GATE_FRAC = 0.5      # ...plus this fraction of the ball's per-frame speed x frames elapsed
BALL_LINK_MAX_STEP_PX = 260          # max per-frame jump accepted off-prediction (hits/bounces reverse direction)
BALL_LINK_MIN_TRACK_POINTS = 4       # shorter tracks are noise
BALL_LINK_MIN_MEDIAN_SPEED_PX = 6    # px/frame; a stray ball rolling on court moves ~2-3
BALL_LINK_FAST_SEGMENT_PX = 20      # ...or a fast stretch (best median of 5 moving steps) this big: a struck ball that then stalls/dies (0 = off)
BALL_LINK_PREFER_FAST = False       # overlapping tracks: prefer the faster one (tested 10-07: hurts the hold-out, off)
BALL_LINK_LOCAL_SLOW_PX = 6         # overlapping tracks: one moving slower than this right now (median step, +/-WINDOW frames) loses (0 = off)
BALL_LINK_LOCAL_WINDOW = 4
BALL_LINK_ROLLER_MAX_PX = 0        # a track whose fastest stretch stays under this is a rolling stray ball: loses to any overlapping track (0 = off)

INTERPOLATION_LIMIT = 10   # max frames to linearly interpolate over gaps

# Margin outside the court (court-space units) before a point is off-court.
# ESTIMATED — validate against real reprojection error once available.
OFF_TABLE_MARGIN = 150
IN_OUT_TOLERANCE_CM = 10   # in/out call slack (line width + calibration); NOT the off-court margin above
# Players stand well behind the baselines (measured 2026-09-27 on job
# 76a383379d90 with a correct calibration: far player median 4.3 m, 90th pct
# 8.3 m behind the far baseline). With the 150 cm ball margin ~46% of player
# positions were nulled and player identity resolved 9/40 rallies. A wrong
# calibration had masked this by pulling far players toward the court.
PLAYER_BASELINE_MARGIN = 800   # cm behind either baseline
PLAYER_SIDE_MARGIN = 450       # cm outside the singles sidelines (people on the next court are further)

# Video frame height in pixels; used by analysis.py's depth-adaptive
# thresholds. NOT a single fixed value across all footage from this
# project -- CONFIRMED via ffprobe that different source files differ:
#   - tennis1_clip.mp4 / tennis1_clip2.mp4: 3840x2160
#   - the 40-min combined rally+drill+point-play recording: 1920x1080
# FRAME_HEIGHT must match whichever file is actually being run through
# the pipeline for that session -- set to 1080 for the 40-min recording
# (2026-09-19). Re-derive analysis.py's depth-adaptive thresholds if
# they were tuned against the 2160p value; don't assume they carry over
# unchanged to 1080p footage.
FRAME_HEIGHT = 1080

# DEPTH-ADAPTIVE as of this session. Real-data check on job 76a383379d90
# (14-min real point-play clip) found accepted ball detections split 71%
# near-half / 29% far-half of on-table frames (by table_x relative to the
# net) -- should be close to symmetric in real singles play -- and that
# far-half survivors moved ~40% fewer pixels/frame than near-half
# survivors (median 1.4px/frame vs 2.8px/frame). This is the same
# perspective-compression failure class already found and fixed for
# BOUNCE_PROMINENCE_NEAR_PX/FAR_PX, HIT_PROMINENCE_NEAR_PX/FAR_PX, and
# PLAYER_PROXIMITY_MARGIN_NEAR_PX/FAR_PX (all in analysis.py) and for
# player table_x via transform.py's _foot_point() -- under this elevated,
# oblique, behind-baseline camera, the same real-world ball motion
# produces far less pixel-space displacement far from the camera than
# near it. A flat BALL_TRACK_MIN_DISPLACEMENT_PX was very likely rejecting
# genuine far-court ball motion as "near-static," contributing to the
# ball-detection coverage regression found via ground-truth comparison
# this session. See detection.py's get_ball_min_displacement() /
# _interp_by_depth() -- same interpolation formula as analysis.py's own
# _interp_by_depth(), duplicated rather than shared.
BALL_TRACK_MIN_DISPLACEMENT_NEAR_PX = 15   # unchanged -- already validated against real near-court data
BALL_TRACK_MIN_DISPLACEMENT_FAR_PX = 8     # ESTIMATED -- placeholder ratio, NOT yet re-derived from a real far-court event. Re-derive via detection.py's debug_dump_path before trusting far-court recall numbers built on this value.
BALL_TRACK_DISPLACEMENT_WINDOW = 30        # frames (~1s @30fps), unchanged

# ── Ball track stitching ──────────────────────────────────────────────────
# ByteTrack frequently loses and re-acquires the real ball for several
# frames at a time (confirmed via real-footage flicker, 2026-09), assigning
# a new track_id each time -- fragmenting one real trajectory into several
# pieces, each individually too short to clear BALL_TRACK_MIN_DISPLACEMENT_PX.
# These bridge gaps between fragments before the displacement filter runs.
#
# UPDATED 2026-09 — re-derived from real confirmed-real-event data (bounce@424,
# hit@446, bounce@599), which surfaced two things the original 3-frame/25px
# values (tuned before any real high-speed footage existed) didn't account
# for:
#   1. Real post-bounce ball motion produces gaps up to 6 frames / ~210px
#      between confidence-threshold-surviving detections -- much larger than
#      originally assumed. Old tight values silently discarded these
#      real fragments as unbridgeable, contributing directly to the ~16.5%
#      real-detection-coverage headline problem.
#   2. Simply loosening these values is NOT safe on its own: real footage
#      has persistent near-static clutter tracks (~1-1.5px internal jitter)
#      that can sit CLOSER to a real fragment's endpoint than the correct
#      next real fragment does. A pure nearest-distance match would
#      wrongly prefer the closer clutter track once the ceiling is raised
#      enough to bridge real motion. See BALL_TRACK_STITCH_MIN_FRAGMENT_MOVEMENT_PX
#      below -- stitch_track_fragments() now excludes any multi-row track
#      under that movement floor from being a stitch source/target at all,
#      which is what makes loosening the values below safe.
BALL_TRACK_STITCH_MAX_GAP_FRAMES = 6
BALL_TRACK_STITCH_MAX_GAP_DIST_PX = 220

# Minimum a multi-row track must move (its own start-to-end displacement)
# to be eligible as a stitch source/target at all -- see explanation above.
# Real clutter tracks measured at 0.0-1.5px internal movement even across
# 25-40 frames; real confirmed ball fragments measured 9px+ even across
# just 2-4 frames -- wide, clean separation, no gray zone found in real
# data so far. Single-row tracks can't be assessed this way and are always
# eligible (unchanged from original design).
#
# DEPTH-ADAPTIVE as of this session -- same perspective-compression
# rationale as BALL_TRACK_MIN_DISPLACEMENT_NEAR_PX/FAR_PX above: a
# genuinely-moving far-court fragment produces less pixel-space
# start-to-end movement than the same real motion near the camera, so a
# flat floor risks excluding real far-court fragments from stitching
# entirely (separate from, and upstream of, the displacement-filter fix
# above -- a fragment excluded here never even reaches that filter).
BALL_TRACK_STITCH_MIN_FRAGMENT_MOVEMENT_NEAR_PX = 5   # unchanged -- already validated
BALL_TRACK_STITCH_MIN_FRAGMENT_MOVEMENT_FAR_PX = 3    # ESTIMATED -- same re-derivation caveat as the displacement floor above

# ── Court-coverage grid ───────────────────────────────────────────────────
# Shared by match_stats.court_coverage() and prioritization.py.
# ESTIMATED — revisit once real coverage data exists.
COURT_GRID_ROWS = 6
COURT_GRID_COLS = 4

# ── Rally-length bucket thresholds ───────────────────────────────────────
# Shared by match_stats.rally_length_stats() and prioritization.py.
# ESTIMATED — unvalidated against real rally-length ground truth.
RALLY_LENGTH_SHORT_MAX_HITS = 4
RALLY_LENGTH_LONG_MIN_HITS = 9

# ── Match scoring (scoring.py) ────────────────────────────────────────────
# Standard singles rules. Both open-question items from PROJECT.md §10 are
# resolved as configurable, not hard-coded — defaults below, both directions
# supported.
NO_AD_SCORING = True             # default: sudden-death at 3-3 (no deuce/ad). False = standard ad scoring.
GAMES_TO_WIN_SET = 6
TIEBREAK_AT_GAMES = 6            # games-games score that triggers a set tiebreak
TIEBREAK_POINTS_TO_WIN = 7       # standard set tiebreak length
TIEBREAK_WIN_BY = 2
SETS_TO_WIN_MATCH = 2            # 2 = best-of-3 (default), 3 = best-of-5

# If True, the deciding set (the set that would end the match) uses a
# longer match-tiebreak instead of a standard set tiebreak at 6-6. Default
# False: every set, including the deciding one, uses a standard
# TIEBREAK_POINTS_TO_WIN-point tiebreak. Only read when MATCH_TIEBREAK_FINAL_SET
# is True.
MATCH_TIEBREAK_FINAL_SET = False
MATCH_TIEBREAK_POINTS_TO_WIN = 10

# ── Shot-type classification (shot_type.py) ───────────────────────────────
# Volley/groundstroke split by distance from net. Derived from existing
# court geometry (net-to-service-line distance) rather than an unrelated
# magic number, but the boundary itself is still an approximation — real
# volleys are sometimes hit from just behind the service line too (players
# still moving forward). ESTIMATED — validate against real point-play
# footage once available; widen/narrow if the geometry-vs-bounce
# disagreement rate (see shot_type.py) is high.
VOLLEY_ZONE_HALF_WIDTH_CM = NET_POSITION_OFFSET - SERVICE_LINE_OFFSET_FROM_BASELINE

# ── Player identity resolution (player_identity.py) ───────────────────────
# Minimum real (non-NaN table_x/table_y) frames a track_id needs within a
# single rally's frame window to count as one of that rally's 2 real
# players, rather than a stray/clutter detection. Real players are on
# court continuously for the rally; noise isn't. ESTIMATED — widen if
# real short rallies get falsely flagged as "fewer_than_2_tracked_players".
PLAYER_IDENTITY_MIN_FRAMES = 5
