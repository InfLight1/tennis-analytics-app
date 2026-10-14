"""
Diff raw ball detections against your ACTUAL detection.py filter pipeline,
for the two windows now confirmed (via manual video check) to contain real
events currently missing from production output:

  frames ~415-455: bounce@424, ball in motion@439, hit@446
  frames ~590-615: bounce@599, ball in motion after@607

Raw model inference at conf=0.05 already found these tracks moving with
real net displacement (see low_conf_movement_summary.csv, tracks
91/142/152) at confidences (0.70-0.85) well above production's
config.BALL_CONF_THRESHOLD (0.3). Production detection.py currently
outputs ZERO real ball detections in these windows. This script re-runs
the exact same ball detect+track loop as run_detection() (same model,
same ByteTrack config, same candidate schema) for just these frames, then
calls your real stitch_track_fragments() / _max_windowed_net_displacement()
/ _select_active_ball_per_frame() to show exactly which stage drops each
track and why (never stitched into a long-enough chain vs. stitched but
still under the displacement threshold).

IMPORTANT CAVEAT: this script uses a FRESH ByteTrack instance scoped to
just each ~40-frame window. Production runs ONE continuous tracker across
the full 684-frame video, accumulating 40-80+ concurrent stray-ball
tracks the whole way through (see PROJECT.md). If this script shows a
chain PASSING the displacement filter but production still finds nothing
in that window, that is NOT a contradiction -- it's a finding: the real
bug would then be in cross-video tracker state (e.g. the real ball's
track_id colliding with, or being shadowed by, an already-long-lived
unrelated stray track), not in stitch/displacement logic itself, which
this script would have already cleared. If that happens, the next step
is re-running with ONE tracker fed the full video from frame 0 through
the window end (slower, but the only way to reproduce accumulated state).

Run standalone:
    python diff_pipeline_stages.py
"""

import cv2
import pandas as pd
import supervision as sv
from pathlib import Path
from ultralytics import YOLO

# Place this script in the same folder as detection.py/config.py (Code/) --
# no sys.path manipulation needed, same as your other scripts.
import config
from detection import (
    _max_windowed_net_displacement,
    _select_active_ball_per_frame,
    stitch_track_fragments,
)

# ---- editable config ----
OUTPUT_DIR = Path(r"C:\Users\rudra\Downloads\Projects\Tennis Performance App\Diagnostics")

# Padded slightly beyond the confirmed event frames to capture full tracks
WINDOWS = [
    (415, 455),   # bounce@424, motion@439, hit@446
    (590, 615),   # bounce@599, motion@607
]


def collect_ball_candidates(video_path, frame_start, frame_end):
    """
    Mirrors run_detection()'s ball-only loop exactly: same model, same
    ByteTrack config, same candidate dict schema (frame/track_id/pixel_x/
    pixel_y/x1/y1/x2/y2/confidence). Confined to one window so ByteTrack
    state doesn't bleed across unrelated time ranges.
    """
    ball_model = YOLO(str(config.BALL_MODEL_PATH))
    ball_tracker = sv.ByteTrack(
        track_activation_threshold=config.TRACKER_ACTIVATION_THRESHOLD,
        lost_track_buffer=config.TRACKER_LOST_BUFFER,
        minimum_matching_threshold=config.TRACKER_MATCHING_THRESHOLD,
        frame_rate=config.TRACKER_FRAME_RATE,
    )

    cap = cv2.VideoCapture(str(video_path))
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_start)

    candidates = []
    for frame_num in range(frame_start, frame_end):
        ret, frame = cap.read()
        if not ret:
            break

        ball_results = ball_model(frame, conf=config.BALL_CONF_THRESHOLD, imgsz=config.INFERENCE_IMGSZ)[0]
        ball_detections = sv.Detections.from_ultralytics(ball_results)
        ball_detections = ball_tracker.update_with_detections(ball_detections)

        for i, box in enumerate(ball_detections.xyxy):
            x1, y1, x2, y2 = box.tolist()
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            tid = int(ball_detections.tracker_id[i]) if ball_detections.tracker_id is not None else -1
            conf = float(ball_detections.confidence[i])
            candidates.append({
                "frame": frame_num, "track_id": tid,
                "pixel_x": cx, "pixel_y": cy,
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "confidence": conf,
            })

    cap.release()
    return candidates


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for start, end in WINDOWS:
        print(f"\n{'='*60}\nWindow {start}-{end}\n{'='*60}")

        candidates = collect_ball_candidates(config.VIDEO_PATH, start, end)
        if not candidates:
            print("  No raw candidates at all in this window (unexpected -- "
                  "earlier diagnostic found tracks here at conf=0.05).")
            continue

        raw_df = pd.DataFrame(candidates)
        print(f"Stage 0 (raw candidates): {len(raw_df)} rows across "
              f"{raw_df['track_id'].nunique()} raw ByteTrack track_ids, "
              f"frames {raw_df['frame'].min()}-{raw_df['frame'].max()}")

        # Stage 1: stitching only (adds chain_id, no filtering yet)
        stitched_df = stitch_track_fragments(raw_df.copy())
        n_chains = stitched_df["chain_id"].nunique()
        print(f"Stage 1 (stitch_track_fragments): {len(stitched_df)} rows -> "
              f"{stitched_df['track_id'].nunique()} raw tracks stitched into {n_chains} chain(s)")

        # Per-chain displacement check, using the REAL helper function --
        # shows exactly why each chain would pass/fail the production filter.
        print(f"\n  Per-chain check (min_displacement={config.BALL_TRACK_MIN_DISPLACEMENT_PX}px, "
              f"window={config.BALL_TRACK_DISPLACEMENT_WINDOW} frames):")
        for cid, g in stitched_df.groupby("chain_id"):
            g = g.sort_values("frame")
            frames = g["frame"].to_numpy()
            xs = g["pixel_x"].to_numpy()
            ys = g["pixel_y"].to_numpy()
            max_disp = _max_windowed_net_displacement(
                frames, xs, ys, config.BALL_TRACK_DISPLACEMENT_WINDOW
            )
            verdict = "PASS" if max_disp >= config.BALL_TRACK_MIN_DISPLACEMENT_PX else "REJECTED"
            raw_tids = sorted(g["track_id"].unique().tolist())
            print(f"    chain {cid} (raw track_ids {raw_tids}): frames {frames.min()}-{frames.max()}, "
                  f"n_rows={len(g)}, max_net_disp={max_disp:.1f}px -> {verdict}")

        # Stage 2: full production function (stitch + filter + best-pick),
        # exactly as run_detection() calls it.
        total_frames = end  # function iterates range(total_frames); harmless extra empty rows before `start`
        resolved_rows = _select_active_ball_per_frame(candidates, total_frames)
        window_rows = [r for r in resolved_rows if start <= r["frame"] < end]
        n_found = sum(1 for r in window_rows if r["pixel_x"] is not None)
        print(f"\nStage 2 (_select_active_ball_per_frame, full production path): "
              f"{n_found} / {len(window_rows)} frames in window have a resolved ball row")

        print("\n  Frame-by-frame result:")
        for r in window_rows:
            if r["pixel_x"] is not None:
                print(f"    frame {r['frame']}: FOUND  (track_id={r['track_id']}, "
                      f"pixel=({r['pixel_x']:.1f},{r['pixel_y']:.1f}), conf={r['confidence']:.2f})")
            else:
                print(f"    frame {r['frame']}: empty")

        raw_df.to_csv(OUTPUT_DIR / f"raw_candidates_{start}_{end}.csv", index=False)
        stitched_df.to_csv(OUTPUT_DIR / f"stitched_{start}_{end}.csv", index=False)
        pd.DataFrame(window_rows).to_csv(OUTPUT_DIR / f"resolved_{start}_{end}.csv", index=False)

    print(f"\nAll stage outputs written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
