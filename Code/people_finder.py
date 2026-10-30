"""
people_finder.py

Doubles detection for hands-free recording (2026-10-29): finds the people in one
camera picture with the same person model the analysis uses (yolov8n.pt) and
returns where each one stands (bottom middle of the box, picture pixels).
aim_guide.players_on_court then counts the ones on the court.

Needs ultralytics (the GPU image has it; runs fine on CPU for one picture).

Run directly:  python Code/people_finder.py frame.jpg path/to/yolov8n.pt
"""

import sys

IMGSZ = 1280      # far-end players are small; the default 640 misses some
CONF = 0.3
_models = {}


def feet(frame_bgr, model_path):
    from ultralytics import YOLO
    if model_path not in _models:
        _models[model_path] = YOLO(model_path)
    r = _models[model_path].predict(frame_bgr, imgsz=IMGSZ, conf=CONF, classes=[0], device="cpu", verbose=False)[0]
    return [[round((x1 + x2) / 2, 1), round(y2, 1)] for x1, _, x2, y2 in r.boxes.xyxy.tolist()]


if __name__ == "__main__":
    import time

    import cv2
    t0 = time.time()
    found = feet(cv2.imread(sys.argv[1]), sys.argv[2])
    print(f"{len(found)} people in {time.time() - t0:.1f}s: {found}")
