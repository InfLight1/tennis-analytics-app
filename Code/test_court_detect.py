"""
test_court_detect.py

Smoke test for court_detect.detect_court on our filming view (camera behind one
baseline). Uses the hand-checked test frame Diagnostics/calib_test_frame_clip2.jpg
(skips if that local file isn't there): the court must be found with a confident
score and the 7 points must land within 20 px of where they were checked by eye
on 2026-10-14 (4K frame).

Run directly:
    python Code/test_court_detect.py
"""

import os
import sys

import cv2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import court_detect  # noqa: E402

FRAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Diagnostics", "calib_test_frame_clip2.jpg")
CHECKED = {   # 3840x2160 pixels, overlay checked by eye on the painted lines
    "baseline_near_left": (286, 1478), "baseline_near_right": (3168, 1405),
    "service_line_near_left": (1020, 962), "service_line_near_right": (2706, 891),
}
TOLERANCE_PX = 20

if __name__ == "__main__":
    if not os.path.exists(FRAME):
        print("SKIP: test frame not found")
        sys.exit(0)
    res = court_detect.detect_court(cv2.imread(FRAME))
    ok = res["ok"] and res["score"] >= court_detect.OK_SCORE
    print(f"{'PASS' if ok else 'FAIL'}  court found: ok={res['ok']} score={res['score']}")
    for name, (x, y) in CHECKED.items():
        px, py = res["points"][name] if res["points"] else (1e9, 1e9)
        d = ((px - x) ** 2 + (py - y) ** 2) ** 0.5
        good = d <= TOLERANCE_PX
        ok &= good
        print(f"{'PASS' if good else 'FAIL'}  {name}: {d:.0f} px from the checked spot")
    sys.exit(0 if ok else 1)
