"""
extract_raw_ball_detections.py -- run the ball model over the first N
frames of a video with NO tracking/filtering at low confidence, and dump
every detection. Input for offline_eval.py / ball_linker tuning.
Optionally also writes production-style tracked player rows.

Reads sequentially (no cap.set seeking -- see the 2026-09-09 finding that
seeking can return different frames on fast motion).

Usage:
  python extract_raw_ball_detections.py <video> <out_csv> --end-frame 2800 \
      [--imgsz 2560] [--players-out raw_players.csv] [--coord-scale 2.0]
"""

import argparse
import csv
import time

import cv2
from ultralytics import YOLO

import config
import detection


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("out_csv")
    ap.add_argument("--end-frame", type=int, default=10**9)
    ap.add_argument("--imgsz", type=int, default=config.INFERENCE_IMGSZ)
    ap.add_argument("--conf", type=float, default=0.05)
    ap.add_argument("--players-out")
    ap.add_argument("--coord-scale", type=float, default=1.0,
                    help="multiply output coordinates (e.g. 2.0 to map a 1080p transcode back to 4K pixel space)")
    ap.add_argument("--half", action="store_true", help="FP16 inference (GPU only)")
    a = ap.parse_args()
    k = a.coord_scale

    model = YOLO(str(config.BALL_MODEL_PATH))
    player_model = tracker = None
    if a.players_out:
        import supervision as sv
        player_model = YOLO(str(config.PLAYER_MODEL_PATH))
        tracker = sv.ByteTrack(
            track_activation_threshold=config.TRACKER_ACTIVATION_THRESHOLD,
            lost_track_buffer=config.PLAYER_TRACKER_LOST_BUFFER,
            minimum_matching_threshold=config.PLAYER_TRACKER_MATCHING_THRESHOLD,
            frame_rate=config.TRACKER_FRAME_RATE,
        )
        pf = open(a.players_out, "w", newline="")
        pw = csv.writer(pf)
        pw.writerow(["frame", "type", "track_id", "pixel_x", "pixel_y", "x1", "y1", "x2", "y2", "confidence"])

    cap = cv2.VideoCapture(a.video)
    t0 = time.time()
    with open(a.out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame", "pixel_x", "pixel_y", "x1", "y1", "x2", "y2", "confidence"])
        fn = 0
        while fn <= a.end_frame:
            ok, frame = cap.read()
            if not ok:
                break
            r = model(frame, conf=a.conf, imgsz=a.imgsz, verbose=False, **detection.fp16_kwargs(a.half))[0]
            for (x1, y1, x2, y2), c in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist()):
                x1, y1, x2, y2 = x1 * k, y1 * k, x2 * k, y2 * k
                w.writerow([fn, (x1 + x2) / 2, (y1 + y2) / 2, x1, y1, x2, y2, c])
            if player_model is not None:
                import supervision as sv
                pr = player_model(frame, classes=[0], conf=config.PLAYER_CONF_THRESHOLD,
                                  imgsz=config.INFERENCE_IMGSZ, verbose=False)[0]
                det = tracker.update_with_detections(sv.Detections.from_ultralytics(pr))
                for i, (x1, y1, x2, y2) in enumerate((det.xyxy * k).tolist()):
                    pw.writerow([fn, "player", int(det.tracker_id[i]), (x1 + x2) / 2, (y1 + y2) / 2,
                                 x1, y1, x2, y2, float(det.confidence[i])])
            fn += 1
            if fn % 250 == 0:
                print(f"  {fn} frames, {time.time() - t0:.0f}s", flush=True)
    if a.players_out:
        pf.close()
    print(f"done: {fn} frames -> {a.out_csv}")


if __name__ == "__main__":
    main()
