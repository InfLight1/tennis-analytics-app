"""
Diagnostic: does a much-lowered YOLO confidence threshold produce ball
candidates in the dead-zone frames (where the normal-threshold pipeline
finds zero real detections)?

Purpose: decide whether the 16.5%-coverage gap is a threshold/confidence
issue (fixable by relabeling near-miss detections) or a genuine capture-level
wall (motion blur / low contrast -> model produces nothing at any threshold,
matching the 2026-09-03 finding).

Time-boxed - if this doesn't show a clear signal in ~30-60 min, treat the
gap as confirmed capture-level and move on to Week 3's hit-detection redesign.
"""

"""
Diagnostic: among the low-confidence YOLO candidates in the dead-zone
frames, is ANY candidate actually moving (plausibly the real ball) or are
they all static false positives (court lines, net posts, fixed background)?

Rationale for the rewrite: the first pass only counted candidates and
found ~55-90 per frame at every threshold, with a suspiciously stable
max_conf (~0.83-0.89) across hundreds of consecutive frames. That's
consistent with a static high-confidence false positive dominating the
pool, not the ball -- candidate COUNT alone can't tell the two apart.

This version records every candidate's box center per frame, then reuses
your production pipeline's own test (rolling net displacement over a
window, same threshold logic as detection.py's _select_active_ball_per_frame)
to flag which candidate TRACKS are actually moving vs. static.

Interpretation:
  - No candidate track anywhere shows real net displacement -> genuinely
    nothing ball-like in the frame at any threshold. Capture-level wall
    confirmed, matches 2026-09-03 finding. Don't relabel, move to Week 3.
  - A candidate track DOES show real displacement, roughly consistent with
    plausible ball speed -> worth a manual video check at those frames;
    targeted relabeling may be worth it.
"""

from ultralytics import YOLO
import cv2
import pandas as pd
from pathlib import Path

# ---- editable config ----
MODEL_PATH = r"C:\Users\rudra\Downloads\Projects\Tennis Performance App\Models\tennis_ball_v1.pt"          # your trained ball detector
VIDEO_PATH = r"C:\Users\rudra\Downloads\Projects\Tennis Performance App\Videos\tennis1_clip.mp4"
OUTPUT_CSV = Path(r"C:\Users\rudra\Downloads\Projects\Tennis Performance App\Diagnostics\low_conf_candidates.csv")
SUMMARY_CSV = Path(r"C:\Users\rudra\Downloads\Projects\Tennis Performance App\Diagnostics\low_conf_movement_summary.csv")

DEAD_ZONE_RANGES = [
    (289, 400),   # right after the first island ends - includes hit@296
    (400, 608),   # the big void
]

CONF_THRESHOLD = 0.05   # single low threshold; superset of 0.10/0.25 candidates
IMGSZ = 1280

# Same convention as detection.py: net displacement over a rolling window,
# not lifetime-cumulative (that bug is already fixed in production - reuse
# the fix here too).
DISPLACEMENT_WINDOW = 30
DISPLACEMENT_THRESHOLD_PX = 15
MAX_MATCH_DIST_PX = 40   # greedy nearest-neighbor gate for stitching candidates frame-to-frame into tracks


def main():
    model = YOLO(MODEL_PATH)
    cap = cv2.VideoCapture(VIDEO_PATH)

    rows = []
    for start, end in DEAD_ZONE_RANGES:
        for frame_idx in range(start, end):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                continue

            results = model.predict(frame, conf=CONF_THRESHOLD, imgsz=IMGSZ, verbose=False)
            boxes = results[0].boxes
            if boxes is None or len(boxes) == 0:
                continue

            xyxy = boxes.xyxy.cpu().numpy()
            confs = boxes.conf.cpu().numpy()
            for (x1, y1, x2, y2), c in zip(xyxy, confs):
                rows.append({
                    "frame": frame_idx,
                    "x_center": (x1 + x2) / 2,
                    "y_center": (y1 + y2) / 2,
                    "conf": float(c),
                })

    df = pd.DataFrame(rows)
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"Raw candidates written to {OUTPUT_CSV} ({len(df)} rows)")

    if df.empty:
        print("No candidates at all, even at conf=0.05 -> capture-level wall confirmed.")
        return

    # Greedy nearest-neighbor stitching into per-frame-sequence tracks, since
    # we have no track IDs from a raw model.predict() call (no ByteTrack here).
    df = df.sort_values("frame").reset_index(drop=True)
    track_id = 0
    df["track_id"] = -1
    open_tracks = {}  # track_id -> (last_frame, x, y)

    for idx, row in df.iterrows():
        best_tid, best_dist = None, MAX_MATCH_DIST_PX
        for tid, (last_frame, x, y) in open_tracks.items():
            if row["frame"] - last_frame > 3:
                continue  # same 3-frame stitch gap convention as production
            dist = ((row["x_center"] - x) ** 2 + (row["y_center"] - y) ** 2) ** 0.5
            if dist < best_dist:
                best_tid, best_dist = tid, dist
        if best_tid is None:
            best_tid = track_id
            track_id += 1
        df.at[idx, "track_id"] = best_tid
        open_tracks[best_tid] = (row["frame"], row["x_center"], row["y_center"])

    # For each track, compute rolling 30-frame NET displacement (not
    # cumulative) and flag whether it ever exceeds the real-ball threshold.
    summary_rows = []
    for tid, g in df.groupby("track_id"):
        g = g.sort_values("frame")
        if len(g) < 2:
            continue
        max_net_disp = 0.0
        frames = g["frame"].values
        xs = g["x_center"].values
        ys = g["y_center"].values
        for i in range(len(g)):
            window_mask = (frames >= frames[i]) & (frames <= frames[i] + DISPLACEMENT_WINDOW)
            if window_mask.sum() < 2:
                continue
            wx, wy = xs[window_mask], ys[window_mask]
            net_disp = ((wx[-1] - wx[0]) ** 2 + (wy[-1] - wy[0]) ** 2) ** 0.5
            max_net_disp = max(max_net_disp, net_disp)

        summary_rows.append({
            "track_id": tid,
            "start_frame": int(frames.min()),
            "end_frame": int(frames.max()),
            "n_frames": len(g),
            "max_net_displacement_px": round(max_net_disp, 1),
            "moving": max_net_disp > DISPLACEMENT_THRESHOLD_PX,
        })

    summary = pd.DataFrame(summary_rows).sort_values("max_net_displacement_px", ascending=False)
    SUMMARY_CSV.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(SUMMARY_CSV, index=False)

    n_moving = summary["moving"].sum()
    print(f"\n{n_moving} / {len(summary)} candidate tracks show real net displacement (>{DISPLACEMENT_THRESHOLD_PX}px).")
    if n_moving == 0:
        print("-> No moving candidates anywhere in the dead zone, even at conf=0.05.")
        print("   Capture-level wall confirmed. Don't relabel; move to Week 3.")
    else:
        print("-> Some candidates ARE moving. Top 5 by displacement:")
        print(summary.head(5).to_string(index=False))
        print("   Manually check these frame ranges in the video before deciding to relabel.")
    print(f"\nFull summary written to {SUMMARY_CSV}")


if __name__ == "__main__":
    main()

