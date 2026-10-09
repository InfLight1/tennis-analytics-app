"""
diagnose_ball_candidates.py

Targeted re-run of ONLY the ball model (skips player detection entirely)
over specific frame windows, dumping every raw candidate BEFORE
_select_active_ball_per_frame()'s displacement filter collapses them down
to one row per frame. detection.py's final CSV only keeps the winner, so
there's no way to recover this from raw_detection.csv after the fact --
this has to re-run inference, but only over the windows you specify (not
the whole clip), which is much faster than a full re-run.

Use this to check: in a frame range where match_data.csv shows the ball
"frozen" at one pixel location for many frames, was there ALSO a real,
moving candidate present that lost the tie-break to a static false
positive? If so, that's detection.py's active-track selection logic
picking wrong -- not a video/detector-visibility problem.

Also reproduces _select_active_ball_per_frame()'s accept/reject decision
per track (using the SAME total-displacement calculation currently in
detection.py) so you can see directly why a track was kept or dropped.

NOTE: uses a FRESH ByteTrack instance per window (not continuous across
the whole video), so track_id numbers restart at each window -- fine for
this diagnostic since we're inspecting each window independently, not
tracking continuity across the whole clip.

Editable variables below, no CLI args. Run directly:
    python diagnose_ball_candidates.py
"""

import numpy as np
import pandas as pd
import cv2
import supervision as sv
from ultralytics import YOLO

import config

# ── Editable top-of-file variables ─────────────────────────────────────────
VIDEO_PATH = config.VIDEO_PATH
BALL_MODEL_PATH = config.BALL_MODEL_PATH
OUTPUT_CANDIDATES_CSV = "ball_candidates_debug.csv"

# Frame windows to inspect (inclusive), based on where match_data.csv shows
# suspiciously static ball positions vs. ground truth events. Adjust freely.
FRAME_WINDOWS = [
    (150, 310),
]

BALL_CONF = config.BALL_CONF_THRESHOLD
IMGSZ = config.INFERENCE_IMGSZ

# Same params + filter threshold detection.py currently uses -- kept
# identical on purpose so the accept/reject verdict printed here matches
# what the real pipeline would decide.
TRACKER_ACTIVATION_THRESHOLD = config.TRACKER_ACTIVATION_THRESHOLD
TRACKER_LOST_BUFFER = config.TRACKER_LOST_BUFFER
TRACKER_MATCHING_THRESHOLD = config.TRACKER_MATCHING_THRESHOLD
TRACKER_FRAME_RATE = config.TRACKER_FRAME_RATE
MIN_DISPLACEMENT = config.BALL_TRACK_MIN_DISPLACEMENT_PX


def run_window(cap, ball_model, start_frame, end_frame):
    tracker = sv.ByteTrack(
        track_activation_threshold=TRACKER_ACTIVATION_THRESHOLD,
        lost_track_buffer=TRACKER_LOST_BUFFER,
        minimum_matching_threshold=TRACKER_MATCHING_THRESHOLD,
        frame_rate=TRACKER_FRAME_RATE,
    )

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    candidates = []

    for frame_num in range(start_frame, end_frame + 1):
        ret, frame = cap.read()
        if not ret:
            print(f"  WARNING: could not read frame {frame_num}, stopping window early.")
            break

        results = ball_model(frame, conf=BALL_CONF, imgsz=IMGSZ, verbose=False)[0]
        detections = sv.Detections.from_ultralytics(results)
        detections = tracker.update_with_detections(detections)

        for i, box in enumerate(detections.xyxy):
            x1, y1, x2, y2 = box.tolist()
            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            tid = int(detections.tracker_id[i]) if detections.tracker_id is not None else -1
            conf = float(detections.confidence[i])
            candidates.append({
                "frame": frame_num, "track_id": tid,
                "pixel_x": cx, "pixel_y": cy,
                "confidence": conf,
            })

    return candidates


def summarize_tracks(df, window_label):
    print(f"\n--- Track summary: {window_label} ---")
    if len(df) == 0:
        print("  No ball candidates detected at all in this window.")
        return

    for tid, group in df.groupby("track_id"):
        group = group.sort_values("frame")
        dx = group["pixel_x"].diff().fillna(0)
        dy = group["pixel_y"].diff().fillna(0)
        total_displacement = float(np.sqrt(dx**2 + dy**2).sum())
        # Net displacement (start to end), for contrast with the
        # accumulated-step-size total detection.py actually filters on.
        net_displacement = float(np.hypot(
            group["pixel_x"].iloc[-1] - group["pixel_x"].iloc[0],
            group["pixel_y"].iloc[-1] - group["pixel_y"].iloc[0],
        ))
        verdict = "ACCEPTED" if total_displacement >= MIN_DISPLACEMENT else "rejected (static)"
        print(f"  track_id={tid:>4}  frames {int(group['frame'].min())}-{int(group['frame'].max())} "
              f"({len(group)} dets)  avg_conf={group['confidence'].mean():.2f}  "
              f"total_displacement={total_displacement:6.1f}px  net_displacement={net_displacement:6.1f}px "
              f"  -> {verdict}")

    accepted_ids = set()
    for tid, group in df.groupby("track_id"):
        dx = group.sort_values("frame")["pixel_x"].diff().fillna(0)
        dy = group.sort_values("frame")["pixel_y"].diff().fillna(0)
        if float(np.sqrt(dx**2 + dy**2).sum()) >= MIN_DISPLACEMENT:
            accepted_ids.add(tid)

    if not accepted_ids:
        print("  ALL tracks in this window would be rejected as static -- "
              "every frame here gets an empty ball row under current logic.")
    else:
        print(f"  {len(accepted_ids)} of {df['track_id'].nunique()} track(s) survive the filter.")


def main():
    print(f"Loading ball model: {BALL_MODEL_PATH}")
    ball_model = YOLO(str(BALL_MODEL_PATH))
    cap = cv2.VideoCapture(str(VIDEO_PATH))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {VIDEO_PATH}")

    all_candidates = []
    for start, end in FRAME_WINDOWS:
        window_label = f"frames {start}-{end}"
        print(f"\nProcessing {window_label} ({end - start + 1} frames)...")
        candidates = run_window(cap, ball_model, start, end)
        df = pd.DataFrame(candidates)
        summarize_tracks(df, window_label)
        all_candidates.extend(candidates)

    cap.release()

    out_df = pd.DataFrame(all_candidates)
    out_df.to_csv(OUTPUT_CANDIDATES_CSV, index=False)
    print(f"\nWrote {len(out_df)} raw candidate rows across {len(FRAME_WINDOWS)} window(s) "
          f"to {OUTPUT_CANDIDATES_CSV}")
    print("\nNext: check whether any REJECTED track in the printed summaries looks like a "
          "real moving ball (short-lived, plausible confidence, but too little accumulated "
          "displacement to pass) -- that would confirm the active-track filter is the problem, "
          "not detector visibility.")


if __name__ == "__main__":
    main()
